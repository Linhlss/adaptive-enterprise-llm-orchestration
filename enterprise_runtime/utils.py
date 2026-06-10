from __future__ import annotations

import logging
import os
import re
import socket
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import psutil  # type: ignore
    HAS_PSUTIL = True
except Exception:
    psutil = None
    HAS_PSUTIL = False

try:
    from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore
    HAS_SCHEDULER = True
except Exception:
    BackgroundScheduler = None
    HAS_SCHEDULER = False


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_ram_usage() -> float:
    if not HAS_PSUTIL:
        return -1.0
    try:
        return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
    except Exception:
        return -1.0


def format_ram_usage(value: float) -> str:
    return "N/A" if value < 0 else f"{value:.2f}MB"


def check_ollama_alive(host: str = "127.0.0.1", port: int = 11434, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def sanitize_id(value: str, default: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-zA-Z0-9_-]+", "_", value)
    return value.strip("_") or default


def normalize_question(question: str) -> str:
    text = question.strip()
    text = re.sub(r"^\s*tenant_id\s*:\s*[^\n]+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*user_id\s*:\s*[^\n]+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^[\s,;:-]+", "", text)
    return text.strip()


def relpath_safe(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""