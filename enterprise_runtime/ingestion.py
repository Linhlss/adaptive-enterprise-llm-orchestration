from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, List, Optional, Tuple

from llama_index.core import SimpleDirectoryReader
from llama_index.readers.web import BeautifulSoupWebReader

from enterprise_runtime.config import (
    ALLOWED_EXTENSIONS,
    ENABLE_WEB_READER,
    LEGACY_SHARED_FILES_DIR,
    LEGACY_SHARED_LINKS_FILE,
    PROJECT_ROOT,
    SHARED_FILES_DIR,
    SHARED_LINKS_FILE,
    TABLE_FILE_EXTENSIONS,
    TENANTS_DIR,
)
from enterprise_runtime.utils import now_str, relpath_safe, safe_read_text


def tenant_files_dir(tenant_id: str) -> Path:
    p = TENANTS_DIR / tenant_id / "files"
    p.mkdir(parents=True, exist_ok=True)
    return p


def tenant_links_file(tenant_id: str) -> Path:
    p = TENANTS_DIR / tenant_id / "links.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text("", encoding="utf-8")
    return p


def iter_data_files(folder: Optional[Path]) -> Iterable[Path]:
    if folder is None or not folder.exists():
        return []
    return [
        p
        for p in folder.rglob("*")
        if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in ALLOWED_EXTENSIONS
    ]


def list_real_files(folder: Optional[Path]) -> List[Path]:
    return list(iter_data_files(folder))


def selected_shared_files_dir() -> Optional[Path]:
    new_files = list_real_files(SHARED_FILES_DIR)
    if new_files:
        return SHARED_FILES_DIR

    legacy_files = list_real_files(LEGACY_SHARED_FILES_DIR)
    if legacy_files:
        return LEGACY_SHARED_FILES_DIR

    if SHARED_FILES_DIR.exists():
        return SHARED_FILES_DIR
    if LEGACY_SHARED_FILES_DIR.exists():
        return LEGACY_SHARED_FILES_DIR
    return None


def selected_shared_links_file() -> Optional[Path]:
    if SHARED_LINKS_FILE.exists() and safe_read_text(SHARED_LINKS_FILE).strip():
        return SHARED_LINKS_FILE
    if LEGACY_SHARED_LINKS_FILE.exists() and safe_read_text(LEGACY_SHARED_LINKS_FILE).strip():
        return LEGACY_SHARED_LINKS_FILE
    if SHARED_LINKS_FILE.exists():
        return SHARED_LINKS_FILE
    if LEGACY_SHARED_LINKS_FILE.exists():
        return LEGACY_SHARED_LINKS_FILE
    return None


def read_links(path: Optional[Path]) -> List[str]:
    if path is None or not path.exists():
        return []
    return [
        line.strip()
        for line in safe_read_text(path).splitlines()
        if line.strip().startswith("http")
    ]


def compute_data_signature(tenant_id: str) -> str:
    records: List[Tuple[str, int, int]] = []

    paths: List[Path] = []
    shared_dir = selected_shared_files_dir()
    shared_links = selected_shared_links_file()

    if shared_dir:
        paths.append(shared_dir)
    if shared_links:
        paths.append(shared_links)

    paths.append(tenant_files_dir(tenant_id))
    paths.append(tenant_links_file(tenant_id))

    for p in [x for x in paths if x.exists()]:
        if p.is_dir():
            for f in iter_data_files(p):
                try:
                    stat = f.stat()
                    records.append((relpath_safe(f, PROJECT_ROOT), stat.st_mtime_ns, stat.st_size))
                except FileNotFoundError:
                    continue
        else:
            try:
                stat = p.stat()
                records.append((relpath_safe(p, PROJECT_ROOT), stat.st_mtime_ns, stat.st_size))
            except FileNotFoundError:
                continue

    payload = json.dumps(sorted(records), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _vectorizable_files(files: List[Path]) -> List[Path]:
    # Excel/CSV goes through the tool path instead of vector RAG to avoid slow rebuilds.
    return [f for f in files if f.suffix.lower() not in TABLE_FILE_EXTENSIONS]


def read_local_documents(files: List[Path], tenant_id: str, scope: str) -> List[Any]:
    files = _vectorizable_files(files)
    if not files:
        return []

    try:
        docs = SimpleDirectoryReader(input_files=[str(f) for f in files]).load_data()
    except Exception:
        return []

    for d in docs:
        src = d.metadata.get("file_path") or d.metadata.get("file_name") or "unknown"
        d.metadata.update(
            {
                "tenant_id": tenant_id,
                "tenant_scope": scope,
                "source_type": "local_file",
                "source_ref": src,
                "loaded_at": now_str(),
            }
        )
    return docs


def read_web_documents(urls: List[str], tenant_id: str, scope: str) -> List[Any]:
    if not ENABLE_WEB_READER or not urls:
        return []

    try:
        docs = BeautifulSoupWebReader().load_data(urls=urls)
    except Exception:
        return []

    for d in docs:
        d.metadata.update(
            {
                "tenant_id": tenant_id,
                "tenant_scope": scope,
                "source_type": "web",
                "source_url": d.metadata.get("source_url", ""),
                "loaded_at": now_str(),
            }
        )
    return docs


def collect_documents(tenant_id: str) -> List[Any]:
    docs: List[Any] = []

    shared_dir = selected_shared_files_dir()
    if shared_dir:
        docs.extend(read_local_documents(list_real_files(shared_dir), tenant_id, "shared"))

    shared_links = selected_shared_links_file()
    if shared_links:
        docs.extend(read_web_documents(read_links(shared_links), tenant_id, "shared"))

    t_dir = tenant_files_dir(tenant_id)
    docs.extend(read_local_documents(list_real_files(t_dir), tenant_id, "tenant"))

    t_links = tenant_links_file(tenant_id)
    docs.extend(read_web_documents(read_links(t_links), tenant_id, "tenant"))

    return docs
