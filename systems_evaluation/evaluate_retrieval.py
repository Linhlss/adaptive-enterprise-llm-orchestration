
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import replace
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Sequence

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from enterprise_runtime.config import bootstrap_dirs, init_embedding_settings
from enterprise_runtime.llm_service import get_or_create_profile
from enterprise_runtime.retrieval import (
    extract_node_metadata,
    extract_node_text,
    file_hints_from_question,
    prioritize_nodes_by_file_hint,
    retrieve_ranked_items,
)
from enterprise_runtime.router import route_question
from enterprise_runtime.runtime_manager import get_runtime

DATASET_PATH = BASE_DIR / "systems_evaluation" / "test_queries_multidomain.json"
ARTIFACTS_DIR = BASE_DIR / "systems_evaluation" / "artifacts"
REPORT_PATH = BASE_DIR / "systems_evaluation" / "retrieval_results.md"
ERROR_PATH = BASE_DIR / "systems_evaluation" / "error_analysis.md"
VECTOR_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".md"}


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
    notes: str
    replay_selected_route: str = ""
    replay_model_class: str = ""
    replay_model_name: str = ""
    replay_route_reason: str = ""
    replay_route_score: float = 0.0
    replay_route_policy: str = ""
    replay_route_candidates: dict[str, float] | None = None
    replay_route_features: dict[str, object] | None = None
    replay_model_selection_policy: str = ""
    replay_direct_answer: str = ""
    replay_direct_answer_detected: bool = False


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
            expected_route=item.get("expected_route", "retrieval"),
            relevant_sources=item.get("relevant_docs", item.get("relevant_sources", [])),
            expected_answer_keywords=item.get("expected_keywords", item.get("expected_answer_keywords", [])),
            forbidden_keywords=item.get("forbidden_keywords", []),
            requires_sources=bool(item.get("requires_sources", False)),
            notes=item.get("notes", ""),
            replay_selected_route=item.get("replay_selected_route", ""),
            replay_model_class=item.get("replay_model_class", ""),
            replay_model_name=item.get("replay_model_name", ""),
            replay_route_reason=item.get("replay_route_reason", ""),
            replay_route_score=float(item.get("replay_route_score", 0.0) or 0.0),
            replay_route_policy=item.get("replay_route_policy", ""),
            replay_route_candidates=item.get("replay_route_candidates", {}),
            replay_route_features=item.get("replay_route_features", {}),
            replay_model_selection_policy=item.get("replay_model_selection_policy", ""),
            replay_direct_answer=item.get("replay_direct_answer", ""),
            replay_direct_answer_detected=bool(item.get("replay_direct_answer_detected", False)),
        )
        for item in raw
    ]


def is_vectorizable_case(case: QueryCase) -> bool:
    if case.expected_route != "retrieval" or not case.relevant_sources:
        return False
    return all(Path(doc).suffix.lower() in VECTOR_EXTENSIONS for doc in case.relevant_sources)


def source_name_from_node(result: Any) -> str:
    meta = extract_node_metadata(result)
    return str(meta.get("file_name") or meta.get("source_ref") or meta.get("source_url") or "").strip()


def serialize_result(result: Any) -> Dict[str, Any]:
    meta = extract_node_metadata(result)
    return {
        "source": source_name_from_node(result),
        "score": float(getattr(result, "score", 0.0) or 0.0),
        "text_preview": extract_node_text(result)[:240],
        "scope": meta.get("tenant_scope"),
        "page_label": meta.get("page_label"),
        "sheet_name": meta.get("sheet_name"),
    }


def matches_any_source(candidate: str, relevant_sources: Sequence[str]) -> bool:
    lowered = candidate.lower()
    return any(ref.lower() in lowered for ref in relevant_sources)


def hit_at_k(results: Sequence[Dict[str, Any]], relevant_sources: Sequence[str], k: int) -> int:
    top_k = [r.get("source", "") for r in results[:k]]
    return int(any(matches_any_source(source, relevant_sources) for source in top_k))


def reciprocal_rank(results: Sequence[Dict[str, Any]], relevant_sources: Sequence[str]) -> float:
    for idx, item in enumerate(results, start=1):
        if matches_any_source(item.get("source", ""), relevant_sources):
            return 1.0 / idx
    return 0.0


