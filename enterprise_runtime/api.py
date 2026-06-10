from __future__ import annotations

from dataclasses import replace
import logging
import time
from typing import Optional

from fastapi import FastAPI, HTTPException

from enterprise_runtime.config import (
    ALLOW_API_FIXED_ROUTE_OVERRIDE,
    bootstrap_dirs,
    ensure_default_config,
    init_embedding_settings,
    load_tenant_configs,
)
from enterprise_runtime.config_validation import validate_tenant_configs
from enterprise_runtime.llm_service import get_or_create_profile
from enterprise_runtime.router import route_question
from enterprise_runtime.schemas import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    HealthResponse,
    MemoryResetRequest,
    MessageResponse,
    RefreshRequest,
    SourceItem,
    StatusResponse,
    TenantItem,
    TenantsResponse,
)
from enterprise_runtime.api_helpers import infer_mode_from_route, parse_sources_from_answer, runtime_status_payload
from enterprise_runtime.workflow import run_workflow_with_trace
from enterprise_runtime.memory_store import MemoryStore
from enterprise_runtime.runtime_manager import build_runtime

app = FastAPI(title="Multi-tenant RAG API", version="v1")
logger = logging.getLogger(__name__)


@app.on_event("startup")
def startup_event() -> None:
    bootstrap_dirs()
    ensure_default_config()
    init_embedding_settings()
    is_valid, issues = validate_tenant_configs()
    if not is_valid:
        logger.warning("Tenant config consistency warnings: %s", issues)
    else:
        logger.info("Tenant config consistency check passed.")
    logger.info("FastAPI startup completed: directories were bootstrapped and embedding settings were initialized.")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="multi-tenant-rag", version="v1")


@app.get("/tenants", response_model=TenantsResponse)
def list_tenants() -> TenantsResponse:
    configs = load_tenant_configs()
    items = []
    for tenant_id, raw in configs.items():
        items.append(
            TenantItem(
                tenant_id=tenant_id,
                display_name=raw.get("display_name", tenant_id),
                language_hint=raw.get("language_hint", "Auto"),
                has_adapter=(raw.get("adapter_name", "base") != "base"),
            )
        )
    return TenantsResponse(tenants=items)


@app.post("/chat", response_model=ChatResponse, responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
def chat(req: ChatRequest) -> ChatResponse:
    started = time.perf_counter()
    try:
        profile = get_or_create_profile(req.tenant_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail={"status": "error", "error_code": "TENANT_NOT_FOUND", "message": str(exc)})

    try:
        if req.fixed_route_mode:
            if not ALLOW_API_FIXED_ROUTE_OVERRIDE:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "status": "error",
                        "error_code": "FIXED_ROUTE_OVERRIDE_DISABLED",
                        "message": "fixed_route_mode is reserved for benchmark/ablation. Set ALLOW_API_FIXED_ROUTE_OVERRIDE=true to enable manually.",
                    },
                )
            profile = replace(profile, fixed_route_mode=req.fixed_route_mode)
        route_result = route_question(req.message, profile, req.user_id)
        answer, trace = run_workflow_with_trace(
            profile=profile,
            user_id=req.user_id,
            question=req.message,
            show_sources=req.show_sources,
            route_result=route_result,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        sources = parse_sources_from_answer(answer)
        return ChatResponse(
            status="ok",
            answer=answer,
            route=trace.route,
            mode=infer_mode_from_route(trace.route),
            tenant_id=req.tenant_id,
            user_id=req.user_id,
            sources=sources,
            metadata={
                "latency_ms": latency_ms,
                "domain_id": profile.domain_id,
                "domain_name": profile.domain_name,
                "used_adapter": trace.used_adapter,
                "route_reason": trace.route_reason,
                "route_score": trace.route_score,
                "route_features": trace.route_features,
                "route_candidates": trace.route_candidates,
                "route_mode": trace.route_mode,
                "route_policy": trace.route_policy,
                "shared_model_name": trace.shared_model_name,
                "model_name": trace.model_name,
                "model_class": trace.model_class,
                "llm_backend": trace.llm_backend,
                "adapter_enabled": trace.adapter_enabled,
                "adapter_available": trace.adapter_available,
                "adapter_path": trace.adapter_path,
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "error_code": "INTERNAL_ERROR",
                "message": str(exc),
            },
        )


@app.post("/memory/reset", response_model=MessageResponse, responses={500: {"model": ErrorResponse}})
def memory_reset(req: MemoryResetRequest) -> MessageResponse:
    try:
        MemoryStore(req.tenant_id, req.user_id).reset()
        return MessageResponse(status="ok", message="Conversation memory has been cleared.")
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "error_code": "INTERNAL_ERROR",
                "message": str(exc),
            },
        )


@app.get("/status", response_model=StatusResponse, responses={500: {"model": ErrorResponse}})
def status(tenant_id: str = "default", user_id: str = "guest") -> StatusResponse:
    try:
        profile = get_or_create_profile(tenant_id)
        payload = runtime_status_payload(profile, user_id)
        return StatusResponse(**payload)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "error_code": "INTERNAL_ERROR",
                "message": str(exc),
            },
        )


@app.post("/refresh", response_model=MessageResponse, responses={500: {"model": ErrorResponse}})
def refresh(req: RefreshRequest) -> MessageResponse:
    try:
        profile = get_or_create_profile(req.tenant_id)
        build_runtime(profile, force_rebuild=True)
        return MessageResponse(status="ok", message="Runtime data has been refreshed.")
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "error_code": "RUNTIME_BUILD_FAILED",
                "message": str(exc),
            },
        )
