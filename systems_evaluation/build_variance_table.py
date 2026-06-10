from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean, pstdev


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


def _avg_latency_ms(prediction_rows) -> float:
    values = [float(row.get("latency_ms", 0.0) or 0.0) for row in prediction_rows]
    return mean(values) if values else 0.0


def _quality(report_path: Path) -> float:
    report = _load_json(report_path)
    overall = report.get("overall") or {}
    return float(overall.get("answer_quality", overall.get("accuracy", 0.0)) or 0.0)


def _m(values: list[float]) -> float:
    return mean(values) if values else 0.0


def _s(values: list[float]) -> float:
    return pstdev(values) if len(values) > 1 else 0.0


def _fmt(x: float) -> str:
    return f"{x:.4f}"


def _parse_row_spec(raw: str) -> dict:
    parts = [part.strip() for part in raw.split("|")]
    if len(parts) < 5 or len(parts) % 2 != 1:
        raise SystemExit(
            "Each --row must have pipe-separated fields: "
            "name|predictions_run1|answer_report_run1|predictions_run2|answer_report_run2"
            "[|predictions_runN|answer_report_runN...]"
        )
    prediction_names = parts[1::2]
    report_names = parts[2::2]
    return {
        "name": parts[0],
        "predictions": prediction_names,
        "reports": report_names,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--reports-dir", default="systems_evaluation/generated_reports")
    parser.add_argument("--output-prefix", default="final_variance")
    parser.add_argument(
        "--row",
        action="append",
        required=True,
        help=(
            "name|predictions_run1|answer_report_run1|predictions_run2|answer_report_run2"
            "[|predictions_runN|answer_report_runN...]"
        ),
    )
    args = parser.parse_args()

    dataset_rows = _load_json(Path(args.dataset))
    reports_dir = Path(args.reports_dir)
    rows = []

    for raw_row in args.row:
        spec = _parse_row_spec(raw_row)
        route_vals = []
        quality_vals = []
        latency_vals = []
        for pred_name, report_name in zip(spec["predictions"], spec["reports"], strict=True):
            pred_rows = _load_json(reports_dir / pred_name)
            route_vals.append(_route_accuracy(dataset_rows, pred_rows))
            latency_vals.append(_avg_latency_ms(pred_rows))
            quality_vals.append(_quality(reports_dir / report_name))

        rows.append(
            {
                "method": spec["name"],
                "route_mean": _m(route_vals),
                "route_std": _s(route_vals),
                "quality_mean": _m(quality_vals),
                "quality_std": _s(quality_vals),
                "latency_mean_ms": _m(latency_vals),
                "latency_std_ms": _s(latency_vals),
                "n_runs": len(route_vals),
            }
        )

    out_json = reports_dir / f"{args.output_prefix}.json"
    out_md = reports_dir / f"{args.output_prefix}.md"
    out_json.write_text(json.dumps({"rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        "# Final Variance Table",
        "",
        "| Method | Route mean | Route std | Quality mean | Quality std | Latency mean (ms) | Latency std (ms) | N runs |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        md_lines.append(
            f"| {row['method']} | {_fmt(row['route_mean'])} | {_fmt(row['route_std'])} | "
            f"{_fmt(row['quality_mean'])} | {_fmt(row['quality_std'])} | "
            f"{row['latency_mean_ms']:.1f} | {row['latency_std_ms']:.1f} | {row['n_runs']} |"
        )
    out_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(f"Saved: {out_json}")
    print(f"Saved: {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
