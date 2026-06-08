from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

VALID_MODEL_CLASSES = ("strong-quality", "balanced", "light-latency")


def _load_rows(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise SystemExit(f"{path} must contain a JSON list.")
    return [dict(item) for item in raw]


def _prediction_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        case_id = str(row.get("id") or "").strip()
        if case_id:
            out[case_id] = dict(row)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare controlled replay datasets from a route-only policy trace.")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--trace", required=True, help="Route-only prediction JSON from the adaptive policy pass.")
    parser.add_argument("--output-dir", default="systems_evaluation")
    parser.add_argument("--prefix", default="test_queries_q2_joint_replay")
    parser.add_argument("--manifest", default="")
    args = parser.parse_args()

    dataset_rows = _load_rows(Path(args.dataset))
    trace_rows = _load_rows(Path(args.trace))
    trace_by_id = _prediction_map(trace_rows)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    by_model: dict[str, list[dict[str, Any]]] = {key: [] for key in VALID_MODEL_CLASSES}
    route_counts = Counter()

    for row in dataset_rows:
        case_id = str(row.get("id") or "").strip()
        trace = trace_by_id.get(case_id)
        if trace is None:
            raise SystemExit(f"Missing policy trace for case id `{case_id}`.")

        selected_class = str(trace.get("model_class") or "").strip()
        if selected_class not in VALID_MODEL_CLASSES:
            raise SystemExit(
                f"Case `{case_id}` has unsupported replay model_class `{selected_class}` in policy trace."
            )

        selected_route = str(trace.get("route") or "").strip()
        if not selected_route:
            raise SystemExit(f"Case `{case_id}` missing route in policy trace.")

        item = dict(row)
        item["replay_selected_route"] = selected_route
        item["replay_model_class"] = selected_class
        item["replay_model_name"] = str(trace.get("model_name") or "")
        item["replay_route_reason"] = str(trace.get("route_reason") or "")
        item["replay_route_score"] = float(trace.get("route_score", 0.0) or 0.0)
        item["replay_route_policy"] = str(trace.get("route_policy") or "controlled_replay_policy_trace")
        item["replay_route_candidates"] = dict(trace.get("route_candidates") or {})
        item["replay_route_features"] = dict(trace.get("route_features") or {})
        item["replay_model_selection_policy"] = str(
            trace.get("model_selection_policy") or "joint_path_model_policy"
        )
        item["replay_direct_answer"] = str(trace.get("direct_answer") or "")
        item["replay_direct_answer_detected"] = bool(trace.get("direct_answer"))
        by_model[selected_class].append(item)
        route_counts[selected_route] += 1

    outputs: dict[str, str] = {}
    model_counts = {model_class: len(rows) for model_class, rows in by_model.items()}
    if sum(model_counts.values()) != len(dataset_rows):
        raise SystemExit("Replay split does not cover the full dataset.")

    for model_class, rows in by_model.items():
        suffix = model_class.replace("-", "_")
        out_path = output_dir / f"{args.prefix}_{suffix}.json"
        out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        outputs[model_class] = str(out_path)
        print(f"Saved {len(rows)} replay cases for {model_class}: {out_path}")

    manifest_payload = {
        "dataset": str(Path(args.dataset)),
        "trace": str(Path(args.trace)),
        "total_cases": len(dataset_rows),
        "model_counts": model_counts,
        "route_counts": dict(route_counts),
        "outputs": outputs,
    }
    manifest_path = Path(args.manifest) if args.manifest else output_dir / f"{args.prefix}_manifest.json"
    manifest_path.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
