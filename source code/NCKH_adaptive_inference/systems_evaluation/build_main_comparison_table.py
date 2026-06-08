from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _route_accuracy(dataset_rows, prediction_rows) -> float:
    expected = {row["id"]: row["expected_route"] for row in dataset_rows}
    matched = 0
    total = 0
    for row in prediction_rows:
        case_id = row.get("id")
        if case_id in expected:
            total += 1
            if row.get("route") == expected[case_id]:
                matched += 1
    return (matched / total) if total else 0.0


def _p95_latency_ms(prediction_rows) -> float:
    values = sorted(float(row.get("latency_ms", 0.0) or 0.0) for row in prediction_rows)
    if not values:
        return 0.0
    index = min(len(values) - 1, int(0.95 * (len(values) - 1)))
    return values[index]


def _avg_latency_ms(prediction_rows) -> float:
    values = [float(row.get("latency_ms", 0.0) or 0.0) for row in prediction_rows]
    return mean(values) if values else 0.0


def _load_answer_quality(report_path: Path) -> float:
    if not report_path.exists():
        return 0.0
    report = _load_json(report_path)
    overall = report.get("overall") or {}
    return float(
        overall.get("answer_quality", overall.get("accuracy", 0.0)) or 0.0
    )


def _load_report_metric(report_path: Path, metric: str) -> float:
    if not report_path.exists():
        return 0.0
    report = _load_json(report_path)
    overall = report.get("overall") or {}
    return float(overall.get(metric, 0.0) or 0.0)


def _load_answer_quality_for_domain(report_path: Path, domain_id: str) -> float:
    if not report_path.exists():
        return 0.0
    report = _load_json(report_path)
    domain_metrics = ((report.get("by_slice") or {}).get("domain_id") or {}).get(domain_id) or {}
    return float(domain_metrics.get("answer_quality", 0.0) or 0.0)


def _load_domain_metric(report_path: Path, domain_id: str, metric: str) -> float:
    if not report_path.exists():
        return 0.0
    report = _load_json(report_path)
    domain_metrics = ((report.get("by_slice") or {}).get("domain_id") or {}).get(domain_id) or {}
    return float(domain_metrics.get(metric, 0.0) or 0.0)


def _domain_ids(dataset_rows) -> list[str]:
    return sorted({str(row.get("domain_id") or "unknown") for row in dataset_rows})


def _filter_domain(rows, domain_id: str):
    return [row for row in rows if str(row.get("domain_id") or "unknown") == domain_id]


def _fmt(x: float) -> str:
    return f"{x:.4f}"


def _parse_row_spec(raw: str) -> dict:
    parts = [part.strip() for part in raw.split("|")]
    if len(parts) != 5:
        raise SystemExit(
            "Each --row must have 5 pipe-separated fields: "
            "name|baseline_type|route_predictions|e2e_predictions|answer_report"
        )
    return {
        "name": parts[0],
        "baseline_type": parts[1],
        "route_pred": parts[2],
        "e2e_pred": parts[3],
        "quality": parts[4],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--reports-dir", default="systems_evaluation/generated_reports")
    parser.add_argument("--output-prefix", default="final_main_table")
    parser.add_argument(
        "--row",
        action="append",
        required=True,
        help="name|baseline_type|route_predictions|e2e_predictions|answer_report",
    )
    args = parser.parse_args()

    dataset_rows = _load_json(Path(args.dataset))
    reports_dir = Path(args.reports_dir)
    rows = []

    for raw_row in args.row:
        spec = _parse_row_spec(raw_row)
        route_rows = _load_json(reports_dir / spec["route_pred"])
        e2e_rows = _load_json(reports_dir / spec["e2e_pred"])
        rows.append(
            {
                "method": spec["name"],
                "baseline_type": spec["baseline_type"],
                "route_suitability": _route_accuracy(dataset_rows, route_rows),
                "response_quality": _load_answer_quality(reports_dir / spec["quality"]),
                "groundedness": _load_report_metric(reports_dir / spec["quality"], "groundedness"),
                "source_compliance": _load_report_metric(reports_dir / spec["quality"], "source_compliance"),
                "refusal_safety": _load_report_metric(reports_dir / spec["quality"], "refusal_safety"),
                "avg_latency_ms": _avg_latency_ms(e2e_rows),
                "p95_latency_ms": _p95_latency_ms(e2e_rows),
                "orchestration_overhead_ms": _avg_latency_ms(route_rows),
            }
        )

    domain_rows = []
    for raw_row in args.row:
        spec = _parse_row_spec(raw_row)
        route_rows = _load_json(reports_dir / spec["route_pred"])
        e2e_rows = _load_json(reports_dir / spec["e2e_pred"])
        for domain_id in _domain_ids(dataset_rows):
            ds_domain = _filter_domain(dataset_rows, domain_id)
            route_domain = _filter_domain(route_rows, domain_id)
            e2e_domain = _filter_domain(e2e_rows, domain_id)
            domain_rows.append(
                {
                    "method": spec["name"],
                    "baseline_type": spec["baseline_type"],
                    "domain_id": domain_id,
                    "route_suitability": _route_accuracy(ds_domain, route_domain),
                    "response_quality": _load_answer_quality_for_domain(reports_dir / spec["quality"], domain_id),
                    "groundedness": _load_domain_metric(reports_dir / spec["quality"], domain_id, "groundedness"),
                    "source_compliance": _load_domain_metric(reports_dir / spec["quality"], domain_id, "source_compliance"),
                    "refusal_safety": _load_domain_metric(reports_dir / spec["quality"], domain_id, "refusal_safety"),
                    "avg_latency_ms": _avg_latency_ms(e2e_domain),
                    "p95_latency_ms": _p95_latency_ms(e2e_domain),
                    "orchestration_overhead_ms": _avg_latency_ms(route_domain),
                }
            )

    out_json = reports_dir / f"{args.output_prefix}.json"
    out_md = reports_dir / f"{args.output_prefix}.md"
    out_json.write_text(json.dumps({"rows": rows, "domain_rows": domain_rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        "# Main Systems Comparison Table",
        "",
        "| Method | Baseline type | Route suitability | Response quality | Groundedness | Source compliance | Refusal safety | Avg latency (ms) | P95 latency (ms) | Orchestration overhead (ms) |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        md_lines.append(
            f"| {row['method']} | {row['baseline_type']} | {_fmt(row['route_suitability'])} | "
            f"{_fmt(row['response_quality'])} | {_fmt(row['groundedness'])} | "
            f"{_fmt(row['source_compliance'])} | {_fmt(row['refusal_safety'])} | {row['avg_latency_ms']:.1f} | "
            f"{row['p95_latency_ms']:.1f} | "
            f"{row['orchestration_overhead_ms']:.1f} |"
        )
    md_lines.extend(
        [
            "",
            "## Domain Breakdown",
            "",
            "| Method | Domain | Route suitability | Response quality | Groundedness | Source compliance | Refusal safety | Avg latency (ms) | P95 latency (ms) | Overhead (ms) |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in domain_rows:
        md_lines.append(
            f"| {row['method']} | {row['domain_id']} | {_fmt(row['route_suitability'])} | "
            f"{_fmt(row['response_quality'])} | {_fmt(row['groundedness'])} | "
            f"{_fmt(row['source_compliance'])} | {_fmt(row['refusal_safety'])} | {row['avg_latency_ms']:.1f} | "
            f"{row['p95_latency_ms']:.1f} | {row['orchestration_overhead_ms']:.1f} |"
        )
    out_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(f"Saved: {out_json}")
    print(f"Saved: {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
