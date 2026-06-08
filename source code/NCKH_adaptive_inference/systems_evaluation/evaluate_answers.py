from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Sequence


@dataclass
class QueryCase:
    id: str
    tenant_id: str
    domain_id: str
    domain_name: str
    user_id: str
    category: str
    difficulty: str
    query: str
    expected_route: str
    relevant_sources: list[str]
    expected_answer_keywords: list[str]
    forbidden_keywords: list[str]
    requires_sources: bool
    requires_denial: bool
    notes: str


def load_cases(dataset_path: Path) -> list[QueryCase]:
    raw = json.loads(dataset_path.read_text(encoding="utf-8"))
    return [
        QueryCase(
            id=item["id"],
            tenant_id=item.get("tenant_id", "default"),
            domain_id=item.get("domain_id", ""),
            domain_name=item.get("domain_name", ""),
            user_id=item.get("user_id", f"eval_{item['id']}"),
            category=item.get("category", "misc"),
            difficulty=item.get("difficulty", "medium"),
            query=item["query"],
            expected_route=item.get("expected_route", ""),
            relevant_sources=item.get("relevant_docs", item.get("relevant_sources", [])),
            expected_answer_keywords=item.get("expected_keywords", item.get("expected_answer_keywords", [])),
            forbidden_keywords=item.get("forbidden_keywords", []),
            requires_sources=bool(item.get("requires_sources", False)),
            requires_denial=bool(item.get("requires_denial", False)),
            notes=item.get("notes", ""),
        )
        for item in raw
    ]


def _safe_mean(values: Iterable[float]) -> float:
    values = list(values)
    return mean(values) if values else 0.0


def _normalize_match_text(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or "").strip().lower())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.replace("\u0111", "d")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"\w+", _normalize_match_text(text)))


def _normalize_source_name(value: str) -> str:
    return Path(str(value).strip()).name.lower()


def _extract_sources(raw_pred: Dict[str, Any]) -> List[str]:
    raw_sources = raw_pred.get("sources") or raw_pred.get("results") or []
    normalized: List[str] = []
    for item in raw_sources:
        if isinstance(item, str):
            normalized.append(_normalize_source_name(item))
        elif isinstance(item, dict):
            value = item.get("name") or item.get("source") or item.get("file_name") or item.get("path") or ""
            if value:
                normalized.append(_normalize_source_name(value))
    return normalized


def _extract_trace_sources(raw_pred: Dict[str, Any]) -> List[str]:
    raw_sources = raw_pred.get("retrieved_sources") or []
    normalized: List[str] = []
    for item in raw_sources:
        if isinstance(item, str):
            normalized.append(_normalize_source_name(item))
        elif isinstance(item, dict):
            value = item.get("name") or item.get("source") or item.get("file_name") or item.get("path") or ""
            if value:
                normalized.append(_normalize_source_name(value))
    return normalized


def _strip_source_appendix(answer: str) -> str:
    text = str(answer or "").strip()
    for marker in ("\nSources used:", "\nSources:", "\nSOURCE:"):
        if marker in text:
            text = text.split(marker, 1)[0].rstrip()
    return text


def _expected_language(question: str) -> str:
    q = str(question or "")
    if re.search(r"[\u00C0-\u1EF9]", q.lower()):
        return "vi"
    lowered = q.lower()
    if re.search(r"\b(how|give me|step-by-step|write|explain|precision|recall|thank you)\b", lowered):
        return "en"
    return "vi"


def _looks_english(text: str) -> bool:
    raw = str(text or "").lower()
    if re.search(r"[\u00C0-\u1EF9]", raw):
        return False

    tokens = re.findall(r"[a-zA-Z]+", raw)
    english_markers = {
        "the", "and", "with", "for", "from", "precision", "recall", "information",
        "retrieval", "machine", "learning", "example", "examples", "summary",
        "measures", "evaluates", "accuracy", "completeness", "results", "model",
    }
    english_hits = sum(1 for tok in tokens if tok in english_markers)
    return english_hits >= 3


def _language_alignment_score(question: str, answer: str) -> float:
    expected = _expected_language(question)
    if not answer.strip():
        return 0.0
    if expected == "vi" and _looks_english(answer):
        return 0.55
    if expected == "en" and re.search(r"[\u00C0-\u1EF9]", answer.lower()):
        return 0.7
    return 1.0


def _meta_artifact_penalty(answer: str) -> float:
    lowered = _normalize_match_text(answer)
    meta_markers = [
        "based on the provided data",
        "i would like to revise",
        "here is my rewritten answer",
        "to verify the answer",
        "re read the documents",
        "this revised question aims",
        "please let me know if you have any further questions",
        "i conclude that my previous answer was incorrect",
    ]
    hits = sum(1 for marker in meta_markers if marker in lowered)
    if hits >= 2:
        return 0.55
    if hits == 1:
        return 0.75
    return 1.0


def _keyword_coverage(answer: str, expected_keywords: Sequence[str]) -> float:
    if not expected_keywords:
        return 0.0
    normalized_answer = _normalize_match_text(answer)
    hits = sum(1 for keyword in expected_keywords if _normalize_match_text(keyword) in normalized_answer)
    return hits / len(expected_keywords)


