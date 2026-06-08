from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib import error, parse, request

import streamlit as st

from systems_evaluation.generate_test_queries import build_source_items, save_generated_queries
from supporting_personalization_assets.paths import (
    ensure_personalization_dirs,
    generated_qa_path,
    lora_clean_dataset_path,
    lora_dataset_path,
    lora_training_report_path,
    tenant_adapter_dir,
    tenant_source_dir,
)
from enterprise_runtime.ingestion import tenant_files_dir, tenant_links_file


BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config" / "tenants.json"
PIPELINE1_DIR = BASE_DIR / "supporting_personalization_dataset"
PERSONALIZATION_DIR = BASE_DIR / "supporting_personalization_assets"
EVAL_DATASET_PATH = BASE_DIR / "systems_evaluation" / "test_queries.json"
DEFAULT_API_BASE = os.getenv("STREAMLIT_API_BASE", "http://127.0.0.1:8000")
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
FILE_TOKEN_RE = re.compile(r"(\/[^\s'\"<>]+\.(?:pdf|docx|doc|xlsx|xls|csv|txt|md))", re.IGNORECASE)
DEFAULT_UI_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:4b")
DEFAULT_UI_MODEL_CLASS = os.getenv("DEFAULT_MODEL_CLASS", "light-latency")
DEFAULT_UI_BACKEND = os.getenv("LLM_BACKEND", "ollama")
DEFAULT_UI_DOMAIN_ID = os.getenv("DEFAULT_DOMAIN_ID", "academic_admin")
DEFAULT_UI_DOMAIN_NAME = os.getenv("DEFAULT_DOMAIN_NAME", "Academic and administrative support")


def http_json(method: str, url: str, payload: Dict[str, Any] | None = None, timeout: int = 120) -> Dict[str, Any]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = request.Request(url=url, method=method.upper(), data=data, headers=headers)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8")
            return json.loads(text) if text else {}
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"message": body or str(exc)}
        raise RuntimeError(f"{exc.code} {exc.reason}: {parsed}")
    except error.URLError as exc:
        raise RuntimeError(f"Could not connect to the API: {exc}")


def api_connection_status(api_base: str) -> Tuple[bool, str]:
    try:
        payload = http_json("GET", f"{api_base.rstrip('/')}/health", timeout=2)
        return True, payload.get("status", "ok")
    except Exception as exc:
        return False, str(exc)


def load_tenant_configs() -> Dict[str, Dict[str, Any]]:
    if not CONFIG_FILE.exists():
        return {}
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


