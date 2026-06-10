from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Optional

from enterprise_runtime.models import TenantProfile
from enterprise_runtime.tools_core import detect_direct_tool

_ROUTE_TOOL = "tool"
_ROUTE_RAG = "retrieval"
_ROUTE_GENERAL = "general"
_ROUTE_OUT_OF_SCOPE = "out_of_scope"

_RAG_KEYWORDS = {
    "policy", "regulation", "procedure", "manual", "guideline", "handbook",
    "course", "credit", "schedule", "timetable", "record", "document", "file",
    "pdf", "xlsx", "doc", "docx", "form", "notice", "source", "evidence", "article",
    "policy", "procedure", "sop", "compliance", "checklist", "guideline", "manual",
    "contract", "invoice", "procurement", "purchase", "vendor", "audit", "risk",
    "hr", "human resources", "leave policy", "onboarding", "benefit", "payroll",
    "operations", "approval", "internal notice", "quality", "training",
}

_GENERAL_PATTERNS = [
    r"^(hello|hi|hey)\b",
    r"\b(who are you)\b",
    r"\b(thanks|thank you)\b",
    r"\b(explain)\b",
    r"\b(summarize)\b",
    r"\b(write)\b",
    r"\b(plan|checklist)\b",
    r"\b(suggest|advice|recommend)\b",
    r"\b(stress|time management)\b",
    r"\b(study plan|study better|exam prep)\b",
    r"\b(remember|remind)\b",
    r"\b(memory|conversation)\b",
]

_OUT_OF_SCOPE_PATTERNS = [
    r"\b(hack|crack|malware|virus|ddos)\b",
    r"\b(bomb|weapon|drug synthesis)\b",
    r"\b(phishing|email scam|scam email)\b",
    r"\b(password|credential(?:s)?|steal password|credential theft)\b",
    r"\b(bypass|disable)\b.*\b(camera|cameras|security)\b",
    r"\b(lockpicking|forg(e|ery) signature)\b",
]

_FILE_HINT_RE = re.compile(r"[\w\-.]+\.(?:pdf|docx|doc|xlsx|xls|txt|md)", re.IGNORECASE)
_TABLE_TERMS = {"excel", "xlsx", "xls", "csv", "sheet", "table", "column", "row", "course code", "class code"}
_TABLE_TERMS.update({
    "table", "spreadsheet", "row", "column", "report", "dashboard",
    "employee_id", "vendor_id", "invoice_id", "po", "purchase order",
    "employee code", "vendor code", "invoice code", "purchase order",
})


@dataclass
class RouterResult:
    route: str
    reason: str
    score: float = 0.0
    candidates: Dict[str, float] | None = None
    features: Dict[str, object] | None = None
    policy: str = "heuristic_v2"
    direct_answer: Optional[str] = None


def _route_features(question: str) -> Dict[str, object]:
    q = question.lower().strip()
    word_count = len(q.split())
    rag_keyword_hits = sum(1 for kw in _RAG_KEYWORDS if kw in q)
    general_pattern_hits = sum(1 for pattern in _GENERAL_PATTERNS if re.search(pattern, q))
    out_of_scope_hits = sum(1 for pattern in _OUT_OF_SCOPE_PATTERNS if re.search(pattern, q))
    has_file_hint = bool(_FILE_HINT_RE.search(question))
    has_table_terms = any(term in q for term in _TABLE_TERMS)

    return {
        "word_count": word_count,
        "is_short_query": word_count <= 3,
        "rag_keyword_hits": rag_keyword_hits,
        "general_pattern_hits": general_pattern_hits,
        "out_of_scope_hits": out_of_scope_hits,
        "has_file_hint": has_file_hint,
        "has_table_terms": has_table_terms,
    }


