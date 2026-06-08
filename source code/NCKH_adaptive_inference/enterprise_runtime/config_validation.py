from __future__ import annotations

from typing import Dict, List, Tuple

from enterprise_runtime.config import load_tenant_configs

ALLOWED_MODEL_CLASSES = {"strong-quality", "balanced", "light-latency", "adaptive", "custom"}
ALLOWED_LLM_BACKENDS = {"ollama", "vllm"}

REQUIRED_TENANT_KEYS = {
    "display_name",
    "domain_id",
    "domain_name",
    "persona",
    "language_hint",
    "top_k",
    "chunk_size",
    "chunk_overlap",
    "memory_turns",
    "model_name",
    "shared_model_name",
    "model_class",
    "llm_backend",
    "adapter_name",
    "enable_query_expansion",
    "enable_hybrid_retrieval",
    "enable_reranker",
    "query_expansion_count",
    "hybrid_alpha",
    "reranker_top_n",
}


def validate_tenant_configs() -> Tuple[bool, Dict[str, List[str]]]:
    configs = load_tenant_configs()
    issues: Dict[str, List[str]] = {}

    if "default" not in configs:
        issues["__global__"] = ["Missing default tenant profile."]

    for tenant_id, raw in configs.items():
        tenant_issues: List[str] = []
        missing = [key for key in sorted(REQUIRED_TENANT_KEYS) if key not in raw]
        if missing:
            tenant_issues.append(f"Missing keys: {', '.join(missing)}")
        model_class = str(raw.get("model_class", "")).strip()
        if model_class and model_class not in ALLOWED_MODEL_CLASSES:
            tenant_issues.append(f"Unsupported model_class: {model_class}")
        llm_backend = str(raw.get("llm_backend", "")).strip()
        if llm_backend and llm_backend not in ALLOWED_LLM_BACKENDS:
            tenant_issues.append(f"Unsupported llm_backend: {llm_backend}")
        if tenant_issues:
            issues[tenant_id] = tenant_issues

    return (len(issues) == 0), issues
