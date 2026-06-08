from __future__ import annotations

import argparse
import sys
from pathlib import Path

from segment import load_documents, segment_documents
from qa_generator import generate_dataset, save_dataset
from export_dataset import export_lora_format


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from supporting_personalization_assets.paths import ensure_personalization_dirs, generated_qa_path, lora_dataset_path, normalize_tenant_id, tenant_source_dir


def run(tenant_id: str = "default") -> None:
    tenant_id = normalize_tenant_id(tenant_id)
    ensure_personalization_dirs(tenant_id)
    source_dir = tenant_source_dir(tenant_id)
    generated_path = generated_qa_path(tenant_id)
    lora_path = lora_dataset_path(tenant_id)

    print(f"Tenant: {tenant_id}")
    print(f"Source dir: {source_dir}")
    print("1. Loading documents...")
    docs = load_documents(str(source_dir))

    print("2. Segmenting...")
    chunks = segment_documents(docs)
    print(f"Chunks created: {len(chunks)}")

    print("3. Generating QA...")
    dataset = generate_dataset(chunks)
    save_dataset(dataset, str(generated_path))
    print(f"Saved generated QA: {generated_path}")

    print("4. Exporting LoRA dataset...")
    export_lora_format(str(generated_path), str(lora_path))
    print(f"Saved LoRA dataset: {lora_path}")
    print("DONE!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Pipeline 1 for a specific tenant.")
    parser.add_argument("--tenant-id", default="default")
    args = parser.parse_args()
    run(args.tenant_id)
