from __future__ import annotations

import ast
import re
import unicodedata
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup

from enterprise_runtime.config import load_tenant_configs
from enterprise_runtime.ingestion import (
    list_real_files,
    read_links,
    selected_shared_files_dir,
    selected_shared_links_file,
    tenant_files_dir,
    tenant_links_file,
)
from enterprise_runtime.models import TenantProfile
from enterprise_runtime.runtime_manager import RUNTIME_CACHE, build_runtime
from enterprise_runtime.utils import HAS_PSUTIL, HAS_SCHEDULER, format_ram_usage, get_ram_usage, now_str


_ALLOWED_BINOPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a ** b,
}
_ALLOWED_UNARYOPS = {
    ast.UAdd: lambda a: +a,
    ast.USub: lambda a: -a,
}

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_FILE_HINT_RE = re.compile(r"[\w\-.]+\.(?:xlsx|xls|csv|pdf|docx|doc|txt|md)", re.IGNORECASE)
_CROSS_TENANT_BOUNDARY_TERMS = {
    "other tenant",
    "tenant `",
    "other tenant data",
    "no access permission",
    "access denied",
    "cannot access",
    "private authentication token",
    "private internal document",
    "private note",
}

EXCEL_HEADER_KEYWORDS = {
    "term", "class_code", "course_code", "course_id", "class_id",
    "course_name", "course_name_en", "day", "time", "room", "status", "class_type", "session_number",
    "school_unit", "faculty", "department", "employee_id", "department_name", "leave_type",
    "policy_id", "sop_id", "checklist", "risk", "control", "compliance", "audit",
    "vendor_id", "supplier", "invoice_id", "po", "purchase_order",
    "contract_id", "procurement", "approval",
}