def save_tenant_configs(configs: Dict[str, Dict[str, Any]]) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(configs, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_tenant_id(raw: str) -> str:
    normalized = re.sub(r"[^a-z0-9_]+", "_", raw.lower()).strip("_")
    return normalized or "tenant_moi"


def run_supporting_personalization_dataset(tenant_id: str) -> Tuple[int, str]:
    cmd = [sys.executable, str(PIPELINE1_DIR / "run_pipeline1.py"), "--tenant-id", tenant_id]
    proc = subprocess.run(
        cmd,
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode, output.strip()


def run_clean_lora_dataset(tenant_id: str) -> Tuple[int, str]:
    cmd = [sys.executable, str(PERSONALIZATION_DIR / "clean_dataset.py"), "--tenant-id", tenant_id]
    proc = subprocess.run(
        cmd,
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode, output.strip()


def run_lora_training(tenant_id: str) -> Tuple[int, str]:
    cmd = [sys.executable, str(BASE_DIR / "supporting_personalization_training" / "train_lora.py"), "--tenant-id", tenant_id]
    proc = subprocess.run(
        cmd,
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode, output.strip()


def run_lora_smoke_test(tenant_id: str, prompt: str) -> Tuple[int, str]:
    cmd = [sys.executable, str(BASE_DIR / "supporting_personalization_validation" / "test_lora.py"), "--tenant-id", tenant_id, "--prompt", prompt]
    proc = subprocess.run(
        cmd,
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode, output.strip()


def count_json_records(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    return len(data) if isinstance(data, list) else 0


def append_unique_links(path: Path, links: List[str]) -> List[str]:
    existing = []
    if path.exists():
        existing = [line.strip() for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
    merged = list(existing)
    added: List[str] = []
    for link in links:
        if link not in merged:
            merged.append(link)
            added.append(link)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(merged) + ("\n" if merged else ""), encoding="utf-8")
    return added


def persist_tenant_links(tenant_id: str, links: List[str]) -> List[str]:
    if not links:
        return []
    return append_unique_links(tenant_links_file(tenant_id), links)


def persist_tenant_files(tenant_id: str, uploaded_files: List[Any]) -> List[str]:
    saved: List[str] = []
    target_dir = tenant_files_dir(tenant_id)
    for item in uploaded_files:
        target = target_dir / item.name
        target.write_bytes(item.getbuffer())
        saved.append(str(target))
    return saved


def persist_file_paths_from_prompt(tenant_id: str, prompt: str) -> List[str]:
    target_dir = tenant_files_dir(tenant_id)
    saved: List[str] = []
    matches = FILE_TOKEN_RE.findall(prompt or "")
    for raw in matches:
        source = Path(raw).expanduser()
        if not source.exists() or not source.is_file():
            continue
        target = target_dir / source.name
        if source.resolve() == target.resolve():
            saved.append(str(target))
            continue
        target.write_bytes(source.read_bytes())
        saved.append(str(target))
    return saved


def refresh_tenant_runtime(api_base: str, tenant_id: str) -> Tuple[bool, str]:
    try:
        payload = http_json("POST", f"{api_base.rstrip('/')}/refresh", {"tenant_id": tenant_id})
        return True, payload.get("message", "Runtime data has been refreshed.")
    except Exception as exc:
        return False, str(exc)


def regenerate_queries_for_sources(tenant_id: str, file_paths: List[str], links: List[str]) -> Tuple[bool, str]:
    try:
        sources = build_source_items(file_paths, links, tenant_id)
        count = save_generated_queries(sources, output=EVAL_DATASET_PATH, merge_existing=True)
        return True, f"Updated systems_evaluation/test_queries.json ({count} records after merge)."
    except Exception as exc:
        return False, f"Could not regenerate queries: {exc}"


def extract_links_from_prompt(prompt: str) -> List[str]:
    cleaned = []
    for match in URL_RE.findall(prompt or ""):
        link = match.rstrip(").,;]}>")
        if link not in cleaned:
            cleaned.append(link)
    return cleaned


def ingest_chat_sources(
    tenant_id: str,
    api_base: str,
    prompt: str = "",
    uploaded_files: List[Any] | None = None,
    manual_links: List[str] | None = None,
) -> Dict[str, Any]:
    uploaded_files = uploaded_files or []
    manual_links = manual_links or []
    prompt_links = extract_links_from_prompt(prompt)
    all_links = list(dict.fromkeys([*manual_links, *prompt_links]))

    saved_files = persist_tenant_files(tenant_id, uploaded_files)
    saved_files.extend([path for path in persist_file_paths_from_prompt(tenant_id, prompt) if path not in saved_files])
    added_links = persist_tenant_links(tenant_id, all_links)

    changed = bool(saved_files or added_links)
    refresh_ok, refresh_note = (True, "No refresh needed.") if not changed else refresh_tenant_runtime(api_base, tenant_id)
    regen_ok, regen_note = (True, "No query regeneration needed.") if not changed else regenerate_queries_for_sources(tenant_id, saved_files, added_links)

    return {
        "changed": changed,
        "saved_files": saved_files,
        "added_links": added_links,
        "refresh_ok": refresh_ok,
        "refresh_note": refresh_note,
        "regen_ok": regen_ok,
        "regen_note": regen_note,
    }


def session_chat_key(tenant_id: str, user_id: str) -> str:
    user = user_id.strip() or "guest"
    return f"{tenant_id}::{user}"


def get_chat_store() -> Dict[str, List[Dict[str, Any]]]:
    if "chat_sessions" not in st.session_state:
        st.session_state.chat_sessions = {}
    return st.session_state.chat_sessions


def get_messages(chat_key: str) -> List[Dict[str, Any]]:
    return get_chat_store().setdefault(chat_key, [])


def append_message(chat_key: str, role: str, content: str, meta: Dict[str, Any] | None = None) -> None:
    get_messages(chat_key).append(
        {
            "role": role,
            "content": content,
            "meta": meta or {},
        }
    )


def clear_messages(chat_key: str) -> None:
    get_chat_store()[chat_key] = []


def nl2br(text: str) -> str:
    return html.escape(text).replace("\n", "<br>")


def render_message(role: str, content: str, meta: Dict[str, Any] | None = None) -> None:
    meta = meta or {}
    side_class = "user-row" if role == "user" else "assistant-row"
    bubble_class = "user-bubble" if role == "user" else "assistant-bubble"
    label = "You" if role == "user" else "Assistant"

    pills: List[str] = []
    for key in ["route", "mode", "latency_ms"]:
        value = meta.get(key)
        if value is None or value == "":
            continue
        if key == "latency_ms":
            pills.append(f"{value} ms")
        else:
            pills.append(str(value))

    pills_html = "".join(f"<span class='msg-pill'>{html.escape(pill)}</span>" for pill in pills)

    st.markdown(
        f"""
        <div class="chat-row {side_class}">
            <div class="chat-bubble {bubble_class}">
                <div class="chat-label">{label}</div>
                <div class="chat-content">{nl2br(content)}</div>
                {"<div class='chat-meta'>" + pills_html + "</div>" if pills_html else ""}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    sources = meta.get("sources") or []
    if role == "assistant" and sources:
        with st.expander("Referenced sources", expanded=False):
            st.dataframe(sources, use_container_width=True)

    metadata = meta.get("metadata") or {}
    if role == "assistant" and metadata:
        with st.expander("Response details", expanded=False):
            st.json(metadata)


def render_preview_card(title: str, body: str, tone: str = "neutral") -> None:
    st.markdown(
        f"""
        <div class="preview-card preview-{tone}">
            <div class="preview-card-title">{html.escape(title)}</div>
            <div class="preview-card-body">{html.escape(body)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_preview_stage(title: str, body: str) -> None:
    st.markdown(
        f"""
        <div class="preview-stage">
            <div class="preview-stage-title">{html.escape(title)}</div>
            <div class="preview-stage-body">{html.escape(body)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_quick_ask_card(icon: str, title: str, body: str, accent: str = "blue") -> None:
    st.markdown(
        f"""
        <div class="quick-card {accent}">
            <div class="quick-icon">{html.escape(icon)}</div>
            <div class="quick-title">{html.escape(title)}</div>
            <div class="quick-body">{html.escape(body)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_session_summary_card(message_count: int, tenant_id: str, user_id: str) -> None:
    user_label = user_id.strip() or "guest"
    st.markdown(
        f"""
        <div class="session-card">
            <div class="session-card-head">
                <span>SESSION OVERVIEW</span>
                <span class="session-badge">#{html.escape(tenant_id)}</span>
            </div>
            <div class="session-card-row">
                <span>Total chats</span>
                <strong>{message_count}</strong>
            </div>
            <div class="session-card-row">
                <span>Active Tenant</span>
                <strong>{html.escape(tenant_id)}</strong>
            </div>
            <div class="session-card-row">
                <span>User Context</span>
                <strong>{html.escape(user_label)}</strong>
            </div>
            <div class="session-card-row">
                <span>RAG Mode</span>
                <strong>Multi-tenant core</strong>
            </div>
            <div class="session-progress">
                <div class="session-progress-bar"></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


st.set_page_config(page_title="Multi-tenant RAG Control Panel", page_icon=":robot_face:", layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap');

    :root {
        --bg-main: #f4f7fb;
        --bg-side: #e7eef6;
        --bg-panel: rgba(255,255,255,0.86);
        --bg-panel-strong: rgba(255,255,255,0.97);
        --line: #d0dae6;
        --line-strong: #b8c7d8;
        --text-main: #1c2633;
        --text-soft: #55697d;
        --text-muted: #7a8ea3;
        --accent: #1d63b7;
        --accent-strong: #174f92;
        --accent-soft: #dfeaf8;
        --navy: #24323d;
        --navy-soft: #31404c;
        --assistant: #ffffff;
        --user: linear-gradient(135deg, #1d63b7 0%, #174f92 100%);
        --shadow: 0 18px 50px rgba(53, 79, 110, 0.08);
    }

    .stApp {
        font-family: 'Manrope', sans-serif;
        background: linear-gradient(180deg, #f6f9fc 0%, #edf2f7 100%);
        color: var(--text-main);
    }

    [data-testid="stHeader"] {
        display: none;
    }

    .stDeployButton {
        display: none;
    }

    html, body, [class*="css"]  {
        font-family: 'Manrope', sans-serif;
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #e9eff5 0%, #edf3f8 100%);
        border-right: 1px solid rgba(51, 76, 102, 0.08);
    }

    [data-testid="stSidebar"] > div:first-child {
        padding-top: 1.4rem;
    }

    [data-testid="stSidebar"] * {
        color: var(--text-main);
    }

    [data-testid="stSidebar"] .stMarkdown h3,
    [data-testid="stSidebar"] .stMarkdown h2,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] .stSelectbox label,
    [data-testid="stSidebar"] .stTextInput label {
        color: #5d6f82 !important;
        font-weight: 700 !important;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        font-size: 0.82rem !important;
    }

    [data-testid="stSidebar"] .stTextInput input,
    [data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] > div {
        background: rgba(255,255,255,0.92);
        border: 1px solid var(--line-strong);
        border-radius: 16px;
        color: var(--text-main) !important;
        min-height: 52px;
    }

    [data-testid="stSidebar"] .stTextInput input::placeholder {
        color: #94a6b8;
        opacity: 1;
    }

    [data-testid="stSidebar"] .stCheckbox label span,
    [data-testid="stSidebar"] .stCheckbox p {
        color: var(--text-main) !important;
        font-weight: 600;
        letter-spacing: 0;
        text-transform: none;
        font-size: 0.98rem !important;
    }

    [data-testid="stSidebar"] .stAlert {
        background: rgba(255,255,255,0.85);
        border: 1px solid rgba(64, 87, 111, 0.08);
        color: var(--text-main);
    }

    [data-testid="stSidebar"] .stButton button {
        border-radius: 18px;
        min-height: 52px;
        background: #4b5563;
        color: #ffffff;
        border: none;
        font-weight: 700;
    }

    .block-container {
        padding-top: 0.4rem;
        padding-bottom: 1.1rem;
        max-width: 1480px;
    }

    .sidebar-brand {
        padding: 0.35rem 0 1.1rem;
        margin-bottom: 0.5rem;
    }

    .sidebar-brand-title {
        font-size: clamp(1.9rem, 1.55rem + 1.1vw, 2.5rem);
        font-weight: 800;
        line-height: 1.05;
        color: #182535;
        letter-spacing: -0.04em;
    }

    .sidebar-brand-sub {
        color: #5a6e82;
        margin-top: 0.35rem;
        font-size: 0.98rem;
    }

    .hero-card {
        background: linear-gradient(180deg, rgba(255,255,255,0.95), rgba(250,252,255,0.92));
        border: 1px solid rgba(64, 87, 111, 0.08);
        box-shadow: 0 10px 28px rgba(70, 96, 128, 0.06);
        border-radius: 0 0 0 0;
        border-left: none;
        border-right: none;
        border-top: none;
        padding: 18px 30px 16px;
        margin: -0.7rem -1rem 1rem;
    }

    .hero-title {
        font-size: clamp(1.85rem, 1.35rem + 1.55vw, 2.65rem);
        font-weight: 800;
        line-height: 1.18;
        color: #1d2734;
        margin-bottom: 4px;
        letter-spacing: -0.04em;
        max-width: 540px;
    }

    .hero-subtitle {
        font-size: clamp(0.98rem, 0.92rem + 0.25vw, 1.12rem);
        color: var(--text-soft);
        max-width: 740px;
        line-height: 1.75;
    }

    .status-pill {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        border-radius: 999px;
        padding: 10px 18px;
        font-size: 0.87rem;
        font-weight: 600;
        margin-top: 10px;
        background: var(--accent-soft);
        color: var(--accent-strong);
        border: 1px solid rgba(29, 99, 183, 0.18);
        letter-spacing: 0.06em;
        text-transform: uppercase;
    }

    .status-pill.offline {
        background: rgba(163, 52, 48, 0.08);
        color: #9f2f2a;
        border-color: rgba(163, 52, 48, 0.14);
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 26px;
        border-bottom: 1px solid rgba(64, 87, 111, 0.1);
        margin-top: 0.2rem;
        flex-wrap: wrap;
    }

    .stTabs [data-baseweb="tab"] {
        height: auto;
        padding: 0.35rem 0 0.7rem;
        color: #44586d;
        font-weight: 700;
        font-size: 0.95rem;
    }

    .stTabs [aria-selected="true"] {
        color: var(--accent) !important;
    }

    .chat-shell {
        background: rgba(255,255,255,0.92);
        border: 1px solid rgba(64, 87, 111, 0.08);
        box-shadow: 0 14px 36px rgba(70, 96, 128, 0.07);
        border-radius: 26px;
        padding: 0;
        overflow: hidden;
    }

    .chat-shell-head {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        padding: 26px 28px 20px;
        border-bottom: 1px solid rgba(64, 87, 111, 0.08);
    }

    .chat-shell-title {
        font-size: clamp(1.75rem, 1.35rem + 1vw, 2.3rem);
        font-weight: 800;
        letter-spacing: -0.03em;
        color: #1c2836;
    }

    .chat-shell-subtitle {
        color: var(--text-soft);
        margin-top: 0.25rem;
        font-size: clamp(0.94rem, 0.9rem + 0.25vw, 1.02rem);
    }

    .chat-shell-action {
        color: var(--accent);
        font-weight: 700;
        font-size: 1rem;
        white-space: nowrap;
    }

    .chat-shell-body {
        padding: 20px 22px 16px;
        min-height: min(58vh, 620px);
    }

    .chat-composer-note {
        text-align: center;
        color: #6e7c8b;
        font-size: 0.86rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        margin-top: 0.75rem;
    }

    .chat-row {
        display: flex;
        width: 100%;
        margin: 0.4rem 0 0.9rem;
    }

    .assistant-row {
        justify-content: flex-start;
    }

    .user-row {
        justify-content: flex-end;
    }

    .chat-bubble {
        max-width: 78%;
        border-radius: 20px;
        padding: 14px 16px 12px;
        box-shadow: 0 10px 22px rgba(70, 96, 128, 0.07);
        border: 1px solid rgba(64, 87, 111, 0.08);
    }

    .assistant-bubble {
        background: var(--assistant);
        color: var(--text-main);
        border-top-left-radius: 8px;
    }

    .user-bubble {
        background: var(--user);
        color: #ffffff;
        border-top-right-radius: 8px;
        border: none;
    }

    .chat-label {
        font-size: 0.82rem;
        font-weight: 700;
        letter-spacing: 0.02em;
        text-transform: uppercase;
        opacity: 0.78;
        margin-bottom: 0.45rem;
    }

    .chat-content {
        font-size: clamp(0.97rem, 0.93rem + 0.2vw, 1.04rem);
        line-height: 1.7;
        word-break: break-word;
    }

    .chat-meta {
        margin-top: 0.8rem;
    }

    .msg-pill {
        display: inline-block;
        padding: 5px 10px;
        margin-right: 6px;
        margin-bottom: 6px;
        border-radius: 999px;
        background: rgba(20, 30, 20, 0.06);
        font-size: 0.78rem;
        font-weight: 600;
    }

    .empty-chat {
        min-height: min(44vh, 480px);
        display: flex;
        align-items: center;
        justify-content: center;
        flex-direction: column;
        padding: 32px 20px;
        text-align: center;
        color: var(--text-soft);
        border: none;
        border-radius: 0;
        background: transparent;
        margin-bottom: 10px;
    }

    .chat-tip-grid {
        display: grid;
        grid-template-columns: 1fr;
        gap: 14px;
        margin-top: 0.3rem;
    }

    .quick-card {
        background: rgba(255,255,255,0.94);
        border: 1px solid rgba(64, 87, 111, 0.08);
        border-radius: 18px;
        padding: 18px 18px 16px;
        box-shadow: 0 10px 24px rgba(70, 96, 128, 0.05);
    }

    .quick-icon {
        font-size: 1.5rem;
        margin-bottom: 0.65rem;
    }

    .quick-title {
        color: #182535;
        font-size: clamp(1rem, 0.97rem + 0.2vw, 1.08rem);
        font-weight: 800;
        margin-bottom: 0.35rem;
    }

    .quick-body {
        color: var(--text-soft);
        font-size: clamp(0.92rem, 0.89rem + 0.18vw, 0.98rem);
        line-height: 1.55;
    }

    .quick-card.blue .quick-icon { color: #1d63b7; }
    .quick-card.green .quick-icon { color: #0f9d75; }
    .quick-card.orange .quick-icon { color: #f08b23; }

    .session-card {
        margin-top: 1.2rem;
        background: linear-gradient(180deg, #2a3742 0%, #25313a 100%);
        color: #f1f6fb;
        border-radius: 22px;
        padding: 22px 18px 18px;
        box-shadow: 0 16px 32px rgba(23, 34, 44, 0.18);
    }

    .session-card-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        font-size: 0.86rem;
        letter-spacing: 0.08em;
        font-weight: 800;
        margin-bottom: 1.1rem;
    }

    .session-badge {
        background: rgba(100, 157, 243, 0.2);
        color: #8bb9ff;
        border-radius: 10px;
        padding: 0.2rem 0.55rem;
    }

    .session-card-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0.7rem 0;
        border-top: 1px solid rgba(220, 233, 245, 0.08);
    }

    .session-card-row span {
        color: #d6e0ea;
    }

    .session-card-row strong {
        color: #ffffff;
    }

    .session-progress {
        margin-top: 1rem;
        height: 8px;
        border-radius: 999px;
        background: rgba(255,255,255,0.1);
        overflow: hidden;
    }

    .session-progress-bar {
        width: 78%;
        height: 100%;
        border-radius: 999px;
        background: linear-gradient(90deg, #77aef8 0%, #4be0c0 100%);
    }

    .soft-section {
        background: rgba(255,255,255,0.9);
        border: 1px solid rgba(64, 87, 111, 0.08);
        border-radius: 18px;
        padding: 18px;
        box-shadow: 0 10px 24px rgba(70, 96, 128, 0.05);
    }

    .soft-section h3 {
        margin-top: 0;
    }

    div[data-testid="stChatInput"] {
        background: rgba(241,246,251,0.92);
        border: 1px solid rgba(64, 87, 111, 0.08);
        border-radius: 24px;
        box-shadow: 0 10px 24px rgba(70, 96, 128, 0.06);
        padding-left: 0.4rem;
    }

    div[data-testid="stChatInput"] textarea,
    div[data-testid="stChatInput"] input {
        color: var(--text-main) !important;
        font-size: 1rem !important;
    }

    div[data-testid="stChatInput"] textarea::placeholder,
    div[data-testid="stChatInput"] input::placeholder {
        color: #91a3b4 !important;
        opacity: 1 !important;
    }

    div[data-testid="stMetric"] {
        background: rgba(255,255,255,0.9);
        border: 1px solid rgba(64, 87, 111, 0.08);
        border-radius: 18px;
        padding: 8px 10px;
    }

    .preview-shell {
        background: rgba(255,255,255,0.76);
        border: 1px solid rgba(31, 54, 43, 0.08);
        box-shadow: var(--shadow);
        border-radius: 28px;
        padding: 24px;
        margin-bottom: 18px;
    }

    .preview-banner {
        display: grid;
        grid-template-columns: 1.4fr 1fr;
        gap: 18px;
        align-items: stretch;
    }

    .preview-panel {
        background: linear-gradient(145deg, rgba(18, 63, 52, 0.96), rgba(31, 122, 99, 0.9));
        color: #f4fbf8;
        border-radius: 24px;
        padding: 22px;
        min-height: 220px;
    }

    .preview-panel.light {
        background: linear-gradient(145deg, rgba(255,255,255,0.96), rgba(245,247,242,0.9));
        color: var(--text-main);
        border: 1px solid rgba(31, 54, 43, 0.08);
    }

    .preview-kicker {
        display: inline-flex;
        padding: 7px 12px;
        border-radius: 999px;
        background: rgba(255,255,255,0.14);
        font-size: 0.82rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        margin-bottom: 14px;
    }

    .preview-panel.light .preview-kicker {
        background: rgba(17, 87, 70, 0.08);
        color: var(--accent-strong);
    }

    .preview-headline {
        font-size: 2rem;
        line-height: 1.08;
        font-weight: 800;
        margin-bottom: 12px;
        letter-spacing: -0.03em;
    }

    .preview-copy {
        font-size: 0.98rem;
        line-height: 1.7;
        opacity: 0.94;
    }

    .preview-card {
        border-radius: 20px;
        padding: 18px;
        border: 1px solid rgba(31, 54, 43, 0.08);
        background: rgba(255,255,255,0.88);
        min-height: 132px;
    }

    .preview-card-title {
        font-size: 0.88rem;
        font-weight: 800;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        margin-bottom: 8px;
        color: var(--accent-strong);
    }

    .preview-card-body {
        font-size: 0.97rem;
        line-height: 1.7;
        color: var(--text-main);
    }

    .preview-accent {
        background: linear-gradient(180deg, rgba(31,122,99,0.12), rgba(255,255,255,0.92));
    }

    .preview-warm {
        background: linear-gradient(180deg, rgba(208,168,92,0.14), rgba(255,255,255,0.92));
    }

    .preview-stage {
        position: relative;
        border-radius: 20px;
        padding: 18px 18px 16px 22px;
        background: rgba(255,255,255,0.85);
        border: 1px solid rgba(31, 54, 43, 0.08);
        min-height: 120px;
    }

    .preview-stage::before {
        content: "";
        position: absolute;
        left: 0;
        top: 18px;
        bottom: 18px;
        width: 6px;
        border-radius: 999px;
        background: linear-gradient(180deg, #1f7a63, #d0a85c);
    }

    .preview-stage-title {
        font-weight: 800;
        color: #233123;
        margin-bottom: 8px;
    }

    .preview-stage-body {
        color: var(--text-soft);
        line-height: 1.65;
    }

    .preview-mini-chat {
        border-radius: 22px;
        background: rgba(247,250,246,0.95);
        border: 1px solid rgba(31, 54, 43, 0.08);
        padding: 16px;
    }

    .preview-mini-row {
        display: flex;
        margin-bottom: 10px;
    }

    .preview-mini-row.user {
        justify-content: flex-end;
    }

    .preview-mini-bubble {
        max-width: 80%;
        border-radius: 18px;
        padding: 12px 14px;
        font-size: 0.94rem;
        line-height: 1.6;
    }

    .preview-mini-row.assistant .preview-mini-bubble {
        background: #ffffff;
        border: 1px solid rgba(31, 54, 43, 0.08);
    }

    .preview-mini-row.user .preview-mini-bubble {
        background: linear-gradient(135deg, #1f7a63 0%, #145144 100%);
        color: #ffffff;
    }

    @media (max-width: 900px) {
        .hero-title {
            font-size: 2.2rem;
        }
        .chat-bubble {
            max-width: 92%;
        }
        .hero-card {
            padding: 16px 18px 14px;
        }
        .chat-shell-head {
            display: block;
        }
        .chat-shell-action {
            margin-top: 0.8rem;
            display: inline-block;
        }
        .block-container {
            padding-left: 0.9rem;
            padding-right: 0.9rem;
        }
    }

    @media (max-width: 640px) {
        .sidebar-brand-title {
            font-size: 1.7rem;
        }
        .status-pill {
            width: 100%;
            justify-content: center;
            text-align: center;
        }
        .preview-banner {
            grid-template-columns: 1fr;
        }
        .chat-shell {
            border-radius: 20px;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

tenant_configs = load_tenant_configs()
tenant_options = sorted(tenant_configs.keys()) or ["default"]

with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-brand">
            <div class="sidebar-brand-title">Control Center</div>
            <div class="sidebar-brand-sub">v2.4.0-stable</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.subheader("System connection")
    api_base = st.text_input("API base URL", value=DEFAULT_API_BASE)
    api_ok, api_note = api_connection_status(api_base)
    if api_ok:
        st.success("API is available")
    else:
        st.error("API is not reachable yet")
        st.caption(api_note)

    st.divider()
    st.subheader("Working session")
    selected_tenant = st.selectbox("Tenant", tenant_options, index=0)
    user_id = st.text_input("User ID", value="guest")
    show_sources = st.checkbox("Show sources", value=True)

    active_chat_key = session_chat_key(selected_tenant, user_id)
    if st.button("Clear UI chat history", use_container_width=True):
        clear_messages(active_chat_key)
        st.rerun()

st.markdown(
    f"""
    <div class="hero-card">
        <div class="hero-title">Multi-tenant RAG Control Panel</div>
        <div class="hero-subtitle">
            This interface is designed as a more modern conversational demo:
            persistent chat, tenant tracking, runtime checks, and LoRA data preparation in one place.
        </div>
        <div class="status-pill {'offline' if not api_ok else ''}">
            {'API connected' if api_ok else 'API not ready'} • Current tenant: {html.escape(selected_tenant)}
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

tab_chat, tab_runtime, tab_tenants, tab_lora, tab_preview = st.tabs(
    ["Chat", "System status", "Tenant config", "LoRA workspace", "Preview"]
)

with tab_chat:
    chat_key = session_chat_key(selected_tenant, user_id)
    messages = get_messages(chat_key)
    if "chat_uploads" not in st.session_state:
        st.session_state.chat_uploads = {}
    if "chat_link_drafts" not in st.session_state:
        st.session_state.chat_link_drafts = {}
    upload_state_key = f"chat_upload::{selected_tenant}"
    link_state_key = f"chat_links::{selected_tenant}"

    top_col, side_col = st.columns([3.2, 1.2], gap="large")

    with top_col:
        st.markdown(
            f"""
            <div class="chat-shell">
                <div class="chat-shell-head">
                    <div>
                        <div class="chat-shell-title">Conversation</div>
                        <div class="chat-shell-subtitle">Active Session: RAG-{html.escape(selected_tenant)}-{html.escape((user_id.strip() or 'guest').upper())}</div>
                    </div>
                    <div class="chat-shell-action">+ New conversation</div>
                </div>
                <div class="chat-shell-body">
            """,
            unsafe_allow_html=True,
        )

        if messages:
            for message in messages:
                render_message(message["role"], message["content"], message.get("meta"))
        else:
            st.markdown(
                """
                <div class="empty-chat">
                    <div style="font-size:4rem; opacity:0.22; margin-bottom:0.8rem;">💬</div>
                    <div style="font-size:2rem; font-weight:800; color:#1e2a39; margin-bottom:0.8rem;">No conversation yet...</div>
                    <div style="font-size:1.12rem; max-width:620px;">
                        Start by entering a question below or choosing one of the quick prompts to explore the current tenant's data.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("</div></div>", unsafe_allow_html=True)

    with side_col:
        st.subheader("QUICK PROMPTS")
        render_quick_ask_card("📄", "PDF file configuration", "How to extract structured data from multiple PDFs?", "blue")
        render_quick_ask_card("📊", "Excel processing", "Querying specific rows in tenant spreadsheets.", "green")
        render_quick_ask_card("🧩", "System Architecture", "Explain the multi-tenant isolation strategy.", "orange")

        render_session_summary_card(len(messages), selected_tenant, user_id)

        st.markdown('<div class="soft-section">', unsafe_allow_html=True)
        st.subheader("Tenant sources")
        st.caption("Links mentioned in prompts are saved automatically. New files can also be attached here for immediate use under data/.")

        chat_link_draft = st.text_area(
            "Links to add to the current tenant",
            key=link_state_key,
            placeholder="One URL per line",
            height=90,
        )
        chat_uploads = st.file_uploader(
            "Attach files for the current tenant",
            type=["pdf", "docx", "doc", "xlsx", "xls", "csv", "txt", "md"],
            accept_multiple_files=True,
            key=upload_state_key,
        )
        if st.button("Save tenant sources + refresh", use_container_width=True):
            manual_links = [line.strip() for line in (chat_link_draft or "").splitlines() if line.strip()]
            ingest_result = ingest_chat_sources(
                selected_tenant,
                api_base,
                prompt="",
                uploaded_files=list(chat_uploads or []),
                manual_links=manual_links,
            )
            if ingest_result["changed"]:
                st.success(
                    f"Saved {len(ingest_result['saved_files'])} files and {len(ingest_result['added_links'])} links. "
                    f"{ingest_result['refresh_note']} {ingest_result['regen_note']}"
                )
            else:
                st.info("No new files or links were provided.")
        st.markdown("</div>", unsafe_allow_html=True)

    prompt = st.chat_input("Enter your question...")
    st.markdown('<div class="chat-composer-note">Powered by advanced RAG pipeline • multi-tenant core</div>', unsafe_allow_html=True)
    if prompt:
        ingest_result = ingest_chat_sources(
            selected_tenant,
            api_base,
            prompt=prompt,
            uploaded_files=[],
            manual_links=[],
        )
        append_message(chat_key, "user", prompt)
        payload = {
            "tenant_id": selected_tenant,
            "user_id": user_id.strip() or "guest",
            "message": prompt.strip(),
            "show_sources": show_sources,
        }

        try:
            with st.spinner("Fetching the answer from the system..."):
                resp = http_json("POST", f"{api_base.rstrip('/')}/chat", payload)
            append_message(
                chat_key,
                "assistant",
                resp.get("answer", ""),
                {
                    "route": resp.get("route", "unknown"),
                    "mode": resp.get("mode", "unknown"),
                    "latency_ms": (resp.get("metadata") or {}).get("latency_ms"),
                    "sources": resp.get("sources") or [],
                    "metadata": {
                        **(resp.get("metadata") or {}),
                        "auto_ingest": {
                            "saved_files": ingest_result["saved_files"],
                            "added_links": ingest_result["added_links"],
                            "refresh_ok": ingest_result["refresh_ok"],
                            "refresh_note": ingest_result["refresh_note"],
                            "regen_ok": ingest_result["regen_ok"],
                            "regen_note": ingest_result["regen_note"],
                        },
                    },
                },
            )
        except Exception as exc:
            append_message(
                chat_key,
                "assistant",
                f"System error: {exc}",
                {"route": "error", "mode": "error"},
            )
        st.rerun()

with tab_preview:
    st.subheader("Page Preview")
    st.caption("This page serves as a preview area for continued demo and committee-view refinement.")

    metric_col1, metric_col2, metric_col3 = st.columns(3)
    with metric_col1:
        st.metric("Checklist 2", "Near complete", "runtime integrated")
    with metric_col2:
        st.metric("Tenant active", selected_tenant)
    with metric_col3:
        st.metric("Presentation mode", "Preview page")

    card_col1, card_col2, card_col3 = st.columns(3)
    with card_col1:
        render_preview_card(
            "Optimization focus",
            "A shared model reduces duplicated resource use, while routing and retrieval optimization avoid unnecessary heavy inference calls.",
            tone="accent",
        )
    with card_col2:
        render_preview_card(
            "Runtime story",
            "The runtime separates tool, retrieval, and general paths so that each query goes through the processing route it actually needs instead of a monolithic pipeline.",
            tone="warm",
        )
    with card_col3:
        render_preview_card(
            "Next milestone",
            "Sau Checklist 3, khu vuc nay co the show adapter theo tenant, before versus after fine-tune, va system comparison cho buoi bao ve.",
        )

with tab_runtime:
    st.subheader("Runtime status")
    st.caption("Use this tab to inspect API health, the current tenant state, and data-refresh actions.")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Check /health", use_container_width=True):
            try:
                st.json(http_json("GET", f"{api_base.rstrip('/')}/health"))
            except Exception as exc:
                st.error(str(exc))

    with col2:
        if st.button("Xem /status", use_container_width=True):
            query = parse.urlencode({"tenant_id": selected_tenant, "user_id": user_id.strip() or "guest"})
            try:
                st.json(http_json("GET", f"{api_base.rstrip('/')}/status?{query}"))
            except Exception as exc:
                st.error(str(exc))

    with col3:
        if st.button("Refresh Index Tenant", use_container_width=True):
            try:
                st.json(
                    http_json(
                        "POST",
                        f"{api_base.rstrip('/')}/refresh",
                        {"tenant_id": selected_tenant},
                    )
                )
            except Exception as exc:
                st.error(str(exc))

    if st.button("Reset Chat Memory", use_container_width=True):
        try:
            st.json(
                http_json(
                    "POST",
                    f"{api_base.rstrip('/')}/memory/reset",
                    {"tenant_id": selected_tenant, "user_id": user_id.strip() or "guest"},
                )
            )
        except Exception as exc:
            st.error(str(exc))

with tab_tenants:
    st.subheader("Tenant configuration")
    tenant_configs = load_tenant_configs()

    if not tenant_configs:
        st.info("No tenant configuration is available yet.")
    else:
        st.dataframe(
            [
                {
                    "tenant_id": tenant_id,
                    "display_name": cfg.get("display_name", tenant_id),
                    "domain_id": cfg.get("domain_id", DEFAULT_UI_DOMAIN_ID),
                    "domain_name": cfg.get("domain_name", DEFAULT_UI_DOMAIN_NAME),
                    "model_name": cfg.get("model_name", DEFAULT_UI_MODEL),
                    "model_class": cfg.get("model_class", DEFAULT_UI_MODEL_CLASS),
                    "llm_backend": cfg.get("llm_backend", DEFAULT_UI_BACKEND),
                    "adapter_name": cfg.get("adapter_name", "base"),
                    "top_k": cfg.get("top_k", 4),
                    "chunk_size": cfg.get("chunk_size", 700),
                    "chunk_overlap": cfg.get("chunk_overlap", 120),
                    "query_expansion": cfg.get("enable_query_expansion", False),
                    "hybrid": cfg.get("enable_hybrid_retrieval", False),
                    "reranker": cfg.get("enable_reranker", False),
                    "memory_turns": cfg.get("memory_turns", 6),
                }
                for tenant_id, cfg in sorted(tenant_configs.items())
            ],
            use_container_width=True,
        )

    st.markdown("### Update current tenant")
    current_cfg = tenant_configs.get(selected_tenant, {})
    with st.form("tenant_update_form"):
        display_name = st.text_input("Display name", value=current_cfg.get("display_name", selected_tenant))
        domain_id = st.text_input("Domain ID", value=current_cfg.get("domain_id", DEFAULT_UI_DOMAIN_ID))
        domain_name = st.text_input("Domain name", value=current_cfg.get("domain_name", DEFAULT_UI_DOMAIN_NAME))
        model_name = st.text_input("Model name", value=current_cfg.get("model_name", DEFAULT_UI_MODEL))
        model_class = st.selectbox(
            "Model class",
            ["light-latency", "balanced", "strong-quality", "adaptive", "custom"],
            index=["light-latency", "balanced", "strong-quality", "adaptive", "custom"].index(
                current_cfg.get("model_class", DEFAULT_UI_MODEL_CLASS)
                if current_cfg.get("model_class", DEFAULT_UI_MODEL_CLASS) in ["light-latency", "balanced", "strong-quality", "adaptive", "custom"]
                else DEFAULT_UI_MODEL_CLASS
            ),
        )
        llm_backend = st.selectbox(
            "LLM backend",
            ["ollama", "vllm"],
            index=0 if current_cfg.get("llm_backend", DEFAULT_UI_BACKEND) != "vllm" else 1,
        )
        adapter_name = st.text_input("Adapter name", value=current_cfg.get("adapter_name", "base"))
        top_k = st.number_input("Top K", min_value=1, max_value=20, value=int(current_cfg.get("top_k", 4)))
        chunk_size = st.number_input("Chunk size", min_value=128, max_value=2000, value=int(current_cfg.get("chunk_size", 700)), step=50)
        chunk_overlap = st.number_input("Chunk overlap", min_value=0, max_value=500, value=int(current_cfg.get("chunk_overlap", 120)), step=10)
        memory_turns = st.number_input(
            "Memory turns",
            min_value=1,
            max_value=30,
            value=int(current_cfg.get("memory_turns", 6)),
        )
        enable_query_expansion = st.checkbox("Enable query expansion", value=bool(current_cfg.get("enable_query_expansion", False)))
        enable_hybrid_retrieval = st.checkbox("Enable hybrid retrieval", value=bool(current_cfg.get("enable_hybrid_retrieval", False)))
        enable_reranker = st.checkbox("Enable reranker", value=bool(current_cfg.get("enable_reranker", False)))
        query_expansion_count = st.number_input(
            "Query expansion count",
            min_value=1,
            max_value=8,
            value=int(current_cfg.get("query_expansion_count", 4)),
        )
        hybrid_alpha = st.number_input(
            "Hybrid alpha",
            min_value=0.0,
            max_value=1.0,
            value=float(current_cfg.get("hybrid_alpha", 0.55)),
            step=0.05,
        )
        reranker_top_n = st.number_input(
            "Reranker top N",
            min_value=1,
            max_value=20,
            value=int(current_cfg.get("reranker_top_n", 8)),
        )
        language_hint = st.text_input(
            "Language hint",
            value=current_cfg.get("language_hint", "Automatically follow the question language"),
        )
        persona = st.text_area(
            "Persona",
            value=current_cfg.get("persona", "You are an enterprise support assistant."),
            height=120,
        )
        submitted = st.form_submit_button("Save tenant config")
        if submitted:
            tenant_configs[selected_tenant] = {
                "display_name": display_name.strip() or selected_tenant,
                "domain_id": normalize_tenant_id(domain_id.strip() or DEFAULT_UI_DOMAIN_ID),
                "domain_name": domain_name.strip() or DEFAULT_UI_DOMAIN_NAME,
                "persona": persona.strip(),
                "language_hint": language_hint.strip() or "Auto",
                "top_k": int(top_k),
                "chunk_size": int(chunk_size),
                "chunk_overlap": int(chunk_overlap),
                "memory_turns": int(memory_turns),
                "model_name": model_name.strip() or DEFAULT_UI_MODEL,
                "shared_model_name": model_name.strip() or DEFAULT_UI_MODEL,
                "model_class": model_class,
                "llm_backend": llm_backend,
                "adapter_name": adapter_name.strip() or "base",
                "enable_query_expansion": bool(enable_query_expansion),
                "enable_hybrid_retrieval": bool(enable_hybrid_retrieval),
                "enable_reranker": bool(enable_reranker),
                "query_expansion_count": int(query_expansion_count),
                "hybrid_alpha": float(hybrid_alpha),
                "reranker_top_n": int(reranker_top_n),
            }
            save_tenant_configs(tenant_configs)
            st.success("Saved tenants.json.")

    st.markdown("### Create a new tenant")
    with st.form("tenant_create_form"):
        raw_tenant_id = st.text_input("New tenant ID (free text)")
        tenant_display = st.text_input("New tenant display name")
        tenant_domain_id = st.text_input("New tenant domain ID", value=DEFAULT_UI_DOMAIN_ID)
        tenant_domain_name = st.text_input("New tenant domain name", value=DEFAULT_UI_DOMAIN_NAME)
        create_submitted = st.form_submit_button("Create tenant")
        if create_submitted:
            tenant_id = normalize_tenant_id(raw_tenant_id.strip())
            if tenant_id in tenant_configs:
                st.warning(f"Tenant `{tenant_id}` already exists.")
            else:
                tenant_configs[tenant_id] = {
                    "display_name": tenant_display.strip() or tenant_id,
                    "domain_id": normalize_tenant_id(tenant_domain_id.strip() or DEFAULT_UI_DOMAIN_ID),
                    "domain_name": tenant_domain_name.strip() or DEFAULT_UI_DOMAIN_NAME,
                    "persona": "You are an enterprise support assistant.",
                    "language_hint": "Automatically follow the question language",
                    "top_k": 5,
                    "chunk_size": 700,
                    "chunk_overlap": 120,
                    "memory_turns": 6,
                    "model_name": DEFAULT_UI_MODEL,
                    "shared_model_name": DEFAULT_UI_MODEL,
                    "model_class": DEFAULT_UI_MODEL_CLASS,
                    "llm_backend": DEFAULT_UI_BACKEND,
                    "adapter_name": "base",
                    "enable_query_expansion": False,
                    "enable_hybrid_retrieval": False,
                    "enable_reranker": False,
                    "query_expansion_count": 4,
                    "hybrid_alpha": 0.55,
                    "reranker_top_n": 8,
                }
                save_tenant_configs(tenant_configs)
                st.success(f"Created tenant `{tenant_id}`. Reload the page to see it in the dropdown.")

with tab_lora:
    st.subheader("LoRA workspace")
    st.caption(
        "This workspace follows Checklist 3: source data, QA datasets, cleaned LoRA datasets, adapters, and reports "
        "are all grouped under `supporting_personalization_assets/` by tenant."
    )

    ensure_personalization_dirs(selected_tenant)
    source_dir = tenant_source_dir(selected_tenant)
    generated_path = generated_qa_path(selected_tenant)
    lora_path = lora_dataset_path(selected_tenant)
    lora_clean_path = lora_clean_dataset_path(selected_tenant)
    adapter_dir = tenant_adapter_dir(selected_tenant)
    report_path = lora_training_report_path(selected_tenant)

    st.markdown("### Tenant currently preparing personalization")
    st.code(
        "\n".join(
            [
                f"tenant_id = {selected_tenant}",
                f"source_dir = {source_dir}",
                f"generated_qa = {generated_path}",
                f"lora_dataset = {lora_path}",
                f"lora_dataset_clean = {lora_clean_path}",
                f"adapter_dir = {adapter_dir}",
            ]
        ),
        language="text",
    )

    uploader = st.file_uploader(
        "Upload txt files for the current tenant's supporting_personalization_dataset",
        type=["txt"],
        accept_multiple_files=True,
    )
    if uploader:
        saved = 0
        for item in uploader:
            target = source_dir / item.name
            target.write_bytes(item.getbuffer())
            saved += 1
        st.success(f"Saved {saved} files to {source_dir}.")

    txt_files: List[Path] = sorted(source_dir.glob("*.txt"))
    st.markdown("### Available source files")
    if txt_files:
        st.dataframe(
            [{"file": p.name, "size_kb": round(p.stat().st_size / 1024, 2)} for p in txt_files],
            use_container_width=True,
        )
    else:
        st.info("No txt files exist yet for this tenant under supporting_personalization_assets/data/<tenant>/files.")

    action_col1, action_col2, action_col3 = st.columns(3)
    with action_col1:
        if st.button("Run supporting_personalization_dataset", use_container_width=True):
            with st.spinner("Running supporting_personalization_dataset..."):
                code, output = run_supporting_personalization_dataset(selected_tenant)
            if code == 0:
                st.success("Pipeline1 completed successfully.")
            else:
                st.error(f"Pipeline1 failed (exit code {code}).")
            st.code(output or "(no output)", language="text")
    with action_col2:
        if st.button("Clean the LoRA dataset", use_container_width=True):
            with st.spinner("Cleaning the dataset..."):
                code, output = run_clean_lora_dataset(selected_tenant)
            if code == 0:
                st.success("Cleaned the LoRA dataset.")
            else:
                st.error(f"Dataset cleaning failed (exit code {code}).")
            st.code(output or "(no output)", language="text")
    with action_col3:
        if st.button("Train LoRA prototype", use_container_width=True):
            with st.spinner("Training the lightweight adapter..."):
                code, output = run_lora_training(selected_tenant)
            if code == 0:
                st.success("LoRA training finished.")
            else:
                st.error(f"LoRA training failed (exit code {code}).")
            st.code(output or "(no output)", language="text")

    st.markdown("### Dataset status")
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric("generated_qa.json records", count_json_records(generated_path))
        st.caption(str(generated_path))
    with col_b:
        st.metric("lora_dataset.json records", count_json_records(lora_path))
        st.caption(str(lora_path))
    with col_c:
        st.metric("lora_dataset_clean.json records", count_json_records(lora_clean_path))
        st.caption(str(lora_clean_path))

    st.markdown("### Adapter and report")
    adapter_col, report_col = st.columns(2)
    with adapter_col:
        st.metric("Adapter files", len(list(adapter_dir.glob("*"))) if adapter_dir.exists() else 0)
        st.caption(str(adapter_dir))
    with report_col:
        st.metric("Training report", "Available" if report_path.exists() else "Missing")
        st.caption(str(report_path))

    st.markdown("### Smoke test adapter")
    smoke_prompt = st.text_input(
        "Adapter test prompt",
        value="What is the company leave policy?",
        key=f"lora_smoke_prompt::{selected_tenant}",
    )
    if st.button("Test the current adapter", use_container_width=True):
        with st.spinner("Running the adapter smoke test..."):
            code, output = run_lora_smoke_test(selected_tenant, smoke_prompt)
        if code == 0:
            st.success("Adapter smoke test completed.")
        else:
            st.error(f"Adapter smoke test failed (exit code {code}).")
        st.code(output or "(no output)", language="text")

    st.markdown(
        "Recommended Checklist 3 flow: `supporting_personalization_dataset` generates tenant-specific QA and LoRA datasets, "
        "then the dataset is cleaned, an adapter is trained into `supporting_personalization_assets/adapters/<tenant_id>/`, and finally `adapter_name` is updated in the tenant config."
    )
