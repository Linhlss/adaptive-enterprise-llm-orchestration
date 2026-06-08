from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from enterprise_runtime.config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    DEFAULT_DOMAIN_ID,
    DEFAULT_DOMAIN_NAME,
    DEFAULT_ENABLE_HYBRID_RETRIEVAL,
    DEFAULT_ENABLE_QUERY_EXPANSION,
    DEFAULT_ENABLE_RERANKER,
    DEFAULT_HYBRID_ALPHA,
    DEFAULT_MODEL_CLASS,
    DEFAULT_MODEL_NAME,
    DEFAULT_QUERY_EXPANSION_COUNT,
    DEFAULT_RERANKER_TOP_N,
    DEFAULT_TOP_K,
    LLM_BACKEND,
)


@dataclass
class TenantProfile:
    tenant_id: str
    display_name: str
    persona: str
    domain_id: str = DEFAULT_DOMAIN_ID
    domain_name: str = DEFAULT_DOMAIN_NAME
    language_hint: str = "Automatically follow the question language"
    top_k: int = DEFAULT_TOP_K
    memory_turns: int = 6
    model_name: str = DEFAULT_MODEL_NAME
    shared_model_name: str = DEFAULT_MODEL_NAME
    model_class: str = DEFAULT_MODEL_CLASS
    llm_backend: str = LLM_BACKEND
    adapter_name: str = "base"
    enable_personalization: bool = False
    fixed_route_mode: str = "adaptive"
    chunk_size: int = CHUNK_SIZE
    chunk_overlap: int = CHUNK_OVERLAP
    enable_query_expansion: bool = DEFAULT_ENABLE_QUERY_EXPANSION
    enable_hybrid_retrieval: bool = DEFAULT_ENABLE_HYBRID_RETRIEVAL
    enable_reranker: bool = DEFAULT_ENABLE_RERANKER
    query_expansion_count: int = DEFAULT_QUERY_EXPANSION_COUNT
    hybrid_alpha: float = DEFAULT_HYBRID_ALPHA
    reranker_top_n: int = DEFAULT_RERANKER_TOP_N


@dataclass
class TenantRuntime:
    profile: TenantProfile
    index: Any
    retriever: Any
    storage_dir: Path
    chroma_dir: Path
    collection_name: str
    data_signature: str
    loaded_at: str
    document_count: int
    node_count: int


@dataclass
class WorkflowTrace:
    route: str
    route_reason: str
    route_score: float
    route_features: dict[str, Any]
    route_candidates: dict[str, float]
    route_mode: str
    route_policy: str
    used_adapter: str
    adapter_enabled: bool
    adapter_available: bool
    adapter_path: str | None
    shared_model_name: str
    model_name: str
    model_class: str
    model_selection_policy: str
    llm_backend: str
    retrieved_context: str | None = None
    retrieved_sources: list[str] | None = None