def _score_routes(features: Dict[str, object], has_direct_tool: bool) -> Dict[str, float]:
    rag_keyword_hits = int(features["rag_keyword_hits"])
    general_pattern_hits = int(features["general_pattern_hits"])
    out_of_scope_hits = int(features["out_of_scope_hits"])
    is_short_query = bool(features["is_short_query"])
    has_file_hint = bool(features["has_file_hint"])
    has_table_terms = bool(features["has_table_terms"])

    scores: Dict[str, float] = {
        _ROUTE_TOOL: 0.0,
        _ROUTE_RAG: 0.15,
        _ROUTE_GENERAL: 0.10,
        _ROUTE_OUT_OF_SCOPE: 0.0,
    }

    if has_direct_tool:
        scores[_ROUTE_TOOL] += 1.0
    if has_file_hint:
        scores[_ROUTE_RAG] += 0.45
        scores[_ROUTE_TOOL] += 0.20 if has_table_terms else 0.0
    if rag_keyword_hits:
        scores[_ROUTE_RAG] += min(0.6, rag_keyword_hits * 0.15)
    if general_pattern_hits:
        scores[_ROUTE_GENERAL] += min(0.7, general_pattern_hits * 0.25)
    if out_of_scope_hits:
        scores[_ROUTE_OUT_OF_SCOPE] += min(1.0, out_of_scope_hits * 0.5)
    if is_short_query:
        scores[_ROUTE_GENERAL] += 0.2
    if has_table_terms:
        scores[_ROUTE_TOOL] += 0.25
        scores[_ROUTE_RAG] += 0.05

    return {key: round(value, 4) for key, value in scores.items()}


def _forced_route(profile: TenantProfile, direct_answer: Optional[str]) -> Optional[RouterResult]:
    fixed_mode = (profile.fixed_route_mode or "adaptive").lower()
    if fixed_mode in {"", "adaptive", "auto"}:
        return None

    if fixed_mode == _ROUTE_TOOL and direct_answer:
        return RouterResult(
            route=_ROUTE_TOOL,
            reason="The fixed tool route is enabled and a direct tool match was found.",
            score=1.0,
            policy="fixed_route",
            direct_answer=direct_answer,
        )
    if fixed_mode == _ROUTE_TOOL:
        return None

    if fixed_mode in {_ROUTE_RAG, _ROUTE_GENERAL, _ROUTE_OUT_OF_SCOPE}:
        return RouterResult(
            route=fixed_mode,
            reason=f"The fixed route mode is forcing route={fixed_mode}.",
            score=1.0,
            policy="fixed_route",
            direct_answer=direct_answer if fixed_mode == _ROUTE_TOOL else None,
        )
    return None


def route_question(question: str, profile: TenantProfile, user_id: str) -> RouterResult:
    direct = detect_direct_tool(question, profile, user_id)
    forced = _forced_route(profile, direct)
    if forced is not None:
        return forced

    features = _route_features(question)
    candidates = _score_routes(features, bool(direct))

    if direct and candidates[_ROUTE_TOOL] >= max(candidates[_ROUTE_RAG], candidates[_ROUTE_GENERAL]):
        return RouterResult(
            route=_ROUTE_TOOL,
            reason="A direct tool match was found.",
            score=candidates[_ROUTE_TOOL],
            candidates=candidates,
            features=features,
            direct_answer=direct,
        )

    if candidates[_ROUTE_OUT_OF_SCOPE] >= 0.5:
        return RouterResult(
            route=_ROUTE_OUT_OF_SCOPE,
            reason="The request appears to be outside the supported scope.",
            score=candidates[_ROUTE_OUT_OF_SCOPE],
            candidates=candidates,
            features=features,
        )

    if candidates[_ROUTE_RAG] >= max(candidates[_ROUTE_GENERAL], candidates[_ROUTE_TOOL]):
        return RouterResult(
            route=_ROUTE_RAG,
            reason="The request appears to require grounding in internal documents or structured evidence.",
            score=candidates[_ROUTE_RAG],
            candidates=candidates,
            features=features,
        )

    if candidates[_ROUTE_GENERAL] >= 0.2:
        return RouterResult(
            route=_ROUTE_GENERAL,
            reason="Direct generation is preferred for lightweight or conversational queries.",
            score=candidates[_ROUTE_GENERAL],
            candidates=candidates,
            features=features,
        )

    return RouterResult(
        route=_ROUTE_RAG,
        reason="The routing signal is weak, so the system falls back to retrieval to preserve recall.",
        score=candidates[_ROUTE_RAG],
        candidates=candidates,
        features=features,
    )