def summarize_group(items: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if not items:
        return {
            "count": 0,
            "hit_at_1": 0.0,
            "hit_at_3": 0.0,
            "hit_at_5": 0.0,
            "mrr": 0.0,
            "route_accuracy": 0.0,
            "avg_retrieval_latency_ms": 0.0,
        }

    def avg(key: str) -> float:
        values = [float(item.get(key, 0.0) or 0.0) for item in items if item.get(key) is not None]
        if not values:
            return 0.0
        return round(sum(values) / len(values), 4)

    return {
        "count": len(items),
        "hit_at_1": avg("hit_at_1"),
        "hit_at_3": avg("hit_at_3"),
        "hit_at_5": avg("hit_at_5"),
        "mrr": avg("mrr"),
        "route_accuracy": avg("route_correct"),
        "avg_retrieval_latency_ms": round(
            sum(float(item.get("retrieval_latency_ms", 0.0) or 0.0) for item in items) / len(items),
            2,
        ),
    }


def build_variant_results(query: str, runtime: Any, variant: str, profile) -> list[Any]:
    raw_nodes = list(runtime.index.as_retriever(similarity_top_k=max(profile.top_k, 5)).retrieve(query))
    if variant == "dense_raw":
        return raw_nodes
    if variant == "dense_prioritized":
        hints = file_hints_from_question(query)
        return prioritize_nodes_by_file_hint(raw_nodes, hints, query)
    if variant == "runtime_profile":
        return retrieve_ranked_items(runtime, question=query, retrieval_query=query, profile=profile)
    raise ValueError(f"Unsupported variant: {variant}")


def _apply_profile_overrides(profile, overrides: Dict[str, Any] | None):
    if not overrides:
        return profile
    return replace(profile, **overrides)


def evaluate_variant(cases: Sequence[QueryCase], variant: str, profile_overrides: Dict[str, Any] | None = None) -> Dict[str, Any]:
    bootstrap_dirs()
    init_embedding_settings()

    runtimes: Dict[str, Any] = {}
    details: list[Dict[str, Any]] = []

    for case in cases:
        profile = _apply_profile_overrides(get_or_create_profile(case.tenant_id), profile_overrides)
        runtime = None
        if is_vectorizable_case(case):
            runtime = runtimes.get(case.tenant_id)
            if runtime is None:
                runtime = get_runtime(profile)
                runtimes[case.tenant_id] = runtime

        route_started = time.perf_counter()
        route_result = route_question(case.query, profile, "eval")
        route_latency_ms = (time.perf_counter() - route_started) * 1000

        retrieval_latency_ms = 0.0
        serialized_results: list[Dict[str, Any]] = []

        if is_vectorizable_case(case) and runtime is not None:
            retrieval_started = time.perf_counter()
            raw_results = build_variant_results(case.query, runtime, variant, profile)
            retrieval_latency_ms = (time.perf_counter() - retrieval_started) * 1000
            serialized_results = [serialize_result(item) for item in raw_results]

        relevant_sources = case.relevant_sources if is_vectorizable_case(case) else []

        details.append(
            {
                "id": case.id,
                "tenant_id": case.tenant_id,
                "category": case.category,
                "difficulty": case.difficulty,
                "query": case.query,
                "expected_route": case.expected_route,
                "predicted_route": route_result.route,
                "route_reason": route_result.reason,
                "route_correct": int(route_result.route == case.expected_route),
                "route_latency_ms": round(route_latency_ms, 2),
                "retrieval_latency_ms": round(retrieval_latency_ms, 2),
                "relevant_sources": relevant_sources,
                "results": serialized_results[:5],
                "hit_at_1": hit_at_k(serialized_results, relevant_sources, 1) if relevant_sources else None,
                "hit_at_3": hit_at_k(serialized_results, relevant_sources, 3) if relevant_sources else None,
                "hit_at_5": hit_at_k(serialized_results, relevant_sources, 5) if relevant_sources else None,
                "mrr": reciprocal_rank(serialized_results, relevant_sources) if relevant_sources else None,
                "notes": case.notes,
            }
        )

    retrieval_items = [item for item in details if item["relevant_sources"]]
    route_items = list(details)

    by_category: Dict[str, Any] = {}
    for category in sorted({item["category"] for item in route_items}):
        category_items = [item for item in retrieval_items if item["category"] == category]
        route_category_items = [item for item in route_items if item["category"] == category]
        summary = summarize_group(category_items)
        summary["route_accuracy"] = summarize_group(route_category_items)["route_accuracy"]
        by_category[category] = summary

    by_difficulty: Dict[str, Any] = {}
    for difficulty in sorted({item["difficulty"] for item in route_items}):
        difficulty_items = [item for item in retrieval_items if item["difficulty"] == difficulty]
        route_difficulty_items = [item for item in route_items if item["difficulty"] == difficulty]
        summary = summarize_group(difficulty_items)
        summary["route_accuracy"] = summarize_group(route_difficulty_items)["route_accuracy"]
        by_difficulty[difficulty] = summary

    by_tenant: Dict[str, Any] = {}
    for tenant_id in sorted({item["tenant_id"] for item in route_items}):
        tenant_items = [item for item in retrieval_items if item["tenant_id"] == tenant_id]
        route_tenant_items = [item for item in route_items if item["tenant_id"] == tenant_id]
        summary = summarize_group(tenant_items)
        summary["route_accuracy"] = summarize_group(route_tenant_items)["route_accuracy"]
        by_tenant[tenant_id] = summary

    failure_items = [item for item in retrieval_items if not item["hit_at_3"] or not item["route_correct"]]
    failure_items.sort(key=lambda item: (item["hit_at_3"], item["route_correct"], item["retrieval_latency_ms"]))

    route_distribution = Counter(item["predicted_route"] for item in route_items)

    return {
        "variant": variant,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "dataset_path": str(DATASET_PATH),
        "profile_overrides": profile_overrides or {},
        "overall_retrieval": summarize_group(retrieval_items),
        "overall_route": {
            "count": len(route_items),
            "accuracy": summarize_group(route_items)["route_accuracy"],
            "avg_route_latency_ms": round(
                statistics.mean(item["route_latency_ms"] for item in route_items) if route_items else 0.0,
                2,
            ),
            "distribution": dict(route_distribution),
        },
        "by_category": by_category,
        "by_difficulty": by_difficulty,
        "by_tenant": by_tenant,
        "failures": failure_items[:10],
        "details": details,
    }


def markdown_table(rows: Iterable[Sequence[str]]) -> str:
    rows = list(rows)
    if not rows:
        return ""
    header = "| " + " | ".join(rows[0]) + " |"
    sep = "| " + " | ".join(["---"] * len(rows[0])) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows[1:]]
    return "\n".join([header, sep] + body)


