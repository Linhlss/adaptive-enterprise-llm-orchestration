from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def load_expected_routes(dataset_path: Path) -> tuple[dict[str, str], dict[str, str]]:
    raw = json.loads(dataset_path.read_text(encoding="utf-8"))
    by_id: dict[str, str] = {}
    by_query: dict[str, str] = {}
    for item in raw:
        case_id = str(item.get("id", "")).strip()
        query = str(item.get("query", "")).strip()
        expected_route = str(item.get("expected_route", "")).strip()
        if case_id and expected_route:
            by_id[case_id] = expected_route
        if query and expected_route:
            by_query[query] = expected_route
    return by_id, by_query


def resolve_expected_route(
    record: dict[str, Any],
    expected_by_id: dict[str, str],
    expected_by_query: dict[str, str],
) -> str:
    rec_id = str(record.get("id", "")).strip()
    query = str(record.get("query", "")).strip()
    if rec_id and rec_id in expected_by_id:
        return expected_by_id[rec_id]
    if query and query in expected_by_query:
        return expected_by_query[query]
    return ""


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Route Consistency Report")
    lines.append("")
    lines.append(f"- Dataset: `{report['dataset_path']}`")
    lines.append(f"- Prediction files scanned: `{report['prediction_file_count']}`")
    lines.append(f"- Evaluated rows: `{report['evaluated_rows']}`")
    lines.append(f"- Route consistency (expected_route vs trace.route): `{report['consistency']:.4f}`")
    lines.append("")

    per_run = report.get("per_run", [])
    if per_run:
        lines.append("## Per Run Summary")
        lines.append("")
        lines.append("| Run | Rows | Matched | Consistency |")
        lines.append("| --- | ---: | ---: | ---: |")
        for run in per_run:
            lines.append(
                f"| {run['run_label']} | {run['rows']} | {run['matched']} | {run['consistency']:.4f} |"
            )
        lines.append("")

    confusion = report.get("confusion_matrix", {})
    if confusion:
        lines.append("## Confusion Matrix (Expected -> Actual)")
        lines.append("")
        lines.append("| Expected | Actual | Count |")
        lines.append("| --- | --- | ---: |")
        for expected_route in sorted(confusion.keys()):
            row = confusion[expected_route]
            for actual_route in sorted(row.keys()):
                lines.append(f"| {expected_route} | {actual_route} | {row[actual_route]} |")
        lines.append("")

    mismatches = report.get("top_mismatches", [])
    if mismatches:
        lines.append("## Top Mismatches")
        lines.append("")
        lines.append("| Run | ID | Expected | Actual | Query |")
        lines.append("| --- | --- | --- | --- | --- |")
        for item in mismatches:
            query_preview = str(item.get("query", "")).replace("\n", " ").strip()
            if len(query_preview) > 100:
                query_preview = query_preview[:97] + "..."
            lines.append(
                f"| {item['run_label']} | {item['id']} | {item['expected_route']} | {item['actual_route']} | {query_preview} |"
            )
        lines.append("")

    missing_expected = report.get("rows_without_expected_route", 0)
    if missing_expected > 0:
        lines.append(
            f"> Warning: `{missing_expected}` rows could not be matched back to dataset by `id` or `query`."
        )
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build consistency report between dataset expected_route and runtime trace.route."
    )
    parser.add_argument("--dataset", default="systems_evaluation/test_queries_q2_multidomain.json")
    parser.add_argument("--report-dir", default="systems_evaluation/generated_reports")
    parser.add_argument("--glob", default="*_predictions.json")
    parser.add_argument("--output-prefix", default="route_consistency")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    expected_by_id, expected_by_query = load_expected_routes(dataset_path)
    prediction_files = sorted(report_dir.glob(args.glob))

    all_rows = 0
    all_matches = 0
    rows_without_expected = 0
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    mismatch_rows: list[dict[str, Any]] = []
    per_run: list[dict[str, Any]] = []

    for pred_file in prediction_files:
        predictions = json.loads(pred_file.read_text(encoding="utf-8"))
        run_rows = 0
        run_matches = 0
        for row in predictions:
            expected_route = resolve_expected_route(row, expected_by_id, expected_by_query)
            actual_route = str(row.get("route", "")).strip()
            if not expected_route:
                rows_without_expected += 1
                continue
            run_rows += 1
            all_rows += 1
            confusion[expected_route][actual_route] += 1
            if expected_route == actual_route:
                run_matches += 1
                all_matches += 1
            else:
                mismatch_rows.append(
                    {
                        "run_label": pred_file.name,
                        "id": str(row.get("id", "")),
                        "query": str(row.get("query", "")),
                        "expected_route": expected_route,
                        "actual_route": actual_route,
                    }
                )

        consistency = (run_matches / run_rows) if run_rows else 0.0
        per_run.append(
            {
                "run_label": pred_file.name,
                "rows": run_rows,
                "matched": run_matches,
                "consistency": round(consistency, 4),
            }
        )

    overall_consistency = (all_matches / all_rows) if all_rows else 0.0
    report = {
        "dataset_path": str(dataset_path),
        "prediction_file_count": len(prediction_files),
        "evaluated_rows": all_rows,
        "matched_rows": all_matches,
        "consistency": round(overall_consistency, 4),
        "rows_without_expected_route": rows_without_expected,
        "per_run": per_run,
        "confusion_matrix": {
            expected_route: dict(actual_counts)
            for expected_route, actual_counts in sorted(confusion.items())
        },
        "top_mismatches": mismatch_rows[:30],
    }

    json_path = report_dir / f"{args.output_prefix}.json"
    md_path = report_dir / f"{args.output_prefix}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    if not prediction_files:
        print(
            "No prediction files found. Generated empty consistency report. "
            "Run benchmark first to populate generated_reports."
        )
    else:
        print(
            "Route consistency report generated: "
            f"consistency={report['consistency']:.4f}, files={len(prediction_files)}, rows={all_rows}"
        )
    print(f"JSON: {json_path}")
    print(f"MD: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
