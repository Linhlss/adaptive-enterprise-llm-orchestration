from __future__ import annotations

import re
from typing import Any, Dict, List

from enterprise_runtime.llm_service import resolve_personalization_state
from enterprise_runtime.models import TenantProfile
from enterprise_runtime.runtime_manager import RUNTIME_CACHE
from enterprise_runtime.utils import format_ram_usage, get_ram_usage
from enterprise_runtime.schemas import SourceItem


_SOURCE_LINE_RE = re.compile(
    r"^[-–]\s*(?P<name>[^|\n]+?)\s*\|\s*scope=(?P<scope>[^|\n]+)(?:\s*\|\s*score=(?P<score>[0-9.]+))?(?:\s*\|\s*page_label=(?P<page>[^|\n]+))?",
    re.IGNORECASE,
)


def infer_mode_from_route(route: str) -> str:
    if route == "tool":
        return "fast_path"
    if route == "retrieval":
        return "normal_path"
    if route == "general":
        return "normal_path"
    return "slow_path"



def parse_sources_from_answer(answer: str) -> List[SourceItem]:
    if "Sources used:" not in answer:
        return []

    _, tail = answer.split("Sources used:", 1)
    items: List[SourceItem] = []
    for line in tail.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _SOURCE_LINE_RE.match(line)
        if m:
            score = m.group("score")
            items.append(
                SourceItem(
                    type="file",
                    name=m.group("name").strip(),
                    scope=m.group("scope").strip(),
                    page_label=(m.group("page").strip() if m.group("page") else None),
                    score=(float(score) if score else None),
                )
            )
        elif line.startswith("-"):
            items.append(SourceItem(type="file", name=line[1:].strip(), scope="unknown"))
    return items



def runtime_status_payload(profile: TenantProfile, user_id: str) -> Dict[str, Any]:
    rt = RUNTIME_CACHE.get(profile.tenant_id)
    personalization = resolve_personalization_state(profile)
    return {
        "status": "ok",
        "tenant_id": profile.tenant_id,
        "user_id": user_id,
        "domain": {
            "id": profile.domain_id,
            "name": profile.domain_name,
        },
        "runtime": {
            "docs": rt.document_count if rt else "N/A",
            "nodes": rt.node_count if rt else "N/A",
            "loaded_at": rt.loaded_at if rt else "N/A",
        },
        "resources": {
            "ram": format_ram_usage(get_ram_usage()),
        },
        "model": {
            "name": personalization["model_name"],
            "class": personalization["model_class"],
            "backend": personalization["llm_backend"],
            "adapter": profile.adapter_name,
        },
        "retrieval": {
            "top_k": profile.top_k,
            "chunk_size": profile.chunk_size,
            "chunk_overlap": profile.chunk_overlap,
            "query_expansion": profile.enable_query_expansion,
            "hybrid_retrieval": profile.enable_hybrid_retrieval,
            "reranker": profile.enable_reranker,
        },
        "routing": {
            "mode": profile.fixed_route_mode,
            "policy": "heuristic_v2",
        },
        "personalization": {
            "enabled": personalization["adapter_enabled"],
            "adapter_available": personalization["adapter_available"],
            "runtime_mode": personalization["runtime_mode"],
            "adapter_path": personalization["adapter_path"],
        },
    }
