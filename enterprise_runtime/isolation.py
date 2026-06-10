from __future__ import annotations

import re
import unicodedata
from typing import Optional

from enterprise_runtime.config import load_tenant_configs
from enterprise_runtime.models import TenantProfile

_TENANT_REF_RE = re.compile(r"\btenant\s+([a-z0-9][a-z0-9_\-]*)\b", re.IGNORECASE)

_ACCESS_SCOPE_HINTS = {
    "document",
    "data",
    "internal",
    "private",
    "note",
    "file",
    "pdf",
    "csv",
    "xlsx",
    "schedule",
    "room",
    "authentication code",
    "memory",
    "conversation",
    "secret string",
    "policy",
    "procedure",
    "sop",
    "compliance",
    "checklist",
    "contract",
    "invoice",
    "procurement",
    "vendor",
    "payroll",
    "benefit",
    "employee",
    "hr",
    "leave policy",
    "contract",
    "vendor",
    "salary",
}

_MEMORY_HINTS = {
    "memory",
    "conversation",
    "secret string",
    "remember it",
    "remember this",
    "in the current memory",
}


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or "").strip().lower())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.replace("\u0111", "d")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _tenant_aliases(tenant_id: str, display_name: str) -> set[str]:
    aliases: set[str] = set()

    def _add_alias(value: str) -> None:
        normalized = _normalize(value)
        if not normalized:
            return
        aliases.add(normalized)
        for token in re.split(r"[\s_\-]+", normalized):
            if len(token) >= 2:
                aliases.add(token)
        for token in re.findall(r"\d{2,6}", normalized):
            aliases.add(token)

    _add_alias(tenant_id)
    _add_alias(display_name)
    return aliases


def _resolve_explicit_foreign_tenant(question: str, current_tenant_id: str) -> Optional[str]:
    normalized_question = _normalize(question)
    if not normalized_question:
        return None

    referenced_tokens = {
        _normalize(match.group(1))
        for match in _TENANT_REF_RE.finditer(normalized_question)
        if _normalize(match.group(1))
    }
    if not referenced_tokens:
        return None

    configs = load_tenant_configs()
    alias_map = {
        tenant_id: _tenant_aliases(tenant_id, str(raw.get("display_name", tenant_id)))
        for tenant_id, raw in configs.items()
    }
    current_aliases = alias_map.get(current_tenant_id, _tenant_aliases(current_tenant_id, current_tenant_id))

    for token in referenced_tokens:
        if token in current_aliases:
            continue
        for tenant_id, aliases in alias_map.items():
            if tenant_id == current_tenant_id:
                continue
            if token in aliases:
                return tenant_id
    return None


def resolve_cross_tenant_access_denial(question: str, profile: TenantProfile) -> Optional[str]:
    foreign_tenant_id = _resolve_explicit_foreign_tenant(question, profile.tenant_id)
    if not foreign_tenant_id:
        return None

    normalized_question = _normalize(question)
    if not any(hint in normalized_question for hint in _ACCESS_SCOPE_HINTS):
        return None

    if any(hint in normalized_question for hint in _MEMORY_HINTS):
        scope_label = "conversation memory"
    else:
        scope_label = "internal data or files"

    return (
        f"Cannot access another tenant's {scope_label} from the current tenant `{profile.tenant_id}`. "
        "Only shared data or data owned by the current tenant may be used."
    )
