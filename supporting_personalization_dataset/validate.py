from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from supporting_personalization_assets.paths import ensure_personalization_dirs, generated_qa_path, normalize_tenant_id, validated_qa_path


def validate_dataset(input_path: Path, output_path: Path) -> None:
    with input_path.open(encoding="utf-8") as handle:
        data = json.load(handle)

    validated = []
    for item in data:
        print("\n----------------------")
        print("Q:", item["question"])
        print("A:", item["answer"])

        ok = input("Keep? (y/n): ")
        if ok.lower() == "y":
            validated.append(item)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(validated, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Validated: {len(validated)} / {len(data)}")
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manual validation for generated QA by tenant.")
    parser.add_argument("--tenant-id", default="default")
    args = parser.parse_args()

    tenant_id = normalize_tenant_id(args.tenant_id)
    ensure_personalization_dirs(tenant_id)
    validate_dataset(generated_qa_path(tenant_id), validated_qa_path(tenant_id))
