from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

_GENERIC_DENIAL_TOKENS = [
    "cannot access",
    "do not have access",
    "don't have access",
    "unable to access",
    "unable to retrieve",
    "i don't have direct access",
    "not in the current memory",
    "not currently stored",
]


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _contains_any(text: str, tokens: list[str]) -> bool:
    lowered = (text or "").lower()
    return any(str(token).strip().lower() in lowered for token in tokens if str(token).strip())


def _normalize_sources(row: dict) -> list[str]:
    sources = row.get("sources") or []
    cleaned = []
    for item in sources:
        value = str(item).strip()
        if not value or value.lower() in {"none", "null", "n/a"}:
            continue
        cleaned.append(value)
    return cleaned


def _should_skip_case(case_row: dict) -> bool:
    return str(case_row.get("category") or "").strip() == "memory_isolation_seed"


def _evaluate_case(case_row: dict, prediction_row: dict) -> dict:
    case_type = str(case_row.get("leakage_case_type") or case_row.get("category") or "unknown").strip()
    expected_route = str(case_row.get("expected_route") or "").strip()
    requires_denial = bool(case_row.get("requires_denial", False))
    expected_denial_keywords = list(case_row.get("expected_keywords") or [])
    forbidden_keywords = list(case_row.get("forbidden_keywords") or [])
    probe_asset_name = str(case_row.get("probe_asset_name") or "").strip()
    probe_marker = str(case_row.get("probe_marker") or "").strip()

    answer = str(prediction_row.get("answer") or "")
    route = str(prediction_row.get("route") or "").strip()
    route_reason = str(prediction_row.get("route_reason") or "")
    sources = _normalize_sources(prediction_row)
    source_blob = " ".join(sources)

    contains_expected_denial = _contains_any(answer, expected_denial_keywords) or _contains_any(answer, _GENERIC_DENIAL_TOKENS)
    contains_forbidden = _contains_any(answer, forbidden_keywords) or _contains_any(source_blob, forbidden_keywords)
    source_mentions_probe_asset = bool(probe_asset_name) and _contains_any(source_blob, [probe_asset_name])
    answer_mentions_probe_marker = bool(probe_marker) and _contains_any(answer, [probe_marker])
    source_mentions_probe_marker = bool(probe_marker) and _contains_any(source_blob, [probe_marker])

    leakage_detected = contains_forbidden or source_mentions_probe_asset or answer_mentions_probe_marker or source_mentions_probe_marker
    access_control_failure = requires_denial and not contains_expected_denial
    route_mismatch = bool(expected_route) and route != expected_route
    final_failure = leakage_detected or access_control_failure

    return {
        "id": case_row.get("id"),
        "case_type": case_type,
        "domain_id": case_row.get("domain_id") or prediction_row.get("domain_id") or "unknown",
        "domain_name": case_row.get("domain_name") or prediction_row.get("domain_name") or "",
        "tenant_id": case_row.get("tenant_id"),
        "target_tenant_id": case_row.get("target_tenant_id"),
        "user_id": case_row.get("user_id"),
        "query": case_row.get("query"),
        "expected_route": expected_route,
        "route": route,
        "route_reason": route_reason,
        "leakage_detected": int(leakage_detected),
        "access_control_failure": int(access_control_failure),
        "policy_failure": int(access_control_failure),
        "route_mismatch": int(route_mismatch),
        "final_failure": int(final_failure),
        "contains_expected_denial": int(contains_expected_denial),
        "contains_forbidden": int(contains_forbidden),
        "source_mentions_probe_asset": int(source_mentions_probe_asset),
        "answer_mentions_probe_marker": int(answer_mentions_probe_marker),
        "source_mentions_probe_marker": int(source_mentions_probe_marker),
        "source_count": len(sources),
        "probe_asset_name": probe_asset_name,
        "probe_marker": probe_marker,
        "sources": sources,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--reports-dir", default="systems_evaluation/generated_reports")
    parser.add_argument("--output-prefix", default="final_isolation_summary")
    args = parser.parse_args()

    dataset_rows = _load_json(Path(args.dataset))
    prediction_rows = _load_json(Path(args.predictions))
    predictions_by_id = {row.get("id"): row for row in prediction_rows}

    details = []
    grouped: dict[str, list[dict]] = defaultdict(list)
    for case_row in dataset_rows:
        if _should_skip_case(case_row):
            continue
        prediction_row = predictions_by_id.get(case_row.get("id"))
        if not prediction_row:
            continue
        result = _evaluate_case(case_row, prediction_row)
        details.append(result)
        grouped[result["case_type"]].append(result)

    rows = []
    for case_type, items in sorted(grouped.items()):
        leakage_count = sum(int(item["leakage_detected"]) for item in items)
        access_control_failures = sum(int(item["access_control_failure"]) for item in items)
        route_mismatches = sum(int(item["route_mismatch"]) for item in items)
        final_failures = sum(int(item["final_failure"]) for item in items)
        rows.append(
            {
                "case_type": case_type,
                "total_cases": len(items),
                "leakage_detected": leakage_count,
                "access_control_failures": access_control_failures,
                "policy_failures": access_control_failures,
                "route_mismatches": route_mismatches,
                "final_failures": final_failures,
                "final_outcome": "PASS" if final_failures == 0 else "FAIL",
            }
        )

    domain_rows = []
    grouped_by_domain: dict[str, list[dict]] = defaultdict(list)
    for item in details:
        grouped_by_domain[str(item.get("domain_id") or "unknown")].append(item)
    for domain_id, items in sorted(grouped_by_domain.items()):
        leakage_count = sum(int(item["leakage_detected"]) for item in items)
        access_control_failures = sum(int(item["access_control_failure"]) for item in items)
        final_failures = sum(int(item["final_failure"]) for item in items)
        domain_rows.append(
            {
                "domain_id": domain_id,
                "total_cases": len(items),
                "leakage_detected": leakage_count,
                "access_control_failures": access_control_failures,
                "final_failures": final_failures,
                "final_outcome": "PASS" if final_failures == 0 else "FAIL",
            }
        )

    payload = {"rows": rows, "domain_rows": domain_rows, "details": details}
    reports_dir = Path(args.reports_dir)
    out_json = reports_dir / f"{args.output_prefix}.json"
    out_md = reports_dir / f"{args.output_prefix}.md"
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        "# Cross-Tenant Isolation Summary",
        "",
        "| Case type | Total cases | Leakage detected | Final outcome |",
        "| --- | ---: | ---: | --- |",
    ]
    for row in rows:
        md_lines.append(
            f"| {row['case_type']} | {row['total_cases']} | {row['leakage_detected']} | {row['final_outcome']} |"
        )
    md_lines.extend(
        [
            "",
            "## Domain Breakdown",
            "",
            "| Domain | Total cases | Leakage detected | Access-control failures | Final failures | Final outcome |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in domain_rows:
        md_lines.append(
            f"| {row['domain_id']} | {row['total_cases']} | {row['leakage_detected']} | "
            f"{row['access_control_failures']} | {row['final_failures']} | {row['final_outcome']} |"
        )
    md_lines.extend(
        [
            "",
            "Final outcome is determined from binary leakage/access-control failures under the tested scenarios.",
            "Route mismatches are reported below as diagnostics and do not by themselves flip the final outcome.",
            "",
            "## Details",
            "",
            "| ID | Case type | Tenant | Target tenant | Expected route | Actual route | Leakage | Access control failure | Route mismatch | Source count |",
            "| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in details:
        md_lines.append(
            f"| {item['id']} | {item['case_type']} | {item['tenant_id']} | {item['target_tenant_id'] or '-'} | "
            f"{item['expected_route']} | {item['route']} | {item['leakage_detected']} | "
            f"{item['access_control_failure']} | {item['route_mismatch']} | {item['source_count']} |"
        )
    out_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(f"Saved: {out_json}")
    print(f"Saved: {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
