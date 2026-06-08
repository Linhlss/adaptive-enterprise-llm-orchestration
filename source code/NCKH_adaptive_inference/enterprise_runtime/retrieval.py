from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Tuple

from enterprise_runtime.config import MAX_SOURCE_NODES
from enterprise_runtime.models import TenantProfile, TenantRuntime


def extract_node_text(result: Any) -> str:
    if isinstance(result, dict):
        if "content" in result:
            return str(result.get("content", "")).strip()
        if "text_preview" in result:
            return str(result.get("text_preview", "")).strip()

    node = getattr(result, "node", result)
    if hasattr(node, "get_content"):
        try:
            return node.get_content().strip()
        except Exception:
            return ""
    return str(node).strip()


def extract_node_metadata(result: Any) -> Dict[str, Any]:
    if isinstance(result, dict):
        return dict(result.get("metadata") or {})
    node = getattr(result, "node", result)
    return dict(getattr(node, "metadata", {}) or {})


def extract_node_score(result: Any) -> float:
    if isinstance(result, dict):
        return float(result.get("score", 0.0) or 0.0)
    return float(getattr(result, "score", 0.0) or 0.0)


def extract_node_id(result: Any) -> str:
    if isinstance(result, dict):
        raw = result.get("id")
        if raw:
            return str(raw)

    node = getattr(result, "node", result)
    node_id = getattr(node, "node_id", "")
    if node_id:
        return str(node_id)

    meta = extract_node_metadata(result)
    source = str(meta.get("source_ref") or meta.get("file_name") or meta.get("source_url") or "")
    text = extract_node_text(result)
    return hashlib.sha1(f"{source}::{text[:200]}".encode("utf-8", errors="ignore")).hexdigest()


def file_hints_from_question(question: str) -> List[str]:
    patterns = re.findall(
        r"[\w\-.]+\.(?:pdf|docx|doc|xlsx|xls|txt|md)",
        question,
        flags=re.IGNORECASE,
    )
    return [p.lower() for p in patterns]


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def _year_hints_from_question(question: str) -> list[str]:
    return re.findall(r"\b20\d{2}\b", question or "")


def _article_hint_from_question(question: str) -> int | None:
    m = re.search(r"article\s*(\d+)", question or "", flags=re.IGNORECASE)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _page_number(meta: Dict[str, Any]) -> int | None:
    raw = meta.get("page_label") or meta.get("page")
    if raw is None:
        return None
    m = re.search(r"\d+", str(raw))
    if not m:
        return None
    try:
        return int(m.group(0))
    except Exception:
        return None


def prioritize_nodes_by_file_hint(nodes: List[Any], hints: List[str], query: str = "") -> List[Any]:
    if not hints and not query:
        return nodes

    query_terms = _tokenize(query)
    year_hints = _year_hints_from_question(query)
    article_hint = _article_hint_from_question(query)
    lowered_query = (query or "").lower()
    first_page_intent = any(token in lowered_query for token in ["signed", "issued", "decision number", "which institution"])
    tuition_intent = "tuition" in lowered_query

    def score_item(item: Any) -> Tuple[int, int, int, int, float]:
        meta = extract_node_metadata(item)
        file_name = str(meta.get("file_name") or meta.get("source_ref") or "").lower()
        matched = any(h in file_name for h in hints)
        text = extract_node_text(item)[:1200]
        overlap = len(query_terms & _tokenize(text)) if query_terms else 0
        raw_score = extract_node_score(item)
        page_num = _page_number(meta)

        year_boost = sum(1 for year in year_hints if year in file_name)
        page_boost = 0
        if first_page_intent and page_num is not None and page_num <= 2:
            page_boost += 3
        if article_hint is not None and page_num is not None and abs(page_num - article_hint) <= 2:
            page_boost += 2
        if tuition_intent and page_num is not None and page_num in {3, 9, 10, 11, 12}:
            page_boost += 1

        return (1 if matched else 0, year_boost, page_boost, overlap, raw_score)

    return sorted(nodes, key=score_item, reverse=True)


def format_source(meta: Dict[str, Any], score: float) -> str:
    file_name = meta.get("file_name")
    source_ref = meta.get("source_ref")
    source_url = meta.get("source_url")
    scope = meta.get("tenant_scope", "unknown")

    main = file_name or source_ref or source_url or "Unknown source"
    parts = [main, f"scope={scope}", f"score={score:.3f}"]

    for key in ["page_label", "page", "sheet_name", "loaded_at"]:
        if meta.get(key):
            parts.append(f"{key}={meta[key]}")

    return " | ".join(parts)


def _dense_search(runtime: TenantRuntime, query: str, top_k: int) -> List[dict]:
    retriever = runtime.index.as_retriever(similarity_top_k=top_k)
    raw_nodes = list(retriever.retrieve(query))
    items: List[dict] = []
    for node in raw_nodes:
        items.append(
            {
                "id": extract_node_id(node),
                "content": extract_node_text(node),
                "metadata": extract_node_metadata(node),
                "score": extract_node_score(node),
                "raw": node,
            }
        )
    return items


def _merge_best(items: List[dict]) -> List[dict]:
    best: Dict[str, dict] = {}
    for item in items:
        item_id = extract_node_id(item)
        previous = best.get(item_id)
        if previous is None or float(item.get("score", 0.0) or 0.0) > float(previous.get("score", 0.0) or 0.0):
            best[item_id] = item
    merged = list(best.values())
    merged.sort(key=lambda item: float(item.get("score", 0.0) or 0.0), reverse=True)
    return merged


def retrieve_ranked_items(
    runtime: TenantRuntime,
    question: str,
    retrieval_query: str | None = None,
    profile: TenantProfile | None = None,
) -> List[dict]:
    profile = profile or runtime.profile
    candidate_top_k = max(profile.top_k * 3, MAX_SOURCE_NODES, 8)
    base_query = retrieval_query or question

    ranked = _dense_search(runtime, base_query, candidate_top_k)
    ranked = _merge_best(ranked)
    ranked = prioritize_nodes_by_file_hint(ranked, file_hints_from_question(question), base_query)
    return ranked


def retrieve_context(runtime: TenantRuntime, question: str, retrieval_query: str | None = None) -> Tuple[str, List[str]]:
    try:
        ranked = retrieve_ranked_items(runtime, question, retrieval_query=retrieval_query, profile=runtime.profile)
    except Exception:
        return "", []

    context_blocks: List[str] = []
    sources: List[str] = []

    for i, item in enumerate(ranked[:MAX_SOURCE_NODES], start=1):
        text = extract_node_text(item)[:1400]
        meta = extract_node_metadata(item)
        score = extract_node_score(item)
        src = format_source(meta, score)
        context_blocks.append(f"[Context {i}] ({src})\n{text}")
        sources.append(src)

    return "\n\n".join(context_blocks), list(dict.fromkeys(sources))
