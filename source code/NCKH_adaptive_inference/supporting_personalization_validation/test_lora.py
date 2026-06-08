from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from supporting_personalization_validation.lora_loader import load_model_with_lora


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test a tenant LoRA adapter.")
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--prompt", default="What is the company leave policy?")
    parser.add_argument("--max-new-tokens", type=int, default=50)
    args = parser.parse_args()

    model, tokenizer = load_model_with_lora(args.tenant_id)
    inputs = tokenizer(args.prompt, return_tensors="pt")
    outputs = model.generate(**inputs, max_new_tokens=args.max_new_tokens)
    response = tokenizer.decode(outputs[0], skip_special_tokens=True)

    print(f"Tenant: {args.tenant_id}")
    print(f"Prompt: {args.prompt}")
    print(f"Response: {response}")


if __name__ == "__main__":
    main()