def _forbidden_keyword_safety(answer: str, forbidden_keywords: Sequence[str]) -> float:
    if not forbidden_keywords:
        return 1.0
    normalized_answer = _normalize_match_text(answer)
    leaked = sum(1 for keyword in forbidden_keywords if _normalize_match_text(keyword) in normalized_answer)
    return 1.0 - (leaked / len(forbidden_keywords))


def _source_requirement_score(raw_pred: Dict[str, Any], case: QueryCase) -> float:
    if not case.requires_sources:
        return 1.0

    cited_sources = set(_extract_sources(raw_pred))
    trace_sources = set(_extract_trace_sources(raw_pred))
    all_sources = cited_sources | trace_sources
    if not all_sources:
        return 0.0

    relevant_sources = {_normalize_source_name(doc) for doc in case.relevant_sources if str(doc).strip()}
    if not relevant_sources:
        return 1.0
    if all_sources & relevant_sources:
        return 1.0
    if cited_sources:
        return 0.35
    return 0.15


def _refusal_safety_score(answer: str, case: QueryCase) -> float:
    if not (case.requires_denial or case.expected_route == "out_of_scope"):
        return 1.0
    refusal_keywords = _keyword_coverage(answer, case.expected_answer_keywords) if case.expected_answer_keywords else 0.0
    forbidden_safety = _forbidden_keyword_safety(answer, case.forbidden_keywords)
    return min(1.0, 0.7 * refusal_keywords + 0.3 * forbidden_safety)


def _context_groundedness(answer: str, raw_pred: Dict[str, Any], case: QueryCase) -> float:
    context_chunks: List[str] = []
    for key in ("contexts", "source_texts"):
        value = raw_pred.get(key) or []
        if isinstance(value, list):
            context_chunks.extend(str(item) for item in value)
    for key in ("context", "retrieved_context"):
        value = raw_pred.get(key)
        if isinstance(value, str):
            context_chunks.append(value)

    context_text = " ".join(context_chunks).strip()
    if context_text:
        answer_tokens = {tok for tok in _tokenize(answer) if len(tok) > 2}
        if not answer_tokens:
            return 0.0
        return len(answer_tokens & _tokenize(context_text)) / len(answer_tokens)

    source_docs = set(_extract_sources(raw_pred))
    relevant_docs = {_normalize_source_name(doc) for doc in case.relevant_sources}
    source_hit = 1.0 if source_docs & relevant_docs else 0.0
    return min(1.0, 0.7 * _keyword_coverage(answer, case.expected_answer_keywords) + 0.3 * source_hit)


def _prediction_map(raw_predictions: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    mapping: Dict[str, Dict[str, Any]] = {}
    for item in raw_predictions:
        key = str(item.get("id") or item.get("query") or "").strip()
        if key:
            mapping[key] = item
    return mapping


def evaluate_predictions(cases: Sequence[QueryCase], predictions: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    pred_map = _prediction_map(predictions)
    rows: List[Dict[str, Any]] = []

    for case in cases:
        raw_pred = pred_map.get(case.id) or pred_map.get(case.query) or {}
        answer = _strip_source_appendix(str(raw_pred.get("answer") or ""))
        route_match = float(case.expected_route == raw_pred.get("route")) if case.expected_route else 0.5
        keyword_coverage = _keyword_coverage(answer, case.expected_answer_keywords)
        completeness = keyword_coverage
        groundedness = _context_groundedness(answer, raw_pred, case)
        source_compliance = _source_requirement_score(raw_pred, case)
        refusal_safety = _refusal_safety_score(answer, case)
        forbidden_safety = _forbidden_keyword_safety(answer, case.forbidden_keywords)
        quality_base = min(1.0, 0.8 * completeness + 0.2 * groundedness)
        answer_quality = (
            quality_base
            * _language_alignment_score(case.query, answer)
            * _meta_artifact_penalty(answer)
            * (0.35 + 0.65 * source_compliance)
            * (0.35 + 0.65 * refusal_safety)
            * forbidden_safety
        )
        accuracy = min(
            1.0,
            0.45 * keyword_coverage
            + 0.2 * route_match
            + 0.2 * source_compliance
            + 0.15 * refusal_safety,
        )
        hallucination_rate = max(0.0, 1.0 - groundedness)

        rows.append(
            {
                "id": case.id,
                "tenant_id": case.tenant_id,
                "domain_id": raw_pred.get("domain_id") or case.domain_id,
                "domain_name": raw_pred.get("domain_name") or case.domain_name,
                "category": case.category,
                "difficulty": case.difficulty,
                "query": case.query,
                "answer_quality": answer_quality,
                "accuracy": accuracy,
                "groundedness": groundedness,
                "hallucination_rate": hallucination_rate,
                "completeness": completeness,
                "route_match": route_match,
                "source_compliance": source_compliance,
                "refusal_safety": refusal_safety,
                "forbidden_safety": forbidden_safety,
                "answer": answer,
            }
        )

    overall = {
        metric: _safe_mean(row[metric] for row in rows)
        for metric in (
            "answer_quality",
            "accuracy",
            "groundedness",
            "hallucination_rate",
            "completeness",
            "route_match",
            "source_compliance",
            "refusal_safety",
            "forbidden_safety",
        )
    }

    by_slice: Dict[str, Dict[str, Any]] = {}
    for field in ("domain_id", "tenant_id", "category", "difficulty"):
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row[field])].append(row)
        by_slice[field] = {
            name: {
                "count": len(group_rows),
                **{
                    metric: _safe_mean(row[metric] for row in group_rows)
                    for metric in (
                        "answer_quality",
                        "accuracy",
                        "groundedness",
                        "hallucination_rate",
                        "completeness",
                        "route_match",
                        "source_compliance",
                        "refusal_safety",
                        "forbidden_safety",
                    )
                },
            }
            for name, group_rows in sorted(grouped.items())
        }

    weakest = sorted(
        rows,
        key=lambda row: (
            row["answer_quality"],
            row["source_compliance"],
            row["refusal_safety"],
            row["groundedness"],
            row["completeness"],
        ),
    )[:10]
    return {"overall": overall, "by_slice": by_slice, "weakest": weakest, "rows": rows}


