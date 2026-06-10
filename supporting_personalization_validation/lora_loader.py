from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from supporting_personalization_assets.paths import normalize_tenant_id, tenant_adapter_dir


def load_model_with_lora(tenant_id: str, model_name: str = "distilgpt2"):
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tenant_id = normalize_tenant_id(tenant_id)
    adapter_path = tenant_adapter_dir(tenant_id)
    if not adapter_path.exists():
        raise FileNotFoundError(f"Adapter for tenant `{tenant_id}` was not found at {adapter_path}")

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    tokenizer.pad_token = tokenizer.eos_token

    base_model = AutoModelForCausalLM.from_pretrained(model_name)
    model = PeftModel.from_pretrained(base_model, str(adapter_path))
    return model, tokenizer