def render_report(results: Sequence[Dict[str, Any]]) -> str:
    lines = [
        "# Retrieval Evaluation",
        "",
        "This report is generated automatically by `systems_evaluation/evaluate_retrieval.py`.",
        "The current variants compare dense-retrieval baselines, file-hint post-processing, and real runtime optimizations.",
        "",
    ]

    summary_rows = [["Variant", "Count", "Hit@1", "Hit@3", "Hit@5", "MRR", "Route Acc.", "Avg Retrieval Latency (ms)"]]
    for result in results:
        overall = result["overall_retrieval"]
        route = result["overall_route"]
        summary_rows.append(
            [
                result["variant"],
                str(overall["count"]),
                f"{overall['hit_at_1']:.3f}",
                f"{overall['hit_at_3']:.3f}",
                f"{overall['hit_at_5']:.3f}",
                f"{overall['mrr']:.3f}",
                f"{route['accuracy']:.3f}",
                f"{overall['avg_retrieval_latency_ms']:.2f}",
            ]
        )
    lines.append(markdown_table(summary_rows))
    lines.append("")

    for result in results:
        lines.append(f"## Variant: `{result['variant']}`")
        lines.append("")
        lines.append(f"- Retrieval set: {result['overall_retrieval']['count']} questions with ground-truth sources.")
        lines.append(
            f"- Route accuracy: {result['overall_route']['accuracy']:.3f} | Avg route latency: {result['overall_route']['avg_route_latency_ms']:.2f} ms"
        )
        lines.append(f"- Route distribution: {json.dumps(result['overall_route']['distribution'], ensure_ascii=False)}")
        lines.append("")

        category_rows = [["Category", "Count", "Hit@3", "MRR", "Route Acc.", "Avg Retrieval Latency (ms)"]]
        for category, summary in result["by_category"].items():
            category_rows.append(
                [
                    category,
                    str(summary["count"]),
                    f"{summary['hit_at_3']:.3f}",
                    f"{summary['mrr']:.3f}",
                    f"{summary['route_accuracy']:.3f}",
                    f"{summary['avg_retrieval_latency_ms']:.2f}",
                ]
            )
        lines.append(markdown_table(category_rows))
        lines.append("")

        difficulty_rows = [["Difficulty", "Count", "Hit@3", "MRR", "Route Acc."]]
        for difficulty, summary in result["by_difficulty"].items():
            difficulty_rows.append(
                [
                    difficulty,
                    str(summary["count"]),
                    f"{summary['hit_at_3']:.3f}",
                    f"{summary['mrr']:.3f}",
                    f"{summary['route_accuracy']:.3f}",
                ]
            )
        lines.append(markdown_table(difficulty_rows))
        lines.append("")

        tenant_rows = [["Tenant", "Count", "Hit@3", "MRR", "Route Acc."]]
        for tenant_id, summary in result["by_tenant"].items():
            tenant_rows.append(
                [
                    tenant_id,
                    str(summary["count"]),
                    f"{summary['hit_at_3']:.3f}",
                    f"{summary['mrr']:.3f}",
                    f"{summary['route_accuracy']:.3f}",
                ]
            )
        lines.append(markdown_table(tenant_rows))
        lines.append("")

        lines.append("### Hard Cases")
        if not result["failures"]:
            lines.append("- No notable retrieval failures were found in the current benchmark pack.")
        else:
            for item in result["failures"][:5]:
                top_sources = [entry["source"] for entry in item["results"][:3] if entry["source"]]
                lines.append(
                    f"- `{item['id']}` | route `{item['predicted_route']}` vs `{item['expected_route']}` | "
                    f"Hit@3={item['hit_at_3']} | top sources={top_sources}"
                )
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def render_error_analysis(results: Sequence[Dict[str, Any]]) -> str:
    lines = [
        "# Error Analysis",
        "",
        "This document is generated automatically from failed retrieval queries in the benchmark.",
        "",
    ]

    for result in results:
        lines.append(f"## Variant: `{result['variant']}`")
        lines.append("")
        failures = result["failures"]
        if not failures:
            lines.append("- No retrieval failures were detected in the current test pack.")
            lines.append("")
            continue

        failure_reason_counter = defaultdict(int)
        for item in failures:
            if item["predicted_route"] != item["expected_route"]:
                failure_reason_counter["route_mismatch"] += 1
            if not item["hit_at_3"]:
                failure_reason_counter["missed_relevant_source"] += 1
            if item["results"] and item["results"][0]["source"] and not matches_any_source(item["results"][0]["source"], item["relevant_sources"]):
                failure_reason_counter["top1_wrong_source"] += 1

        for reason, count in sorted(failure_reason_counter.items()):
            lines.append(f"- {reason}: {count}")
        lines.append("")

        for item in failures[:5]:
            lines.append(f"### {item['id']}")
            lines.append(f"- Query: {item['query']}")
            lines.append(f"- Tenant: `{item['tenant_id']}` | Category: `{item['category']}` | Difficulty: `{item['difficulty']}`")
            lines.append(f"- Expected route: `{item['expected_route']}` | Predicted route: `{item['predicted_route']}`")
            lines.append(f"- Relevant sources: {item['relevant_sources']}")
            lines.append(f"- Top retrieved: {[entry['source'] for entry in item['results'][:3]]}")
            lines.append(f"- Notes: {item['notes'] or 'No notes.'}")
            lines.append("")

    return "\n".join(lines).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate retrieval and routing on benchmark queries.")
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument(
        "--variants",
        nargs="+",
        default=["dense_raw", "dense_prioritized"],
        choices=["dense_raw", "dense_prioritized", "runtime_profile"],
    )
    parser.add_argument("--json-out", type=Path, default=ARTIFACTS_DIR / "retrieval_metrics.json")
    parser.add_argument("--report-out", type=Path, default=REPORT_PATH)
    parser.add_argument("--error-out", type=Path, default=ERROR_PATH)
    args = parser.parse_args()

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    cases = load_cases(args.dataset)
    results = [evaluate_variant(cases, variant) for variant in args.variants]

    args.json_out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    args.report_out.write_text(render_report(results), encoding="utf-8")
    args.error_out.write_text(render_error_analysis(results), encoding="utf-8")

    print(f"Saved retrieval metrics to {args.json_out}")
    print(f"Saved retrieval report to {args.report_out}")
    print(f"Saved error analysis to {args.error_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
