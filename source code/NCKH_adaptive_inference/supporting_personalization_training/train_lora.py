from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from supporting_personalization_assets.paths import (
    ensure_personalization_dirs,
    lora_clean_dataset_path,
    lora_dataset_path,
    lora_training_report_path,
    normalize_tenant_id,
    tenant_adapter_dir,
)


def _load_json_records(path: Path) -> int:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    return len(data) if isinstance(data, list) else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a lightweight LoRA adapter for one tenant.")
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--model-name", default="distilgpt2")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--max-length", type=int, default=256)
    args = parser.parse_args()

    tenant_id = normalize_tenant_id(args.tenant_id)
    ensure_personalization_dirs(tenant_id)

    dataset_path = lora_clean_dataset_path(tenant_id)
    if not dataset_path.exists() or _load_json_records(dataset_path) == 0:
        dataset_path = lora_dataset_path(tenant_id)
    if not dataset_path.exists():
        raise SystemExit(f"Training dataset not found: {dataset_path}")

    from datasets import load_dataset
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments

    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(args.model_name)
    model.resize_token_embeddings(len(tokenizer))

    dataset = load_dataset("json", data_files={"train": str(dataset_path)})

    def format_example(example):
        text = f"### Instruction:\n{example['instruction']}\n\n### Response:\n{example['output']}"
        return {"text": text}

    def tokenize(example):
        tokens = tokenizer(
            example["text"],
            truncation=True,
            padding="max_length",
            max_length=args.max_length,
        )
        tokens["labels"] = list(tokens["input_ids"])
        return tokens

    dataset = dataset.map(format_example)
    dataset = dataset.map(tokenize, batched=True)

    lora_config = LoraConfig(
        r=4,
        lora_alpha=16,
        target_modules=["c_attn"],
        lora_dropout=0.1,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)

    adapter_dir = tenant_adapter_dir(tenant_id)
    training_args = TrainingArguments(
        output_dir=str(adapter_dir),
        per_device_train_batch_size=args.batch_size,
        num_train_epochs=args.epochs,
        logging_steps=1,
        save_steps=5,
        learning_rate=2e-4,
        remove_unused_columns=False,
        report_to=[],
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset["train"],
    )
    trainer.train()
    model.save_pretrained(str(adapter_dir))

    report_path = lora_training_report_path(tenant_id)
    report_path.write_text(
        "\n".join(
            [
                f"# LoRA Training Report - {tenant_id}",
                "",
                f"- model_name: `{args.model_name}`",
                f"- dataset_path: `{dataset_path}`",
                f"- sample_count: `{_load_json_records(dataset_path)}`",
                f"- epochs: `{args.epochs}`",
                f"- batch_size: `{args.batch_size}`",
                f"- adapter_dir: `{adapter_dir}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Tenant: {tenant_id}")
    print(f"Dataset: {dataset_path}")
    print(f"Adapter saved: {adapter_dir}")
    print(f"Report saved: {report_path}")


if __name__ == "__main__":
    main()
