from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from systems_evaluation.benchmark_corpus_blueprint import BENCHMARK_CORPUS_BLUEPRINT

TENANTS_DIR = BASE_DIR / "data" / "tenants"
DIRECT_BINARY_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv"}
TEXT_CONTENT_TYPES = {
    "text/html": ".md",
    "text/plain": ".txt",
}
USER_AGENT = "Mozilla/5.0 (compatible; BenchmarkCorpusBuilder/1.0; +https://openai.com)"


@dataclass
class BuildStats:
    prose_written: int = 0
    prose_skipped: int = 0
    structured_written: int = 0
    structured_skipped: int = 0


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_") or "file"


def _tenant_root(tenant_id: str) -> Path:
    root = TENANTS_DIR / tenant_id
    (root / "files").mkdir(parents=True, exist_ok=True)
    return root


def _fetch(url: str, timeout: int = 40) -> tuple[bytes, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        payload = response.read()
        content_type = response.headers.get_content_type().lower()
    return payload, content_type


def _extension_from_source(url: str, content_type: str) -> str:
    path_suffix = Path(urlparse(url).path).suffix.lower()
    if path_suffix in DIRECT_BINARY_EXTENSIONS:
        return path_suffix
    if path_suffix in {".txt", ".md"}:
        return path_suffix
    if content_type in TEXT_CONTENT_TYPES:
        return TEXT_CONTENT_TYPES[content_type]
    guessed = mimetypes.guess_extension(content_type) or ""
    if guessed in DIRECT_BINARY_EXTENSIONS | {".txt", ".md"}:
        return guessed
    return ".md"


def _extract_html_text(payload: bytes, fallback_title: str) -> str:
    soup = BeautifulSoup(payload, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else fallback_title
    main = soup.find("main") or soup.find("article") or soup.body or soup
    lines: list[str] = []
    seen: set[str] = set()
    for block in main.find_all(["h1", "h2", "h3", "p", "li"]):
        text = " ".join(block.get_text(" ", strip=True).split())
        if len(text) < 30 or text in seen:
            continue
        seen.add(text)
        lines.append(text)
    body = "\n\n".join(lines[:120]).strip()
    header = f"# {title}\n\n"
    return header + body if body else header + "No extractable text found."


def _write_payload(path: Path, payload: bytes, extension: str, title: str, force: bool) -> bool:
    if path.exists() and not force:
        return False
    if extension in DIRECT_BINARY_EXTENSIONS:
        path.write_bytes(payload)
        return True
    text = payload.decode("utf-8", errors="ignore")
    if extension == ".md":
        text = _extract_html_text(payload, title)
    path.write_text(text, encoding="utf-8")
    return True


def _build_prose_files(tenant_id: str, tenant_spec: dict[str, Any], force: bool) -> tuple[list[dict[str, Any]], BuildStats]:
    stats = BuildStats()
    written_records: list[dict[str, Any]] = []
    files_dir = _tenant_root(tenant_id) / "files"
    for entry in tenant_spec["prose_sources"]:
        url = str(entry["url"])
        title = str(entry["title"])
        source_id = str(entry["id"])
        try:
            payload, content_type = _fetch(url)
            extension = _extension_from_source(url, content_type)
            filename = f"{tenant_id}_{_slugify(source_id)}{extension}"
            path = files_dir / filename
            wrote = _write_payload(path, payload, extension, title, force)
            if wrote:
                stats.prose_written += 1
            else:
                stats.prose_skipped += 1
            written_records.append(
                {
                    "id": source_id,
                    "title": title,
                    "url": url,
                    "content_type": content_type,
                    "filename": filename,
                    "status": "written" if wrote else "skipped_existing",
                }
            )
        except Exception as exc:
            written_records.append(
                {
                    "id": source_id,
                    "title": title,
                    "url": url,
                    "status": "failed",
                    "error": str(exc),
                }
            )
    return written_records, stats


def _write_structured_csv(path: Path, rows: list[dict[str, Any]], force: bool) -> bool:
    if path.exists() and not force:
        return False
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return True


def _build_structured_files(tenant_id: str, tenant_spec: dict[str, Any], force: bool) -> tuple[list[dict[str, Any]], BuildStats]:
    stats = BuildStats()
    records: list[dict[str, Any]] = []
    files_dir = _tenant_root(tenant_id) / "files"
    for spec in tenant_spec["structured_files"]:
        filename = str(spec["filename"])
        rows = [dict(row) for row in spec["rows"]]
        path = files_dir / filename
        wrote = _write_structured_csv(path, rows, force)
        if wrote:
            stats.structured_written += 1
        else:
            stats.structured_skipped += 1
        records.append(
            {
                "filename": filename,
                "description": str(spec["description"]),
                "row_count": len(rows),
                "status": "written" if wrote else "skipped_existing",
            }
        )
    return records, stats


def _write_inventory(tenant_id: str, tenant_spec: dict[str, Any], prose_records: list[dict[str, Any]], structured_records: list[dict[str, Any]]) -> None:
    payload = {
        "tenant_id": tenant_id,
        "domain_id": tenant_spec["domain_id"],
        "domain_name": tenant_spec["domain_name"],
        "summary": tenant_spec["summary"],
        "prose_sources": prose_records,
        "structured_files": structured_records,
    }
    inventory_path = _tenant_root(tenant_id) / "source_manifest.json"
    inventory_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _selected_tenants(raw: list[str]) -> list[str]:
    if not raw:
        return sorted(BENCHMARK_CORPUS_BLUEPRINT)
    selected: list[str] = []
    unknown: list[str] = []
    for tenant_id in raw:
        if tenant_id in BENCHMARK_CORPUS_BLUEPRINT:
            selected.append(tenant_id)
        else:
            unknown.append(tenant_id)
    if unknown:
        raise SystemExit(f"Unknown benchmark tenant ids: {', '.join(sorted(unknown))}")
    return sorted(set(selected))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the benchmark tenant corpus pack from curated public sources.")
    parser.add_argument("--tenant-id", action="append", default=[], help="Build only the given benchmark tenant. Repeatable.")
    parser.add_argument("--force", action="store_true", help="Overwrite generated files if they already exist.")
    parser.add_argument("--prose-only", action="store_true", help="Download prose files only.")
    parser.add_argument("--structured-only", action="store_true", help="Generate structured CSV files only.")
    args = parser.parse_args()

    if args.prose_only and args.structured_only:
        raise SystemExit("Choose only one of --prose-only or --structured-only.")

    totals = BuildStats()
    for tenant_id in _selected_tenants(args.tenant_id):
        tenant_spec = BENCHMARK_CORPUS_BLUEPRINT[tenant_id]
        prose_records: list[dict[str, Any]] = []
        structured_records: list[dict[str, Any]] = []
        tenant_stats = BuildStats()
        if not args.structured_only:
            prose_records, prose_stats = _build_prose_files(tenant_id, tenant_spec, args.force)
            tenant_stats.prose_written += prose_stats.prose_written
            tenant_stats.prose_skipped += prose_stats.prose_skipped
        if not args.prose_only:
            structured_records, structured_stats = _build_structured_files(tenant_id, tenant_spec, args.force)
            tenant_stats.structured_written += structured_stats.structured_written
            tenant_stats.structured_skipped += structured_stats.structured_skipped
        _write_inventory(tenant_id, tenant_spec, prose_records, structured_records)
        totals.prose_written += tenant_stats.prose_written
        totals.prose_skipped += tenant_stats.prose_skipped
        totals.structured_written += tenant_stats.structured_written
        totals.structured_skipped += tenant_stats.structured_skipped
        print(
            f"{tenant_id}: prose_written={tenant_stats.prose_written} prose_skipped={tenant_stats.prose_skipped} "
            f"structured_written={tenant_stats.structured_written} structured_skipped={tenant_stats.structured_skipped}"
        )

    print(
        "TOTAL: "
        f"prose_written={totals.prose_written} prose_skipped={totals.prose_skipped} "
        f"structured_written={totals.structured_written} structured_skipped={totals.structured_skipped}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
