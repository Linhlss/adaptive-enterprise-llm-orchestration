from __future__ import annotations

import logging
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from llama_index.llms.ollama import Ollama

from enterprise_runtime.config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    DEFAULT_DOMAIN_ID,
    DEFAULT_DOMAIN_NAME,
    DEFAULT_ENABLE_HYBRID_RETRIEVAL,
    DEFAULT_ENABLE_PERSONALIZATION,
    DEFAULT_ENABLE_QUERY_EXPANSION,
    DEFAULT_ENABLE_RERANKER,
    DEFAULT_FIXED_ROUTE_MODE,
    DEFAULT_HYBRID_ALPHA,
    DEFAULT_MODEL_CLASS,
    DEFAULT_MODEL_NAME,
    DEFAULT_QUERY_EXPANSION_COUNT,
    DEFAULT_RERANKER_TOP_N,
    DEFAULT_SHARED_MODEL_NAME,
    DEFAULT_TOP_K,
    ALLOW_VLLM_ONLINE_JOINT_MODEL_SELECTION,
    OLLAMA_BASE_URL,
    OLLAMA_TIMEOUT,
    LLM_BACKEND,
    LLM_MAX_RETRIES,
    LLM_NUM_PREDICT,
    LLM_RETRY_DELAY,
    LLM_TIMEOUT,
    LLM_TEMPERATURE,
    LLM_TOP_P,
    OLLAMA_QWEN3_4B_MODEL,
    OLLAMA_QWEN3_8B_MODEL,
    OLLAMA_QWEN3_14B_MODEL,
    VLLM_API_KEY,
    VLLM_BASE_URL,
    VLLM_QWEN3_4B_MODEL,
    VLLM_QWEN3_8B_MODEL,
    VLLM_QWEN3_14B_MODEL,
    load_tenant_configs,
    save_tenant_configs,
)
from enterprise_runtime.models import TenantProfile
from supporting_personalization_assets.paths import tenant_adapter_dir
from enterprise_runtime.utils import check_ollama_alive, sanitize_id

logger = logging.getLogger(__name__)

LLM_CACHE: Dict[tuple[str, str], Any] = {}
_COMPLETE_KWARGS: Dict[str, object] = {}

_MODEL_CLASS_ALIASES = {
    "strong": "strong-quality",
    "strong-quality": "strong-quality",
    "strong_quality": "strong-quality",
    "qwen3-14b-awq": "strong-quality",
    "qwen3-14b": "strong-quality",
    "14b": "strong-quality",
    "balanced": "balanced",
    "qwen3-8b-awq": "balanced",
    "qwen3-8b": "balanced",
    "8b": "balanced",
    "light": "light-latency",
    "light-latency": "light-latency",
    "light_latency": "light-latency",
    "qwen3-4b-awq": "light-latency",
    "qwen3-4b": "light-latency",
    "4b": "light-latency",
    "adaptive": "adaptive",
    "joint": "adaptive",
    "joint-adaptive": "adaptive",
    "joint_adaptive": "adaptive",
    "custom": "custom",
}


@dataclass(frozen=True)
class ModelSelection:
    backend: str
    model_name: str
    model_class: str
    selection_policy: str


@dataclass
class _Completion:
    text: str


