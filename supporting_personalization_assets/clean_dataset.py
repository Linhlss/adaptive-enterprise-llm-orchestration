from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from supporting_personalization_assets.paths import ensure_personalization_dirs, lora_clean_dataset_path, lora_dataset_path, normalize_tenant_id


def clean_dataset(input_path: Path, output_path: Path) -> tuple[int, int]:
    with input_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    cleaned = []
    for item in data:
        instruction = str(item.get("instruction", "")).strip()
        output = str(item.get("output", "")).strip()

        if not instruction or not output:
            continue
        if len(output) < 3:
            continue
        if "unclear" in output.lower():
            continue

        cleaned.append(
            {
                "instruction": instruction,
                "input": str(item.get("input", "")).strip(),
                "output": output,
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(data), len(cleaned)


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean a tenant-specific LoRA dataset.")
    parser.add_argument("--tenant-id", default="default")
    args = parser.parse_args()

    tenant_id = normalize_tenant_id(args.tenant_id)
    ensure_personalization_dirs(tenant_id)

    input_path = lora_dataset_path(tenant_id)
    output_path = lora_clean_dataset_path(tenant_id)
    if not input_path.exists():
        raise SystemExit(f"Raw dataset not found: {input_path}")

    before, after = clean_dataset(input_path, output_path)
    print(f"Tenant: {tenant_id}")
    print(f"Before: {before} samples")
    print(f"After: {after} samples")
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
