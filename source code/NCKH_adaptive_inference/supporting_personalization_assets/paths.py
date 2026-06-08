from __future__ import annotations

import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
PERSONALIZATION_DIR = BASE_DIR / "supporting_personalization_assets"
DATA_DIR = PERSONALIZATION_DIR / "data"
DATASETS_DIR = PERSONALIZATION_DIR / "datasets"
ADAPTERS_DIR = PERSONALIZATION_DIR / "adapters"
REPORTS_DIR = PERSONALIZATION_DIR / "reports"


def normalize_tenant_id(raw: str) -> str:
    normalized = re.sub(r"[^a-z0-9_]+", "_", (raw or "").lower()).strip("_")
    return normalized or "default"


def tenant_source_dir(tenant_id: str) -> Path:
    return DATA_DIR / normalize_tenant_id(tenant_id) / "files"


def tenant_dataset_dir(tenant_id: str) -> Path:
    return DATASETS_DIR / normalize_tenant_id(tenant_id)


def tenant_adapter_dir(tenant_id: str) -> Path:
    return ADAPTERS_DIR / normalize_tenant_id(tenant_id)


def tenant_report_dir(tenant_id: str) -> Path:
    return REPORTS_DIR / normalize_tenant_id(tenant_id)


def generated_qa_path(tenant_id: str) -> Path:
    return tenant_dataset_dir(tenant_id) / "generated_qa.json"


def validated_qa_path(tenant_id: str) -> Path:
    return tenant_dataset_dir(tenant_id) / "generated_qa_validated.json"


def lora_dataset_path(tenant_id: str) -> Path:
    return tenant_dataset_dir(tenant_id) / "lora_dataset.json"


def lora_clean_dataset_path(tenant_id: str) -> Path:
    return tenant_dataset_dir(tenant_id) / "lora_dataset_clean.json"


def lora_training_report_path(tenant_id: str) -> Path:
    return tenant_report_dir(tenant_id) / "lora_training_report.md"


def ensure_personalization_dirs(tenant_id: str) -> None:
    tenant_source_dir(tenant_id).mkdir(parents=True, exist_ok=True)
    tenant_dataset_dir(tenant_id).mkdir(parents=True, exist_ok=True)
    tenant_adapter_dir(tenant_id).mkdir(parents=True, exist_ok=True)
    tenant_report_dir(tenant_id).mkdir(parents=True, exist_ok=True)