class OpenAICompatibleLLM:
    """Minimal client for vLLM's OpenAI-compatible chat completions API."""

    def __init__(self, model: str, base_url: str, api_key: str, timeout: float) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = "" if (api_key or "").strip().upper() == "EMPTY" else (api_key or "")
        self.timeout = timeout

    def complete(self, prompt: str, **_: object) -> _Completion:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": LLM_TEMPERATURE,
            "top_p": LLM_TOP_P,
        }
        if LLM_NUM_PREDICT > 0:
            payload["max_tokens"] = LLM_NUM_PREDICT

        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        endpoint = (
            f"{self.base_url}/chat/completions"
            if self.base_url.endswith("/v1")
            else f"{self.base_url}/v1/chat/completions"
        )
        request = Request(
            endpoint,
            data=data,
            headers=headers,
            method="POST",
        )
        with urlopen(request, timeout=self.timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        choice = (body.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        text = message.get("content") or choice.get("text") or ""
        return _Completion(str(text).strip())


def _build_ollama_options() -> Dict[str, object]:
    options: Dict[str, object] = {
        "temperature": LLM_TEMPERATURE,
        "top_p": LLM_TOP_P,
    }
    if LLM_NUM_PREDICT > 0:
        options["num_predict"] = LLM_NUM_PREDICT
    return options


def normalize_model_class(value: str | None) -> str:
    raw = (value or DEFAULT_MODEL_CLASS or "light-latency").strip().lower()
    return _MODEL_CLASS_ALIASES.get(raw, raw)


def normalize_backend(value: str | None) -> str:
    raw = (value or LLM_BACKEND or "ollama").strip().lower()
    if raw in {"vllm", "openai", "openai-compatible", "openai_compatible"}:
        return "vllm"
    return "ollama"


def _qwen_model_for_class(backend: str, model_class: str) -> str:
    if backend == "vllm":
        mapping = {
            "strong-quality": VLLM_QWEN3_14B_MODEL,
            "balanced": VLLM_QWEN3_8B_MODEL,
            "light-latency": VLLM_QWEN3_4B_MODEL,
        }
    else:
        mapping = {
            "strong-quality": OLLAMA_QWEN3_14B_MODEL,
            "balanced": OLLAMA_QWEN3_8B_MODEL,
            "light-latency": OLLAMA_QWEN3_4B_MODEL,
        }
    return mapping.get(model_class, mapping["light-latency"])


def _adaptive_model_class(profile: TenantProfile, route_result=None, question: str | None = None) -> str:
    route = getattr(route_result, "route", "") or ""
    features = getattr(route_result, "features", None) or {}
    score = float(getattr(route_result, "score", 0.0) or 0.0)
    word_count = int(features.get("word_count", len((question or "").split())) or 0)

    if route == "retrieval":
        if score < 0.55 or word_count >= 18:
            return "strong-quality"
        return "balanced"
    if route == "tool":
        return "balanced"
    if route == "general":
        return "light-latency"
    if route == "out_of_scope":
        return "light-latency"
    configured_class = normalize_model_class(profile.model_class)
    if configured_class == "adaptive":
        return "light-latency"
    return configured_class


def resolve_model_selection(
    profile: TenantProfile,
    route_result=None,
    question: str | None = None,
) -> ModelSelection:
    backend = normalize_backend(profile.llm_backend)
    requested_class = normalize_model_class(profile.model_class)

    if requested_class == "custom":
        model_name = profile.shared_model_name or profile.model_name or DEFAULT_SHARED_MODEL_NAME
        return ModelSelection(
            backend=backend,
            model_name=model_name,
            model_class="custom",
            selection_policy="custom_profile_model",
        )

    if requested_class == "adaptive":
        selected_class = _adaptive_model_class(profile, route_result=route_result, question=question)
        return ModelSelection(
            backend=backend,
            model_name=_qwen_model_for_class(backend, selected_class),
            model_class=selected_class,
            selection_policy="joint_path_model_policy",
        )

    selected_class = requested_class if requested_class in {"strong-quality", "balanced", "light-latency"} else DEFAULT_MODEL_CLASS
    return ModelSelection(
        backend=backend,
        model_name=_qwen_model_for_class(backend, selected_class),
        model_class=selected_class,
        selection_policy="fixed_model_class",
    )


def _as_bool(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def get_or_create_profile(tenant_id: str) -> TenantProfile:
    tenant_id = sanitize_id(tenant_id, "default")
    configs = load_tenant_configs()

    if tenant_id not in configs:
        configs[tenant_id] = configs.get("default", {}).copy()
        configs[tenant_id]["display_name"] = tenant_id.replace("_", " ").title()
        save_tenant_configs(configs)

    raw = configs[tenant_id]
    return TenantProfile(
        tenant_id=tenant_id,
        display_name=raw.get("display_name", tenant_id),
        persona=raw.get("persona", ""),
        domain_id=raw.get("domain_id", DEFAULT_DOMAIN_ID),
        domain_name=raw.get("domain_name", DEFAULT_DOMAIN_NAME),
        language_hint=raw.get("language_hint", "Auto"),
        top_k=int(raw.get("top_k", DEFAULT_TOP_K)),
        memory_turns=int(raw.get("memory_turns", 6)),
        model_name=raw.get("model_name", DEFAULT_MODEL_NAME),
        shared_model_name=raw.get("shared_model_name", raw.get("model_name", DEFAULT_SHARED_MODEL_NAME)),
        model_class=raw.get("model_class", DEFAULT_MODEL_CLASS),
        llm_backend=raw.get("llm_backend", LLM_BACKEND),
        adapter_name=raw.get("adapter_name", "base"),
        enable_personalization=_as_bool(raw.get("enable_personalization"), DEFAULT_ENABLE_PERSONALIZATION),
        fixed_route_mode=str(raw.get("fixed_route_mode", DEFAULT_FIXED_ROUTE_MODE) or DEFAULT_FIXED_ROUTE_MODE).lower(),
        chunk_size=int(raw.get("chunk_size", CHUNK_SIZE)),
        chunk_overlap=int(raw.get("chunk_overlap", CHUNK_OVERLAP)),
        enable_query_expansion=_as_bool(raw.get("enable_query_expansion"), DEFAULT_ENABLE_QUERY_EXPANSION),
        enable_hybrid_retrieval=_as_bool(raw.get("enable_hybrid_retrieval"), DEFAULT_ENABLE_HYBRID_RETRIEVAL),
        enable_reranker=_as_bool(raw.get("enable_reranker"), DEFAULT_ENABLE_RERANKER),
        query_expansion_count=int(raw.get("query_expansion_count", DEFAULT_QUERY_EXPANSION_COUNT)),
        hybrid_alpha=float(raw.get("hybrid_alpha", DEFAULT_HYBRID_ALPHA)),
        reranker_top_n=int(raw.get("reranker_top_n", DEFAULT_RERANKER_TOP_N)),
    )


def resolve_personalization_state(
    profile: TenantProfile,
    route_result=None,
    question: str | None = None,
) -> Dict[str, object]:
    adapter_name = (profile.adapter_name or "base").strip() or "base"
    adapter_enabled = bool(profile.enable_personalization and adapter_name != "base")
    adapter_path = tenant_adapter_dir(profile.tenant_id) if adapter_enabled else None
    adapter_available = bool(adapter_path and adapter_path.exists())

    selection = resolve_model_selection(profile, route_result=route_result, question=question)
    return {
        "shared_model_name": selection.model_name,
        "model_name": selection.model_name,
        "model_class": selection.model_class,
        "llm_backend": selection.backend,
        "model_selection_policy": selection.selection_policy,
        "adapter_name": adapter_name,
        "adapter_enabled": adapter_enabled,
        "adapter_available": adapter_available,
        "adapter_path": (str(adapter_path) if adapter_path else None),
        "runtime_mode": (
            "base_plus_lora"
            if adapter_enabled and adapter_available
            else "base_fallback"
            if adapter_enabled
            else "base_only"
        ),
    }


def get_llm(model_name: str, backend: str | None = None):
    backend = normalize_backend(backend)
    cache_key = (backend, model_name)
    if cache_key not in LLM_CACHE:
        options = _build_ollama_options()
        if backend == "vllm":
            LLM_CACHE[cache_key] = OpenAICompatibleLLM(
                model=model_name,
                base_url=VLLM_BASE_URL,
                api_key=VLLM_API_KEY,
                timeout=LLM_TIMEOUT,
            )
        else:
            try:
                LLM_CACHE[cache_key] = Ollama(
                    model=model_name,
                    request_timeout=OLLAMA_TIMEOUT,
                    base_url=OLLAMA_BASE_URL,
                    additional_kwargs={"options": options},
                )
                _COMPLETE_KWARGS.clear()
            except TypeError:
                # Fallback for older llama-index Ollama wrappers.
                LLM_CACHE[cache_key] = Ollama(
                    model=model_name,
                    request_timeout=OLLAMA_TIMEOUT,
                    base_url=OLLAMA_BASE_URL,
                )
                _COMPLETE_KWARGS.clear()
                _COMPLETE_KWARGS["options"] = options
    return LLM_CACHE[cache_key]


def get_llm_for_profile(profile: TenantProfile, route_result=None, question: str | None = None):
    selection = resolve_model_selection(profile, route_result=route_result, question=question)
    if (
        selection.backend == "vllm"
        and selection.selection_policy == "joint_path_model_policy"
        and not ALLOW_VLLM_ONLINE_JOINT_MODEL_SELECTION
    ):
        raise RuntimeError(
            "Online adaptive model-tier selection on a single vLLM endpoint is disabled by default. "
            "Use the controlled replay benchmark pipeline, or set "
            "ALLOW_VLLM_ONLINE_JOINT_MODEL_SELECTION=true only for a separately validated deployment."
        )
    logger.info(
        "LLM runtime selected tenant=%s backend=%s model=%s model_class=%s policy=%s",
        profile.tenant_id,
        selection.backend,
        selection.model_name,
        selection.model_class,
        selection.selection_policy,
    )
    return get_llm(selection.model_name, backend=selection.backend)


def complete_with_retry(llm, prompt: str) -> str:
    last_error: Optional[Exception] = None

    for attempt in range(LLM_MAX_RETRIES + 1):
        try:
            try:
                response = llm.complete(prompt, **_COMPLETE_KWARGS)
            except TypeError:
                response = llm.complete(prompt)
            return str(response.text).strip()
        except Exception as exc:
            last_error = exc
            logger.warning(
                "LLM call failed (attempt %s/%s): %s",
                attempt + 1,
                LLM_MAX_RETRIES + 1,
                exc,
            )
            if attempt < LLM_MAX_RETRIES:
                time.sleep(LLM_RETRY_DELAY)

    raise RuntimeError(f"The LLM backend failed after multiple retries: {last_error}")


def draft_answer(llm, prompt: str) -> str:
    return complete_with_retry(llm, prompt)


def rewrite_query(llm, prompt: str) -> str:
    return complete_with_retry(llm, prompt)


def verify_answer(llm, prompt: str) -> str:
    return complete_with_retry(llm, prompt)


def rewrite_style(llm, prompt: str) -> str:
    return complete_with_retry(llm, prompt)


def check_llm_backend_alive() -> bool:
    backend = normalize_backend(LLM_BACKEND)
    if backend == "ollama":
        parsed = urlparse(OLLAMA_BASE_URL)
    else:
        parsed = urlparse(VLLM_BASE_URL)
    host = parsed.hostname or "127.0.0.1"
    port = int(parsed.port or (443 if parsed.scheme == "https" else 80))
    return check_ollama_alive(host=host, port=port)
