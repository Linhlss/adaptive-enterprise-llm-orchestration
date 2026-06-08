from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
TENANT_CONFIG = BASE_DIR / "config" / "tenants.json"
TENANTS_DIR = BASE_DIR / "data" / "tenants"

DOMAIN_TEMPLATES = {
    "academic_admin": {
        "name": "Academic and administrative support",
        "tenants": ["academic_registrar", "academic_department"],
        "persona": "You are an academic and administrative document assistant. Answer using regulations, forms, schedules, and internal notices.",
    },
    "hr_policy": {
        "name": "HR and internal policy support",
        "tenants": ["hr_people_ops", "hr_compliance"],
        "persona": "You are an HR document assistant. Answer using leave policies, onboarding materials, benefits information, and internal procedures.",
    },
    "ops_compliance": {
        "name": "Operations and compliance support",
        "tenants": ["ops_procurement", "ops_quality"],
        "persona": "You are an operations and compliance document assistant. Answer using SOPs, checklists, procurement flows, and compliance materials.",
    },
}


def _load_configs() -> dict[str, dict[str, Any]]:
    if not TENANT_CONFIG.exists():
        return {}
    raw = json.loads(TENANT_CONFIG.read_text(encoding="utf-8"))
    return {str(k): dict(v) for k, v in raw.items()}


def _base_profile(domain_id: str, domain_name: str, tenant_id: str, persona: str) -> dict[str, Any]:
    return {
        "display_name": tenant_id.replace("_", " ").title(),
        "domain_id": domain_id,
        "domain_name": domain_name,
        "q2_domain_pack": True,
        "persona": persona,
        "language_hint": "Automatically follow the question language",
        "top_k": 4,
        "chunk_size": 500,
        "chunk_overlap": 80,
        "memory_turns": 6,
        "model_name": "Qwen/Qwen3-4B-AWQ",
        "shared_model_name": "Qwen/Qwen3-4B-AWQ",
        "model_class": "adaptive",
        "llm_backend": "vllm",
        "adapter_name": "base",
        "enable_query_expansion": True,
        "enable_hybrid_retrieval": False,
        "enable_reranker": False,
        "query_expansion_count": 4,
        "hybrid_alpha": 0.55,
        "reranker_top_n": 8,
    }


def _ensure_tenant_dirs(tenant_id: str) -> None:
    root = TENANTS_DIR / tenant_id
    (root / "files").mkdir(parents=True, exist_ok=True)
    links = root / "links.txt"
    if not links.exists():
        links.write_text("", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create Q2 domain tenant scaffolding without generating benchmark evidence."
    )
    parser.add_argument("--apply", action="store_true", help="Write config/tenant directories. Without this flag, dry-run only.")
    parser.add_argument("--force", action="store_true", help="Refresh existing Q2 tenant configs to the current source-of-truth defaults.")
    args = parser.parse_args()

    configs = _load_configs()
    planned: dict[str, dict[str, Any]] = {}
    for domain_id, domain in DOMAIN_TEMPLATES.items():
        for tenant_id in domain["tenants"]:
            planned[tenant_id] = _base_profile(
                domain_id=domain_id,
                domain_name=str(domain["name"]),
                tenant_id=tenant_id,
                persona=str(domain["persona"]),
            )

    existing = sorted(set(configs) & set(planned))
    missing = sorted(set(planned) - set(configs))
    print(f"Q2 scaffold tenants missing={missing}")
    if existing:
        action = "will be refreshed" if args.force else "will not be overwritten"
        print(f"Existing tenant ids {action}: {existing}")

    if not args.apply:
        print("Dry-run only. Re-run with --apply to create missing tenant configs and directories.")
        return 0

    target_ids = sorted(set(missing) | (set(existing) if args.force else set()))
    for tenant_id in target_ids:
        configs[tenant_id] = planned[tenant_id]
        _ensure_tenant_dirs(tenant_id)

    TENANT_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    TENANT_CONFIG.write_text(json.dumps(configs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Created/refreshed {len(target_ids)} tenant scaffolds. "
        "Add real corpus files under data/tenants/<tenant_id>/files/."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
