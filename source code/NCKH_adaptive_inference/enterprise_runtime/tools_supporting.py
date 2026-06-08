from __future__ import annotations

from typing import Any, Dict

from enterprise_runtime.memory_store import MemoryStore
from enterprise_runtime.models import TenantProfile
from enterprise_runtime.tools_core import (
    _dataset_kind,
    _group_columns,
    _read_csv_clean,
    _read_excel_sheet_clean,
    _sample_values,
    safe_calculate,
    tool_current_time,
    tool_list_docs,
    tool_list_tenants,
    tool_refresh,
    tool_status,
)


def handle_slash_command(
    cmd_raw: str,
    profile: TenantProfile,
    user_id: str,
    state: Dict[str, Any],
):
    q = cmd_raw.strip()
    q_lower = q.lower()

    if q_lower == "/help":
        msg = (
            "Support commands:\n"
            "/status\n"
            "/tenants\n"
            "/listdocs\n"
            "/refresh or /reindex\n"
            "/resetmem\n"
            "/switch <tenant> <user>\n"
            "/time\n"
            "/calc <expression>\n"
            "/sources on | /sources off"
        )
        return profile, user_id, msg

    if q_lower == "/status":
        return profile, user_id, tool_status(profile, user_id)

    if q_lower == "/tenants":
        return profile, user_id, tool_list_tenants()

    if q_lower == "/listdocs":
        return profile, user_id, tool_list_docs(profile)

    if q_lower in {"/refresh", "/reindex"}:
        return profile, user_id, tool_refresh(profile)

    if q_lower == "/resetmem":
        MemoryStore(profile.tenant_id, user_id).reset()
        return profile, user_id, "Conversation memory has been cleared."

    if q_lower == "/time":
        return profile, user_id, tool_current_time()

    if q_lower.startswith("/calc "):
        return profile, user_id, f"Calculation result: {safe_calculate(q[6:])}"

    if q_lower.startswith("/switch "):
        parts = q.split()
        new_tenant = parts[1] if len(parts) > 1 else "default"
        new_user = parts[2] if len(parts) > 2 else user_id
        state["tenant_id"] = new_tenant
        state["user_id"] = new_user
        from enterprise_runtime.llm_service import get_or_create_profile

        new_profile = get_or_create_profile(new_tenant)
        return new_profile, new_user, f"Switched to tenant: {new_tenant}, user: {new_user}"

    if q_lower == "/sources on":
        state["show_sources"] = True
        return profile, user_id, "Source display is now enabled."

    if q_lower == "/sources off":
        state["show_sources"] = False
        return profile, user_id, "Source display is now disabled."

    return profile, user_id, "Invalid command. Type /help to view the command list."