def _eval_ast(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_ast(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.Num):
        return node.n
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        return _ALLOWED_BINOPS[type(node.op)](_eval_ast(node.left), _eval_ast(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
        return _ALLOWED_UNARYOPS[type(node.op)](_eval_ast(node.operand))
    raise ValueError("Unsupported expression")


def safe_calculate(expr: str) -> str:
    try:
        parsed = ast.parse(expr, mode="eval")
        value = _eval_ast(parsed)
        return str(value)
    except Exception as exc:
        return f"Error: {exc}"


def tool_current_time() -> str:
    return f"Current time: {now_str()}"


def tool_list_docs(profile: TenantProfile) -> str:
    shared_dir = selected_shared_files_dir()
    tenant_dir = tenant_files_dir(profile.tenant_id)
    shared_docs = [p.name for p in list_real_files(shared_dir)] if shared_dir else []
    tenant_docs = [p.name for p in list_real_files(tenant_dir)]
    shared_links = read_links(selected_shared_links_file())
    tenant_links = read_links(tenant_links_file(profile.tenant_id))

    return (
        f"--- DATA INVENTORY ---\n"
        f"Shared files: {shared_docs or '[]'}\n"
        f"Tenant files: {tenant_docs or '[]'}\n"
        f"Shared links: {shared_links or '[]'}\n"
        f"Tenant links: {tenant_links or '[]'}"
    )


def tool_list_tenants() -> str:
    configs = load_tenant_configs()
    return f"Tenant list: {list(configs.keys())}"


def tool_status(profile: TenantProfile, user_id: str) -> str:
    rt = RUNTIME_CACHE.get(profile.tenant_id)
    ram = format_ram_usage(get_ram_usage())
    return (
        f"--- STATUS ---\n"
        f"Tenant: {profile.tenant_id}\n"
        f"Domain: {profile.domain_id} ({profile.domain_name})\n"
        f"User: {user_id}\n"
        f"RAM: {ram}\n"
        f"Docs: {rt.document_count if rt else 'N/A'}\n"
        f"Nodes: {rt.node_count if rt else 'N/A'}\n"
        f"Loaded at: {rt.loaded_at if rt else 'N/A'}\n"
        f"Model: {profile.shared_model_name or profile.model_name}\n"
        f"Model class: {profile.model_class}\n"
        f"LLM backend: {profile.llm_backend}\n"
        f"Scheduler: {'enabled' if HAS_SCHEDULER else 'unavailable'}\n"
        f"psutil: {'enabled' if HAS_PSUTIL else 'unavailable'}"
    )


def tool_refresh(profile: TenantProfile) -> str:
    rt = build_runtime(profile, force_rebuild=True)
    return f"Runtime data was refreshed at {rt.loaded_at}."


def _normalize_text(text: Any) -> str:
    s = "" if text is None else str(text)
    s = " ".join(s.replace("\n", " ").replace("\r", " ").split()).strip()
    return s


def _normalize_key(text: Any) -> str:
    s = _normalize_text(text).lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("\u0111", "d")
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def _describe_file_question_detected(question: str) -> bool:
    q = question.lower().strip()

    if not _FILE_HINT_RE.search(question) and any(term in q for term in _CROSS_TENANT_BOUNDARY_TERMS):
        return False

    patterns = [
        "what does this file contain",
        "what is in this file",
        "what is this file about",
        "what does this excel file contain",
        "what is in this excel file",
        "what does this csv file contain",
        "what is in this csv file",
        "what is this pdf about",
        "what does this pdf contain",
        "what is this document about",
        "what is this text about",
        "what is this link about",
        "what does this link contain",
        "describe file",
        "summarize file",
    ]

    if any(p in q for p in patterns):
        return True

    file_words = ["file", "excel", "csv", "pdf", "link", "url", "document", "text", "sheet"]
    intent_words = ["contain", "contains", "about", "content", "summary", "summarize", "describe"]

    return any(w in q for w in file_words) and any(w in q for w in intent_words)


def _file_update_question_detected(question: str) -> bool:
    q = question.lower().strip()
    update_terms = [
        "updated when",
        "update date",
        "last updated",
        "modified date",
    ]
    file_words = ["file", "excel", "csv", "pdf", "xlsx", "xls", "document", "text", "schedule"]
    return any(term in q for term in update_terms) and (
        _FILE_HINT_RE.search(question) or any(word in q for word in file_words)
    )


def _excel_question_detected(question: str) -> bool:
    q = question.lower()

    file_hints = [match.group(0).lower() for match in _FILE_HINT_RE.finditer(question)]
    if any(hint.endswith((".xlsx", ".xls", ".csv")) for hint in file_hints):
        return True
    if file_hints and not any(term in q for term in {"excel", "xlsx", "xls", "csv", "sheet", "table"}):
        return False

    excel_terms = [
        "excel",
        "xlsx",
        "xls",
        "csv",
        "sheet",
        "spreadsheet",
        "which column",
        "which columns",
        "what data does it contain",
        "what data is included",
        "dataset",
        "schedule",
        "how many classes",
        "which day",
        "list courses",
        "course code",
        "read course information",
        "course information",
        "course",
        "employee",
        "leave",
        "policy",
        "sop",
        "compliance",
        "audit",
        "vendor",
        "supplier",
        "invoice",
        "contract",
        "procurement",
        "purchase order",
        "vendor",
        "approval",
    ]

    if any(term in q for term in excel_terms):
        return True

    if "course" in q and "http" not in q and "link" not in q:
        return True

    return False


def _link_question_detected(question: str) -> bool:
    q = question.lower()
    if _URL_RE.search(question):
        return True
    link_terms = [
        "link",
        "url",
        "website",
        "this website",
        "this page",
        "link content",
    ]
    return any(term in q for term in link_terms)


def _extract_keywords_from_text(text: str, top_k: int = 8) -> List[str]:
    stopwords = {
        "the", "and", "for", "with", "from", "this", "that", "are", "was", "were",
        "http", "https", "www", "com", "org", "net", "pdf", "file", "sheet",
    }
    words = re.findall(r"\b\w+\b", text.lower())
    words = [w for w in words if len(w) >= 3 and w not in stopwords and not w.isdigit()]
    freq = Counter(words)
    return [w for w, _ in freq.most_common(top_k)]


def _candidate_data_files(profile: TenantProfile) -> List[Path]:
    files: List[Path] = []
    shared_dir = selected_shared_files_dir()
    if shared_dir:
        files.extend(list_real_files(shared_dir))
    files.extend(list_real_files(tenant_files_dir(profile.tenant_id)))
    return files


def _candidate_excel_files(profile: TenantProfile) -> List[Path]:
    return [p for p in _candidate_data_files(profile) if p.suffix.lower() in {".xlsx", ".xls", ".csv"}]


def _extract_requested_file_hints(question: str, extensions: str = r"(?:xlsx|xls|csv|pdf|docx|doc|txt|md)") -> List[str]:
    pattern = re.compile(rf"[\w\-.]+\.{extensions}", re.IGNORECASE)
    return list(dict.fromkeys(match.lower() for match in pattern.findall(question or "")))


def _tenant_scoped_access_denied_message(profile: TenantProfile, requested_name: str) -> str:
    return (
        f"Cannot access file `{requested_name}` from the current tenant `{profile.tenant_id}`. "
        "The tool may only use shared files or files that belong to the current tenant, not another tenant's data."
    )


def _choose_target_file(question: str, profile: TenantProfile) -> Optional[Path]:
    files = _candidate_data_files(profile)
    if not files:
        return None

    q = question.lower()
    normalized_q = _normalize_key(q)
    hinted = _extract_requested_file_hints(q)
    if hinted:
        for f in files:
            if f.name.lower() in hinted:
                return f
        return None

    for f in files:
        stem_key = _normalize_key(f.stem)
        if stem_key and stem_key in normalized_q:
            return f
        parts = [part for part in stem_key.split("_") if len(part) >= 4]
        if parts and all(part in normalized_q for part in parts[:2]):
            return f

    priority_suffixes: List[str] = []
    if any(k in q for k in ["excel", "xlsx", "xls"]):
        priority_suffixes = [".xlsx", ".xls"]
    elif "csv" in q:
        priority_suffixes = [".csv"]
    elif "pdf" in q:
        priority_suffixes = [".pdf"]

    for suffix in priority_suffixes:
        for f in files:
            if f.suffix.lower() == suffix:
                return f

    explicit_reference = any(word in q for word in ["file", "pdf", "excel", "csv", "document", "text"])
    if explicit_reference and len(files) == 1:
        return files[0]
    return None


def _choose_excel_file(question: str, profile: TenantProfile) -> Optional[Path]:
    files = _candidate_excel_files(profile)
    if not files:
        return None

    q = question.lower()
    hinted = _extract_requested_file_hints(q, extensions=r"(?:xlsx|xls|csv)")
    if hinted:
        for f in files:
            if f.name.lower() in hinted:
                return f
        return None

    for f in files:
        if f.name.lower() in q:
            return f

    return files[0]


def _header_row_score(row_values: List[Any]) -> float:
    cells = [_normalize_text(v) for v in row_values]
    non_empty = [c for c in cells if c]
    if not non_empty:
        return -1.0

    score = len(non_empty) * 1.5
    lowered = [_normalize_key(c) for c in non_empty]

    for cell in lowered:
        if cell in EXCEL_HEADER_KEYWORDS:
            score += 5
        if any(k in cell for k in [
            "ma_lop", "ma_hp", "ten_hp", "ten_hp_tieng_anh", "thoi_gian", "phong",
            "trang_thai", "loai_lop", "buoi_so", "truong_vien_khoa", "khoi_luong",
            "vien", "khoa", "thu",
        ]):
            score += 4
        if re.fullmatch(r"\d{4,}", cell):
            score -= 3
        if len(cell) > 60:
            score -= 2

    joined = " ".join(lowered)
    if "thoi_khoa_bieu" in joined:
        score -= 4
    if "ky" in lowered or "truong_vien_khoa" in lowered:
        score += 2
    return score


def _make_unique_headers(values: List[Any]) -> List[str]:
    used: Dict[str, int] = {}
    headers: List[str] = []
    for idx, value in enumerate(values, start=1):
        raw = _normalize_text(value)
        if not raw:
            raw = f"Unnamed_{idx}"
        base = raw
        count = used.get(base, 0)
        if count:
            raw = f"{base}_{count + 1}"
        used[base] = count + 1
        headers.append(raw)
    return headers


def _read_csv_clean(path: Path) -> Tuple[pd.DataFrame, int, str]:
    df = pd.read_csv(path)
    df = df.dropna(axis=1, how="all")
    df = df.dropna(axis=0, how="all").reset_index(drop=True)
    title = path.stem
    return df, 0, title


def _read_excel_sheet_clean(path: Path, sheet_name: str) -> Tuple[pd.DataFrame, int, str]:
    if path.suffix.lower() == ".csv":
        return _read_csv_clean(path)

    raw = pd.read_excel(path, sheet_name=sheet_name, header=None)
    raw = raw.dropna(axis=1, how="all")
    raw = raw.dropna(axis=0, how="all").reset_index(drop=True)

    if raw.empty:
        return raw, 0, ""

    title = _normalize_text(raw.iloc[0, 0]) if raw.shape[0] > 0 else ""

    candidate_rows = min(len(raw), 12)
    best_idx = 0
    best_score = float("-inf")
    for idx in range(candidate_rows):
        score = _header_row_score(raw.iloc[idx].tolist())
        if score > best_score:
            best_score = score
            best_idx = idx

    headers = _make_unique_headers(raw.iloc[best_idx].tolist())
    df = raw.iloc[best_idx + 1 :].copy().reset_index(drop=True)
    df.columns = headers
    df = df.dropna(axis=0, how="all")

    keep_cols: List[str] = []
    for col in df.columns:
        series = df[col]
        non_null_ratio = 1.0 - float(series.isna().mean()) if len(series) else 0.0
        if str(col).startswith("Unnamed_") and non_null_ratio < 0.2:
            continue
        keep_cols.append(col)
    df = df[keep_cols]

    return df, best_idx, title


def _dataset_kind(title: str, columns: List[str], path: Path) -> str:
    title_key = _normalize_key(title)
    cols_key = [_normalize_key(c) for c in columns]
    joined = " ".join(cols_key)
    name_key = _normalize_key(path.stem)

    if "thoi_khoa_bieu" in title_key or "thoi_khoa_bieu" in name_key:
        match = re.search(r"ky[_ ]?(\d{4,6})", title_key or name_key)
        ky = match.group(1) if match else ""
        return f"planned course schedule for term {ky}".strip()
    if "ma_hp" in joined and ("thu" in joined or "thoi_gian" in joined):
        return "course schedule data"
    if "diem" in joined:
        return "grades or academic results"
    if "hoc_phi" in joined:
        return "tuition data"
    if any(term in joined for term in ["employee", "nhan_vien", "leave", "nghi_phep", "payroll", "benefit"]):
        return "HR data"
    if any(term in joined for term in ["vendor", "supplier", "invoice", "purchase_order", "contract", "procurement"]):
        return "procurement / vendor / contract data"
    if any(term in joined for term in ["policy", "sop", "compliance", "audit", "risk", "control", "checklist"]):
        return "policy / compliance / SOP data"
    return "internal structured data"


def _group_columns(columns: List[str]) -> List[str]:
    col_keys = {_normalize_key(c): c for c in columns}
    keys = list(col_keys.keys())
    groups: List[str] = []

    def has(*patterns: str) -> bool:
        return any(any(p in key for p in patterns) for key in keys)

    if has("truong_vien_khoa", "vien", "khoa"):
        groups.append("School, faculty, or department")
    if has("ma_lop", "ma_lop_kem"):
        groups.append("Class code and linked class code")
    if has("ma_hp", "ten_hp", "ten_hp_tieng_anh"):
        groups.append("Course code, course name, and English title")
    if has("khoi_luong", "ghi_chu"):
        groups.append("Course load and class notes")
    if has("buoi_so", "thu", "thoi_gian", "bd", "kt", "kip", "tuan"):
        groups.append("Scheduling fields: session number, weekday, time, slot, week")
    if has("phong", "can_tn", "sldk", "sl_max", "trang_thai", "loai_lop", "dot_mo"):
        groups.append("Rooms, registration capacity, and class status")
    if has("employee", "nhan_vien", "department", "phong_ban", "role", "position"):
        groups.append("Human resources: employee ID, department, role/title")
    if has("leave", "nghi_phep", "absence", "benefit", "payroll", "salary"):
        groups.append("HR policy: leave, benefits, payroll, or absence")
    if has("vendor", "supplier", "nha_cung_cap", "invoice", "purchase_order", "po", "contract"):
        groups.append("Procurement: vendors, invoices, purchase orders, contracts")
    if has("policy", "sop", "compliance", "audit", "risk", "control", "checklist"):
        groups.append("Compliance/SOP: policy, control, risk, checklist")

    if not groups:
        groups.append("Key columns: " + ", ".join(map(str, columns[:6])))

    return groups


def _sample_values(df: pd.DataFrame, col_patterns: List[str], limit: int = 3) -> List[str]:
    target_cols = [c for c in df.columns if any(p in _normalize_key(c) for p in col_patterns)]
    if not target_cols:
        return []

    values: List[str] = []
    for col in target_cols:
        for v in df[col].dropna().astype(str):
            v = _normalize_text(v)
            if not v or v.lower() == "nan":
                continue
            if v not in values:
                values.append(v)
            if len(values) >= limit:
                return values
    return values


def _guess_table_column_roles(columns: List[str]) -> Dict[str, List[str]]:
    roles: Dict[str, List[str]] = {
        "code": [],
        "name": [],
        "category": [],
        "quantity": [],
        "price": [],
        "time": [],
        "location": [],
        "status": [],
        "unit": [],
        "other": [],
    }

    for col in columns:
        key = _normalize_key(col)

        if any(k in key for k in ["ma", "code", "sku", "id"]):
            roles["code"].append(str(col))
        elif any(k in key for k in ["ten", "name", "mo_ta", "description"]):
            roles["name"].append(str(col))
        elif any(k in key for k in ["loai", "nhom", "category", "brand"]):
            roles["category"].append(str(col))
        elif any(k in key for k in ["so_luong", "quantity", "stock", "ton"]):
            roles["quantity"].append(str(col))
        elif any(k in key for k in ["gia", "price", "doanh_thu", "revenue", "cost"]):
            roles["price"].append(str(col))
        elif any(k in key for k in ["ngay", "date", "time", "thoi_gian", "thu", "kip"]):
            roles["time"].append(str(col))
        elif any(k in key for k in ["dia_diem", "chi_nhanh", "store", "location", "phong"]):
            roles["location"].append(str(col))
        elif any(k in key for k in ["trang_thai", "status"]):
            roles["status"].append(str(col))
        elif any(k in key for k in ["vien", "khoa", "unit", "department"]):
            roles["unit"].append(str(col))
        else:
            roles["other"].append(str(col))

    return roles


def _format_table_inspection(path: Path, df: pd.DataFrame, source_name: str, header_note: str = "") -> str:
    if df.empty:
        return f"File `{source_name}` does not currently expose a clear enough table structure to describe."

    columns = [str(c) for c in df.columns.tolist()]
    roles = _guess_table_column_roles(columns)

    sample_info: List[str] = []
    for role in ["code", "name", "category", "unit", "quantity", "price", "time", "location", "status"]:
        cols = roles.get(role, [])
        if not cols:
            continue
        col = cols[0]
        vals = []
        for v in df[col].dropna().astype(str):
            v = _normalize_text(v)
            if v and v not in vals:
                vals.append(v)
            if len(vals) >= 3:
                break
        if vals:
            sample_info.append(f"- Column `{col}` includes example values: {', '.join(vals)}")

    keywords = _extract_keywords_from_text(
        " ".join(columns + [str(v) for v in df.head(20).fillna("").astype(str).values.flatten()])
    )

    group_lines: List[str] = []
    if roles["code"]:
        group_lines.append("- Code or ID fields")
    if roles["name"]:
        group_lines.append("- Name or description fields")
    if roles["category"]:
        group_lines.append("- Category fields")
    if roles["quantity"]:
        group_lines.append("- Quantity or inventory fields")
    if roles["price"]:
        group_lines.append("- Value, price, or revenue fields")
    if roles["time"]:
        group_lines.append("- Time or schedule fields")
    if roles["location"]:
        group_lines.append("- Location, branch, or room fields")
    if roles["status"]:
        group_lines.append("- Status fields")
    if roles["unit"]:
        group_lines.append("- Unit, department, or faculty fields")
    if not group_lines:
        group_lines.append("- General structured table fields")

    lines: List[str] = []
    lines.append(f"File `{source_name}` is a **structured data table**.")
    lines.append("")
    lines.append(f"- Data rows: **{len(df):,}**")
    lines.append(f"- Useful columns: **{len(columns)}**")
    lines.append(f"- Example key columns: {', '.join(columns[:12])}")

    if header_note:
        lines.append(f"- File-reading note: {header_note}")

    lines.append("")
    lines.append("The file appears to contain information grouped into categories such as:")
    lines.extend(group_lines)

    if keywords:
        lines.append("")
        lines.append("Notable keywords inferred from the data:")
        lines.append("- " + ", ".join(keywords[:8]))

    if sample_info:
        lines.append("")
        lines.append("Example values in the table:")
        lines.extend(sample_info[:6])

    return "\n".join(lines)


def _inspect_excel_csv(path: Path) -> str:
    try:
        if path.suffix.lower() == ".csv":
            df, _, _ = _read_csv_clean(path)
            return _format_table_inspection(path, df, path.name)

        workbook = pd.ExcelFile(path)
        best_sheet = None
        best_df = None
        best_score = -1
        best_header_note = ""

        for sheet in workbook.sheet_names:
            try:
                df, header_row_idx, _ = _read_excel_sheet_clean(path, sheet)
                if df.empty:
                    continue

                score = len(df.columns) + min(len(df), 1000) / 1000.0
                score += _score_sheet(df, "describe file")

                if score > best_score:
                    best_score = score
                    best_sheet = sheet
                    best_df = df
                    best_header_note = (
                        f"selected sheet `{sheet}` as the representative sheet"
                        + (
                            f", automatically skipping about {header_row_idx} leading header/subtitle rows"
                            if header_row_idx > 0 else ""
                        )
                    )
            except Exception:
                continue

        if best_df is None or best_df.empty:
            return f"Excel file `{path.name}` did not yield a clear table structure."

        result = _format_table_inspection(path, best_df, path.name, best_header_note)

        if len(workbook.sheet_names) > 1:
            result += f"\n\nThe workbook also contains **{len(workbook.sheet_names)} sheets**: " + ", ".join(workbook.sheet_names[:10])

        return result
    except Exception as exc:
        return f"Error while analyzing table file `{path.name}`: {exc}"


def _inspect_pdf(path: Path) -> str:
    try:
        import pypdf

        reader = pypdf.PdfReader(str(path))
        page_count = len(reader.pages)

        extracted_pages: List[str] = []
        for page in reader.pages[:5]:
            try:
                extracted_pages.append(page.extract_text() or "")
            except Exception:
                continue

        text = "\n".join(extracted_pages)
        text = " ".join(text.split())
        if not text:
            return f"PDF file `{path.name}` has {page_count} pages, but no readable text could be extracted."

        title_candidates = re.findall(r"[A-Z][^\n]{10,120}", text[:1000])
        title = title_candidates[0].strip() if title_candidates else path.stem

        keywords = _extract_keywords_from_text(text, top_k=10)
        preview = text[:1200]

        lines = [
            f"PDF file `{path.name}` is a **text document** with approximately **{page_count} pages**.",
            "",
            f"- Title or main-topic hint: **{title}**",
        ]
        if keywords:
            lines.append(f"- Notable keywords: {', '.join(keywords[:10])}")
        lines.extend([
            "",
            "Representative excerpt from the document:",
            preview,
        ])
        return "\n".join(lines)
    except Exception as exc:
        return f"Error while analyzing PDF `{path.name}`: {exc}"


def _inspect_generic_text_file(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        text = " ".join(text.split())
        if not text:
            return f"File `{path.name}` does not contain readable text."

        keywords = _extract_keywords_from_text(text, top_k=10)
        lines = [
            f"File `{path.name}` is a **text file**.",
            "",
            f"- Estimated length: **{len(text):,} characters**",
        ]
        if keywords:
            lines.append(f"- Notable keywords: {', '.join(keywords[:10])}")
        lines.extend([
            "",
            "Representative excerpt:",
            text[:1200],
        ])
        return "\n".join(lines)
    except Exception as exc:
        return f"Error while reading text file `{path.name}`: {exc}"


def _format_excel_summary(path: Path) -> str:
    try:
        if path.suffix.lower() == ".csv":
            df, _, title = _read_csv_clean(path)
            if df.empty:
                return f"CSV file `{path.name}` does not contain any data to analyze."

            columns = list(df.columns)
            kind = _dataset_kind(title, columns, path)
            groups = _group_columns(columns)

            lines: List[str] = []
            lines.append(f"This CSV file contains **{kind}**.")
            lines.append("")
            lines.append("The data is organized into groups such as:")
            for group in groups:
                lines.append(f"- {group}")
            lines.append("")
            lines.append(f"The file currently contains about **{len(df):,} data rows** and **{len(columns)} useful columns**.")
            return "\n".join(lines).strip()

        workbook = pd.ExcelFile(path)
        sheet_names = workbook.sheet_names
        if not sheet_names:
            return f"Excel file `{path.name}` does not contain any sheets to analyze."

        sheet_summaries: List[str] = []
        primary_df: Optional[pd.DataFrame] = None
        primary_title = ""
        primary_header_row = 0
        primary_sheet = sheet_names[0]

        for sheet in sheet_names[:5]:
            try:
                df, header_row_idx, title = _read_excel_sheet_clean(path, sheet)
            except Exception as exc:
                sheet_summaries.append(f"- Sheet '{sheet}': unreadable ({exc})")
                continue

            if primary_df is None and not df.empty:
                primary_df = df
                primary_title = title
                primary_header_row = header_row_idx
                primary_sheet = sheet

            sheet_summaries.append(f"- Sheet '{sheet}': {len(df):,} data rows, {len(df.columns)} useful columns")

        if primary_df is None or primary_df.empty:
            return (
                f"The Excel file `{path.name}` was opened, but no clear table structure could be extracted. "
                f"You may need to specify the sheet name or normalize the file layout."
            )

        columns = list(primary_df.columns)
        kind = _dataset_kind(primary_title, columns, path)
        groups = _group_columns(columns)
        course_examples = _sample_values(primary_df, ["ten_hp", "ten_hoc_phan"], limit=3)
        unit_examples = _sample_values(primary_df, ["truong_vien_khoa", "vien", "khoa"], limit=3)

        lines: List[str] = []
        lines.append(f"This Excel file primarily contains **{kind}**.")

        lines.append("")
        lines.append("The data is organized into groups such as:")
        for group in groups:
            lines.append(f"- {group}")

        if course_examples:
            lines.append("")
            lines.append("Example courses found in the data:")
            for item in course_examples:
                lines.append(f"- {item}")

        if unit_examples:
            lines.append("")
            lines.append("Example units or faculties found in the data:")
            for item in unit_examples:
                lines.append(f"- {item}")

        lines.append("")
        lines.append(
            f"The primary sheet `{primary_sheet}` currently contains about **{len(primary_df):,} data rows** and **{len(columns)} useful columns**."
        )

        if primary_header_row > 0:
            lines.append(
                f"The parser automatically skipped about **{primary_header_row} leading header/subtitle rows** to locate a cleaner header row."
            )

        unnamed_cols = [c for c in columns if _normalize_key(c).startswith("unnamed")]
        if unnamed_cols:
            lines.append(
                "Some columns still have unclear names, so the header should be normalized if precise field extraction is required."
            )

        if len(sheet_names) > 1:
            lines.append("")
            lines.append(f"The workbook also contains **{len(sheet_names)} sheets**. Quick summary:")
            lines.extend(sheet_summaries)

        return "\n".join(lines).strip()
    except Exception as exc:
        return f"Error while reading Excel/CSV file `{path.name}`: {exc}"


def _excel_query_detect(question: str) -> Optional[Dict[str, Any]]:
    q = question.lower()

    if "which column" in q and "course code" in q:
        return {"type": "column_lookup", "field": "course_code"}

    code_match = re.search(r"(?:course code|code)\s+([a-z]{2,}\d{2,})", q)
    if code_match and any(term in q for term in ["what is the course name", "course name"]):
        return {"type": "course_name_by_code", "code": code_match.group(1).upper()}
    if code_match and any(term in q for term in ["when does it meet", "what time", "schedule", "meeting time"]):
        return {"type": "schedule_by_code", "code": code_match.group(1).upper()}

    if "how many classes" in q:
        m = re.search(r"([a-z]{2,}\d{2,})", q)
        if m:
            return {"type": "count", "code": m.group(1).upper()}

        m_name = re.search(r"how many classes (?:for|of) course\s+(.+)", q)
        if m_name:
            return {"type": "count_name", "name": m_name.group(1).strip()}

    if "which day" in q or ("meets on" in q and "day" in q):
        m = re.search(r"([a-z]{2,}\d{2,})", q)
        if m:
            return {"type": "day", "code": m.group(1).upper()}

        m_name = re.search(r"course\s+(.+?)\s+(?:meets on|meets).*", q)
        if m_name:
            return {"type": "day_name", "name": m_name.group(1).strip()}

    if "course information" in q or "read course information" in q or "details for course" in q:
        m_name = re.search(r"course\s+(.+)", q)
        if m_name:
            return {"type": "info_name", "name": m_name.group(1).strip()}

    if "list" in q and any(token in q for token in ["faculty", "department", "unit"]):
        unit_match = re.search(r"(?:faculty|department|unit)\s+([^\n,.;:]+)", q)
        unit = unit_match.group(1).strip() if unit_match else None
        return {"type": "list_unit", "unit": unit}

    if "course" in q and any(token in q for token in ["faculty", "department", "unit"]):
        unit_match = re.search(r"(?:faculty|department|unit)\s+([^\n,.;:]+)", q)
        unit = unit_match.group(1).strip() if unit_match else None
        return {"type": "list_unit", "unit": unit}

    return None


def _find_column(df: pd.DataFrame, keywords: List[str]) -> Optional[str]:
    for col in df.columns:
        key = _normalize_key(col)
        if any(k in key for k in keywords):
            return col
    return None


def _score_sheet(df: pd.DataFrame, question: str) -> int:
    score = 0
    q = question.lower()

    for col in df.columns:
        col_lower = str(col).lower()
        if any(k in col_lower for k in ["code", "id"]):
            score += 2
        if any(k in col_lower for k in ["name", "title", "description"]):
            score += 2
        if any(k in col_lower for k in ["day", "weekday"]):
            score += 2
        if any(k in col_lower for k in ["faculty", "department", "unit"]):
            score += 2
        if any(k in col_lower for k in ["room", "time", "session", "slot"]):
            score += 1

    if re.search(r"[a-z]{2,}\d{2,}", q):
        score += 2
    if "class" in q:
        score += 1
    if "course" in q:
        score += 1

    return score


def _select_best_sheet(path: Path, question: str) -> Tuple[Optional[str], Optional[pd.DataFrame]]:
    if path.suffix.lower() == ".csv":
        df, _, _ = _read_csv_clean(path)
        return path.stem, df

    workbook = pd.ExcelFile(path)

    best_score = -1
    best_sheet: Optional[str] = None
    best_df: Optional[pd.DataFrame] = None

    for sheet in workbook.sheet_names:
        try:
            df, _, _ = _read_excel_sheet_clean(path, sheet)
            if df.empty:
                continue

            score = _score_sheet(df, question)
            if score > best_score:
                best_score = score
                best_sheet = sheet
                best_df = df
        except Exception:
            continue

    return best_sheet, best_df


def _filter_contains(df: pd.DataFrame, col: str, value: str) -> pd.DataFrame:
    return df[df[col].astype(str).str.contains(value, case=False, na=False)]


def _run_excel_query(df: pd.DataFrame, query: Dict[str, Any]) -> str:
    ma_hp_col = _find_column(df, ["course_code", "course_id", "ma_hp", "ma_hoc_phan", "mahp"])
    thu_col = _find_column(df, ["day", "weekday", "thu"])
    unit_col = _find_column(df, ["school_unit", "faculty", "department", "unit", "vien", "khoa"])
    ten_hp_col = _find_column(df, ["course_name", "course_title", "ten_hp", "ten_hoc_phan", "ten"])
    ma_lop_col = _find_column(df, ["class_code", "class_id", "ma_lop"])
    thoi_gian_col = _find_column(df, ["meeting_time", "time", "schedule", "time_slot", "thoi_gian", "gio", "kip"])
    phong_col = _find_column(df, ["room", "location", "phong"])

    if query["type"] == "column_lookup":
        field = query.get("field")
        if field == "course_code":
            if ma_hp_col:
                return f"The column that stores the course code is `{ma_hp_col}`."
            return "Could not find a column that stores the course code."

    if query["type"] == "course_name_by_code":
        code = query["code"]
        if not ma_hp_col:
            return "Could not find the course-code column."
        if not ten_hp_col:
            return "Could not find the course-name column."
        subset = _filter_contains(df, ma_hp_col, code)
        if subset.empty:
            return f"No data was found for course code {code}."
        names = [str(x) for x in subset[ten_hp_col].dropna().astype(str).unique().tolist() if _normalize_text(x)]
        if not names:
            return f"Course code {code} was found, but no clear course name was available in the data."
        return f"Course code {code} corresponds to course name {names[0]}."

    if query["type"] == "schedule_by_code":
        code = query["code"]
        if not ma_hp_col:
            return "Could not find the course-code column."
        subset = _filter_contains(df, ma_hp_col, code)
        if subset.empty:
            return f"No data was found for course code {code}."

        parts: List[str] = [f"Course code {code} has the following schedule:"]
        if thu_col:
            days = [str(x) for x in subset[thu_col].dropna().astype(str).unique().tolist()[:5]]
            if days:
                parts.append(f"- Meeting days: {', '.join(days)}")
        if thoi_gian_col:
            times = [str(x) for x in subset[thoi_gian_col].dropna().astype(str).unique().tolist()[:5]]
            if times:
                parts.append(f"- Meeting times: {', '.join(times)}")
        if phong_col:
            rooms = [str(x) for x in subset[phong_col].dropna().astype(str).unique().tolist()[:5]]
            if rooms:
                parts.append(f"- Rooms: {', '.join(rooms)}")

        if len(parts) == 1:
            return f"Course code {code} was found, but the schedule fields are still incomplete."
        return "\n".join(parts)

    if query["type"] == "count":
        code = query["code"]
        if not ma_hp_col:
            return "Could not find the course-code column."
        subset = _filter_contains(df, ma_hp_col, code)
        if subset.empty:
            return f"No data was found for course {code}."
        if ma_lop_col:
            class_count = subset[ma_lop_col].astype(str).nunique()
            return f"Course {code} has about {class_count} distinct classes."
        return f"Course {code} appears in about {len(subset)} rows/classes."

    if query["type"] == "count_name":
        name = query["name"]
        if not ten_hp_col:
            return "Could not find the course-name column."
        subset = _filter_contains(df, ten_hp_col, name)
        if subset.empty:
            return f"No data was found for course '{name}'."
        if ma_lop_col:
            class_count = subset[ma_lop_col].astype(str).nunique()
            return f"Course '{name}' has about {class_count} distinct classes."
        return f"Course '{name}' appears in about {len(subset)} rows/classes."

    if query["type"] == "day":
        code = query["code"]
        if not ma_hp_col:
            return "Could not find the course-code column."
        subset = _filter_contains(df, ma_hp_col, code)
        if subset.empty:
            return f"No data was found for course {code}."
        if not thu_col:
            return f"Course {code} was found, but no day/weekday column could be identified."

        days = [str(x) for x in subset[thu_col].dropna().astype(str).unique().tolist()]
        if not days:
            return f"Course {code} was found, but no meeting-day data is available."

        extra_parts: List[str] = []
        if thoi_gian_col:
            times = [str(x) for x in subset[thoi_gian_col].dropna().astype(str).unique().tolist()[:5]]
            if times:
                extra_parts.append("meeting times: " + ", ".join(times))
        if phong_col:
            rooms = [str(x) for x in subset[phong_col].dropna().astype(str).unique().tolist()[:5]]
            if rooms:
                extra_parts.append("rooms: " + ", ".join(rooms))

        answer = f"Course {code} meets on: {', '.join(days)}."
        if extra_parts:
            answer += " Additional details: " + "; ".join(extra_parts) + "."
        return answer

    if query["type"] == "day_name":
        name = query["name"]
        if not ten_hp_col:
            return "Could not find the course-name column."
        subset = _filter_contains(df, ten_hp_col, name)
        if subset.empty:
            return f"No data was found for course '{name}'."
        if not thu_col:
            return f"Course '{name}' was found, but no day/weekday column could be identified."

        days = [str(x) for x in subset[thu_col].dropna().astype(str).unique().tolist()]
        answer = f"Course '{name}' meets on: {', '.join(days)}."
        if thoi_gian_col:
            times = [str(x) for x in subset[thoi_gian_col].dropna().astype(str).unique().tolist()[:5]]
            if times:
                answer += " Meeting times: " + ", ".join(times) + "."
        return answer

    if query["type"] == "info_name":
        name = query["name"]
        if not ten_hp_col:
            return "Could not find the course-name column."
        subset = _filter_contains(df, ten_hp_col, name)
        if subset.empty:
            return f"No data was found for course '{name}'."

        lines = [f"Information found for course '{name}':"]

        if ma_hp_col:
            codes = [str(x) for x in subset[ma_hp_col].dropna().astype(str).unique().tolist()[:5]]
            if codes:
                lines.append(f"- Course codes: {', '.join(codes)}")

        if ma_lop_col:
            classes = [str(x) for x in subset[ma_lop_col].dropna().astype(str).unique().tolist()[:10]]
            if classes:
                lines.append(f"- Class codes: {', '.join(classes)}")

        if thu_col:
            days = [str(x) for x in subset[thu_col].dropna().astype(str).unique().tolist()[:10]]
            if days:
                lines.append(f"- Meeting days: {', '.join(days)}")

        if thoi_gian_col:
            times = [str(x) for x in subset[thoi_gian_col].dropna().astype(str).unique().tolist()[:10]]
            if times:
                lines.append(f"- Meeting times: {', '.join(times)}")

        if phong_col:
            rooms = [str(x) for x in subset[phong_col].dropna().astype(str).unique().tolist()[:10]]
            if rooms:
                lines.append(f"- Rooms: {', '.join(rooms)}")

        return "\n".join(lines)

    if query["type"] == "list_unit":
        if not unit_col or not ten_hp_col:
            return "Could not find the faculty/department/unit column or the course column."
        subset = df
        unit = query.get("unit")
        if unit:
            subset = _filter_contains(df, unit_col, unit)
            if subset.empty:
                return f"No data was found for faculty/department/unit '{unit}'."

        units = [str(x) for x in subset[unit_col].dropna().astype(str).unique().tolist()[:10]]
        subjects = [str(x) for x in subset[ten_hp_col].dropna().astype(str).unique().tolist()[:20]]

        lines: List[str] = []
        if unit:
            lines.append(f"Courses found for faculty/department/unit '{unit}':")
        else:
            lines.append("Example faculties or departments found in the data:")
            for u in units[:5]:
                lines.append(f"- {u}")
            lines.append("")
            lines.append("Example courses:")

        for s in subjects[:10]:
            lines.append(f"- {s}")
        return "\n".join(lines)

    return "The query could not be handled."


def _run_excel_query_multi(path: Path, question: str, query: Dict[str, Any]) -> str:
    selected_sheet, df = _select_best_sheet(path, question)

    if df is None or df.empty:
        return "No suitable sheet was found for data processing."

    result = _run_excel_query(df, query)
    if "Could not find" not in result and "No data was found" not in result:
        if selected_sheet and path.suffix.lower() != ".csv":
            return f"[Sheet: {selected_sheet}]\n{result}"
        return result

    if path.suffix.lower() != ".csv":
        workbook = pd.ExcelFile(path)
        for sheet in workbook.sheet_names:
            if sheet == selected_sheet:
                continue
            try:
                df2, _, _ = _read_excel_sheet_clean(path, sheet)
                if df2.empty:
                    continue
                result2 = _run_excel_query(df2, query)
                if "Could not find" not in result2 and "No data was found" not in result2:
                    return f"[Sheet: {sheet}]\n{result2}"
            except Exception:
                continue

    return result


def tool_describe_excel(profile: TenantProfile, question: str) -> str:
    path = _choose_excel_file(question, profile)
    if path is None:
        hinted = _extract_requested_file_hints(question, extensions=r"(?:xlsx|xls|csv)")
        if hinted:
            return _tenant_scoped_access_denied_message(profile, hinted[0])
        return "No Excel/CSV file is currently available in the shared or tenant data for analysis."

    query = _excel_query_detect(question)
    if query:
        return _run_excel_query_multi(path, question, query)

    return _format_excel_summary(path)


def _extract_target_url(question: str, profile: TenantProfile) -> Optional[str]:
    m = _URL_RE.search(question)
    if m:
        return m.group(0).rstrip(").,;]}>")

    tenant_urls = read_links(tenant_links_file(profile.tenant_id))
    shared_urls = read_links(selected_shared_links_file())
    urls = tenant_urls + [u for u in shared_urls if u not in tenant_urls]
    return urls[0] if urls else None


def tool_describe_link(profile: TenantProfile, question: str) -> str:
    url = _extract_target_url(question, profile)
    if not url:
        return "No link was found to analyze. You can provide a URL directly or add links to links.txt."

    try:
        resp = requests.get(
            url,
            timeout=12,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
        text = " ".join(soup.get_text(separator=" ").split())
        text = text[:2500]

        if not text:
            return f"The link {url} was reached, but no readable text could be extracted."

        lines = [f"Link: {url}"]
        if title:
            lines.append(f"Title: {title}")
        lines.append("Extracted raw content summary:")
        lines.append(text)
        return "\n".join(lines)
    except Exception as exc:
        return f"Error while reading link '{url}': {exc}"


def tool_describe_any_file(profile: TenantProfile, question: str) -> str:
    path = _choose_target_file(question, profile)

    if path is None:
        hinted = _extract_requested_file_hints(question)
        if hinted:
            return _tenant_scoped_access_denied_message(profile, hinted[0])
        if _link_question_detected(question):
            return tool_describe_link(profile, question)
        return "No file or link is currently available in the data to describe."

    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls", ".csv"}:
        return _inspect_excel_csv(path)
    if suffix == ".pdf":
        return _inspect_pdf(path)
    if suffix in {".txt", ".md"}:
        return _inspect_generic_text_file(path)

    return f"File `{path.name}` was identified, but there is no dedicated inspector yet for the `{suffix}` format."


def _extract_embedded_update_date(path: Path) -> Optional[str]:
    if path.suffix.lower() not in {".xlsx", ".xlsm"}:
        return None

    try:
        with zipfile.ZipFile(path) as zf:
            if "xl/sharedStrings.xml" in zf.namelist():
                text = zf.read("xl/sharedStrings.xml").decode("utf-8", errors="ignore")
                match = re.search(r"UPDATED\s+ON\s*(\d{2}\.\d{2}\.\d{4})", text, re.IGNORECASE)
                if match:
                    return match.group(1)

            if "docProps/core.xml" in zf.namelist():
                text = zf.read("docProps/core.xml").decode("utf-8", errors="ignore")
                match = re.search(r"<dcterms:modified[^>]*>([^<]+)</dcterms:modified>", text)
                if match:
                    parsed = datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))
                    return parsed.strftime("%d.%m.%Y")
    except Exception:
        return None

    return None


def tool_describe_file_update_time(profile: TenantProfile, question: str) -> str:
    path = _choose_target_file(question, profile)

    if path is None:
        hinted = _extract_requested_file_hints(question)
        if hinted:
            return _tenant_scoped_access_denied_message(profile, hinted[0])
        return "No file has been identified yet for update-date inspection."

    embedded_date = _extract_embedded_update_date(path)
    if embedded_date:
        return f"File `{path.name}` was updated on {embedded_date}."

    try:
        updated_at = datetime.fromtimestamp(path.stat().st_mtime)
    except Exception as exc:
        return f"Could not read the update time for file `{path.name}`: {exc}"

    display_date = updated_at.strftime("%d.%m.%Y")
    display_time = updated_at.strftime("%H:%M")
    return (
        f"File `{path.name}` was updated on {display_date} "
        f"(approximate timestamp: {display_time})."
    )


def detect_direct_tool(question: str, profile: TenantProfile, user_id: str) -> Optional[str]:
    q = question.strip().lower()

    if q in {"time", "current time", "what time is it"}:
        return tool_current_time()
    if q in {"status", "system status"}:
        return tool_status(profile, user_id)
    if q in {"listdocs", "list docs", "list documents"}:
        return tool_list_docs(profile)
    if q in {"tenants", "list tenants"}:
        return tool_list_tenants()
    if q.startswith("calc "):
        return f"Calculation result: {safe_calculate(question[5:])}"

    if (
        any(term in q for term in _CROSS_TENANT_BOUNDARY_TERMS)
        and not _FILE_HINT_RE.search(question)
        and "record" not in q
    ):
        return None

    if _file_update_question_detected(question):
        return tool_describe_file_update_time(profile, question)

    if _excel_question_detected(question):
        return tool_describe_excel(profile, question)

    if _describe_file_question_detected(question):
        return tool_describe_any_file(profile, question)

    if _link_question_detected(question):
        return tool_describe_link(profile, question)

    return None