def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    header_line = "| " + " | ".join(headers) + " |"
    sep_line = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join([header_line, sep_line, *body])


def render_markdown(report: Dict[str, Any], label: str) -> str:
    overall = report["overall"]
    category_rows = [
        [
            name,
            metrics["count"],
            f"{metrics['answer_quality']:.3f}",
            f"{metrics['accuracy']:.3f}",
            f"{metrics['groundedness']:.3f}",
            f"{metrics['source_compliance']:.3f}",
            f"{metrics['refusal_safety']:.3f}",
            f"{metrics['hallucination_rate']:.3f}",
            f"{metrics['completeness']:.3f}",
        ]
        for name, metrics in report["by_slice"]["category"].items()
    ]
    domain_rows = [
        [
            name or "unknown",
            metrics["count"],
            f"{metrics['answer_quality']:.3f}",
            f"{metrics['accuracy']:.3f}",
            f"{metrics['groundedness']:.3f}",
            f"{metrics['source_compliance']:.3f}",
            f"{metrics['refusal_safety']:.3f}",
            f"{metrics['hallucination_rate']:.3f}",
            f"{metrics['completeness']:.3f}",
        ]
        for name, metrics in report["by_slice"].get("domain_id", {}).items()
    ] or [["unknown", 0, "0.000", "0.000", "0.000", "0.000", "0.000", "0.000", "0.000"]]
    weakest_rows = [
        [
            item["id"],
            item["category"],
            item["difficulty"],
            f"{item['answer_quality']:.3f}",
            f"{item['groundedness']:.3f}",
            item["query"],
        ]
        for item in report["weakest"]
    ] or [["-", "-", "-", "-", "-", "No evaluated examples"]]

    return "\n".join(
        [
            f"# Answer-Level Evaluation Report - {label}",
            "",
            "## Overall Metrics",
            _table(
                [
                    "System",
                    "Answer Quality",
                    "Legacy Accuracy",
                    "Groundedness",
                    "Source Compliance",
                    "Refusal Safety",
                    "Hallucination Rate",
                    "Completeness",
                    "Route Match",
                ],
                [[
                    label,
                    f"{overall['answer_quality']:.3f}",
                    f"{overall['accuracy']:.3f}",
                    f"{overall['groundedness']:.3f}",
                    f"{overall['source_compliance']:.3f}",
                    f"{overall['refusal_safety']:.3f}",
                    f"{overall['hallucination_rate']:.3f}",
                    f"{overall['completeness']:.3f}",
                    f"{overall['route_match']:.3f}",
                ]],
            ),
            "",
            "## Metrics by Category",
            _table(
                [
                    "Category",
                    "Count",
                    "Answer Quality",
                    "Legacy Accuracy",
                    "Groundedness",
                    "Source Compliance",
                    "Refusal Safety",
                    "Hallucination",
                    "Completeness",
                ],
                category_rows,
            ),
            "",
            "## Metrics by Domain",
            _table(
                [
                    "Domain",
                    "Count",
                    "Answer Quality",
                    "Legacy Accuracy",
                    "Groundedness",
                    "Source Compliance",
                    "Refusal Safety",
                    "Hallucination",
                    "Completeness",
                ],
                domain_rows,
            ),
            "",
            "## Weak Samples",
            _table(["ID", "Category", "Difficulty", "Answer Quality", "Groundedness", "Query"], weakest_rows),
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate answer-level predictions with lightweight lexical metrics.")
    parser.add_argument("--dataset", default="systems_evaluation/test_queries_q2_multidomain.json")
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--label", default="baseline")
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-md", default="")
    args = parser.parse_args()

    cases = load_cases(Path(args.dataset))
    predictions = json.loads(Path(args.predictions).read_text(encoding="utf-8"))
    report = evaluate_predictions(cases, predictions)
    rendered = render_markdown(report, args.label)
    print(rendered)

    if args.output_json:
        Path(args.output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.output_md:
        Path(args.output_md).write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
