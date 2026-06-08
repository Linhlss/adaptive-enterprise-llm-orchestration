from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class BackendProbeResult:
    ok: bool
    backend: str
    endpoint: str
    available_models: list[str]
    missing_models: list[str]
    error: str = ""


def _read_json(url: str, *, headers: dict[str, str] | None = None, timeout: float = 3.0) -> Any:
    request = Request(url, headers=headers or {}, method="GET")
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _normalize_models(values: list[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def probe_backend_http(
    *,
    backend: str,
    base_url: str,
    expected_models: list[str] | None = None,
    api_key: str = "",
    timeout: float = 3.0,
) -> BackendProbeResult:
    normalized_backend = (backend or "ollama").strip().lower()
    expected = _normalize_models(expected_models or [])
    root = base_url.rstrip("/")

    if normalized_backend == "vllm":
        endpoint = f"{root}/models" if root.endswith("/v1") else f"{root}/v1/models"
        headers = {"Accept": "application/json"}
        if api_key and api_key.strip().upper() != "EMPTY":
            headers["Authorization"] = f"Bearer {api_key.strip()}"
        try:
            payload = _read_json(endpoint, headers=headers, timeout=timeout)
            items = payload.get("data") if isinstance(payload, dict) else []
            available = _normalize_models(
                [item.get("id", "") for item in items if isinstance(item, dict)]
            )
        except HTTPError as exc:
            return BackendProbeResult(
                ok=False,
                backend="vllm",
                endpoint=endpoint,
                available_models=[],
                missing_models=expected,
                error=f"HTTP {exc.code}",
            )
        except URLError as exc:
            return BackendProbeResult(
                ok=False,
                backend="vllm",
                endpoint=endpoint,
                available_models=[],
                missing_models=expected,
                error=str(exc.reason),
            )
        except Exception as exc:
            return BackendProbeResult(
                ok=False,
                backend="vllm",
                endpoint=endpoint,
                available_models=[],
                missing_models=expected,
                error=str(exc),
            )
    else:
        endpoint = f"{root}/api/tags"
        try:
            payload = _read_json(endpoint, timeout=timeout)
            items = payload.get("models") if isinstance(payload, dict) else []
            available = _normalize_models(
                [item.get("name", "") for item in items if isinstance(item, dict)]
            )
        except HTTPError as exc:
            return BackendProbeResult(
                ok=False,
                backend="ollama",
                endpoint=endpoint,
                available_models=[],
                missing_models=expected,
                error=f"HTTP {exc.code}",
            )
        except URLError as exc:
            return BackendProbeResult(
                ok=False,
                backend="ollama",
                endpoint=endpoint,
                available_models=[],
                missing_models=expected,
                error=str(exc.reason),
            )
        except Exception as exc:
            return BackendProbeResult(
                ok=False,
                backend="ollama",
                endpoint=endpoint,
                available_models=[],
                missing_models=expected,
                error=str(exc),
            )

    missing = [model for model in expected if model not in set(available)]
    return BackendProbeResult(
        ok=not missing,
        backend="vllm" if normalized_backend == "vllm" else "ollama",
        endpoint=endpoint,
        available_models=available,
        missing_models=missing,
    )
