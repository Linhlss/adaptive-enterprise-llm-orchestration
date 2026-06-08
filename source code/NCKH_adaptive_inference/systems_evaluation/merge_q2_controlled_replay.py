from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_rows(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise SystemExit(f"{path} must contain a JSON list.")
    return [dict(item) for item in raw]


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge controlled replay prediction shards into one benchmark artifact.")
    parser.add_argument("--dataset", required=True, help="Original full dataset used for policy pass ordering.")
    parser.add_argument("--predictions", nargs="+", required=True, help="Prediction JSON files from replay passes.")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    dataset_rows = _load_rows(Path(args.dataset))
    pred_map: dict[str, dict[str, Any]] = {}
    for value in args.predictions:
        for row in _load_rows(Path(value)):
            case_id = str(row.get("id") or "").strip()
            if not case_id:
                raise SystemExit(f"Prediction row without id found in {value}.")
            if case_id in pred_map:
                raise SystemExit(f"Duplicate replay prediction for case id `{case_id}`.")
            pred_map[case_id] = dict(row)

    merged: list[dict[str, Any]] = []
    missing: list[str] = []
    for row in dataset_rows:
        case_id = str(row.get("id") or "").strip()
        pred = pred_map.get(case_id)
        if pred is None:
            missing.append(case_id)
            continue
        merged.append(pred)

    extras = sorted(set(pred_map) - {str(row.get("id") or "").strip() for row in dataset_rows})
    if missing:
        raise SystemExit(f"Missing replay predictions for ids: {missing[:10]}{'...' if len(missing) > 10 else ''}")
    if extras:
        raise SystemExit(f"Replay predictions contain unexpected ids: {extras[:10]}{'...' if len(extras) > 10 else ''}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved merged replay predictions: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

