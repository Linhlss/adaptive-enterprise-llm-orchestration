from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from pypdf import PdfReader  # noqa: E402

try:
    import docx2txt  # type: ignore
except Exception:  # pragma: no cover - optional runtime dependency
    docx2txt = None

DATA_DIR = BASE_DIR / "data"
LEGACY_SHARED_FILES_DIR = DATA_DIR / "files"
SHARED_FILES_DIR = DATA_DIR / "shared" / "files"
TENANTS_DIR = DATA_DIR / "tenants"

VECTOR_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
STRUCTURED_EXTENSIONS = {".csv", ".xlsx"}
UNSUPPORTED_EXTENSIONS = {".doc", ".xls"}
TEXT_EXTENSIONS = VECTOR_EXTENSIONS | STRUCTURED_EXTENSIONS
DISCOVERABLE_EXTENSIONS = TEXT_EXTENSIONS | UNSUPPORTED_EXTENSIONS


@dataclass
class CorpusFile:
    path: Path
    name: str
    suffix: str
    text: str
    supported: bool


def _load_rows(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise SystemExit(f"{path} must contain a JSON list.")
    return [dict(item) for item in raw]


def _normalize_text(value: str) -> str:
    text = str(value or "").lower()
    text = text.replace("\u0111", "d")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _contains_phrase(haystack: str, needle: str) -> bool:
    return _normalize_text(needle) in _normalize_text(haystack)


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _extract_pdf_text(path: Path) -> str:
    try:
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def _extract_docx_text(path: Path) -> str:
    if docx2txt is None:
        return ""
    try:
        return str(docx2txt.process(str(path)) or "")
    except Exception:
        return ""


def _extract_csv_text(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
            rows = csv.reader(handle)
            return "\n".join(" | ".join(cell.strip() for cell in row) for row in rows)
    except Exception:
        return _safe_read_text(path)


def _extract_xlsx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as zf:
            shared_strings: list[str] = []
            if "xl/sharedStrings.xml" in zf.namelist():
                root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
                for node in root.iter():
                    if node.tag.endswith("}t") and node.text:
                        shared_strings.append(node.text)

            out: list[str] = []
            for name in zf.namelist():
                if not name.startswith("xl/worksheets/sheet") or not name.endswith(".xml"):
                    continue
                root = ET.fromstring(zf.read(name))
                for cell in root.iter():
                    if not cell.tag.endswith("}c"):
                        continue
                    cell_type = cell.attrib.get("t", "")
                    value_node = next((child for child in cell if child.tag.endswith("}v")), None)
                    if value_node is None or value_node.text is None:
                        continue
                    raw = value_node.text
                    if cell_type == "s":
                        try:
                            out.append(shared_strings[int(raw)])
                        except Exception:
                            out.append(raw)
                    else:
                        out.append(raw)
            return "\n".join(out)
    except Exception:
        return ""


def _extract_file_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return _safe_read_text(path)
    if suffix == ".pdf":
        return _extract_pdf_text(path)
    if suffix == ".docx":
        return _extract_docx_text(path)
    if suffix == ".csv":
        return _extract_csv_text(path)
    if suffix == ".xlsx":
        return _extract_xlsx_text(path)
    if suffix == ".xls":
        return ""
    if suffix == ".doc":
        return ""
    return ""


def _collect_visible_files(
    tenant_id: str,
) -> tuple[dict[str, list[CorpusFile]], dict[str, list[Path]], list[CorpusFile]]:
    files: dict[str, list[CorpusFile]] = {}
    collisions: dict[str, list[Path]] = {}
    unsupported: list[CorpusFile] = []
    roots = [SHARED_FILES_DIR, LEGACY_SHARED_FILES_DIR, TENANTS_DIR / tenant_id / "files"]
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.name.startswith("."):
                continue
            suffix = path.suffix.lower()
            if suffix not in DISCOVERABLE_EXTENSIONS:
                continue
            item = CorpusFile(
                path=path,
                name=path.name,
                suffix=suffix,
                text=_extract_file_text(path) if suffix in TEXT_EXTENSIONS else "",
                supported=suffix in TEXT_EXTENSIONS,
            )
            key = path.name.lower()
            files.setdefault(key, []).append(item)
            if len(files[key]) > 1:
                collisions[key] = [entry.path for entry in files[key]]
            if not item.supported:
                unsupported.append(item)
    return files, collisions, unsupported


def _tenant_corpus_text(files: dict[str, list[CorpusFile]]) -> str:
    return "\n".join(item.text for bucket in files.values() for item in bucket if item.text)


def _keyword_hits(text: str, keywords: list[str]) -> tuple[list[str], list[str]]:
    hits: list[str] = []
    missing: list[str] = []
    for keyword in keywords:
        if _contains_phrase(text, keyword):
            hits.append(keyword)
        else:
            missing.append(keyword)
    return hits, missing


def _fail(message: str, failures: list[str]) -> None:
    failures.append(message)


def _warn(message: str, warnings: list[str]) -> None:
    warnings.append(message)


def _case_relevant_docs(row: dict[str, Any]) -> list[str]:
    values = row.get("relevant_docs", row.get("relevant_sources", [])) or []
    return [str(item).strip() for item in values if str(item).strip()]


def _case_expected_keywords(row: dict[str, Any]) -> list[str]:
    values = row.get("expected_keywords", row.get("expected_answer_keywords", [])) or []
    return [str(item).strip() for item in values if str(item).strip()]


def _case_forbidden_keywords(row: dict[str, Any]) -> list[str]:
    values = row.get("forbidden_keywords") or []
    return [str(item).strip() for item in values if str(item).strip()]


def _visible_doc(files: dict[str, list[CorpusFile]], doc_name: str) -> CorpusFile | None:
    matches = files.get(Path(doc_name).name.lower()) or []
    if len(matches) != 1:
        return None
    return matches[0]


def _validate_retrieval_case(
    row: dict[str, Any],
    files: dict[str, list[CorpusFile]],
    failures: list[str],
    warnings: list[str],
) -> None:
    case_id = str(row.get("id") or "<unknown>")
    relevant_docs = _case_relevant_docs(row)
    if not relevant_docs:
        _fail(f"{case_id}: retrieval case missing relevant_docs.", failures)
        return

    texts: list[str] = []
    for doc_name in relevant_docs:
        item = _visible_doc(files, doc_name)
        if item is None:
            _fail(f"{case_id}: relevant doc `{doc_name}` not found in visible corpus.", failures)
            continue
        if item.suffix not in VECTOR_EXTENSIONS:
            _fail(f"{case_id}: retrieval doc `{doc_name}` has non-vector extension `{item.suffix}`.", failures)
        texts.append(item.text)

    expected_keywords = _case_expected_keywords(row)
    if expected_keywords and texts:
        _hits, missing = _keyword_hits("\n".join(texts), expected_keywords)
        if missing:
            _fail(f"{case_id}: expected_keywords missing from relevant_docs: {missing}", failures)
    elif not expected_keywords:
        _warn(f"{case_id}: retrieval case has no expected_keywords.", warnings)


def _validate_tool_case(
    row: dict[str, Any],
    files: dict[str, list[CorpusFile]],
    failures: list[str],
    warnings: list[str],
) -> None:
    case_id = str(row.get("id") or "<unknown>")
    relevant_docs = _case_relevant_docs(row)
    if not relevant_docs:
        _fail(f"{case_id}: tool case missing relevant_docs.", failures)
        return

    texts: list[str] = []
    for doc_name in relevant_docs:
        item = _visible_doc(files, doc_name)
        if item is None:
            _fail(f"{case_id}: tool doc `{doc_name}` not found in visible corpus.", failures)
            continue
        if item.suffix not in STRUCTURED_EXTENSIONS:
            _fail(f"{case_id}: tool doc `{doc_name}` is not csv/xls/xlsx.", failures)
        texts.append(item.text)

    expected_keywords = _case_expected_keywords(row)
    if expected_keywords and texts:
        _hits, missing = _keyword_hits("\n".join(texts), expected_keywords)
        if missing:
            _fail(f"{case_id}: expected_keywords missing from tool docs: {missing}", failures)
    elif not expected_keywords:
        _warn(f"{case_id}: tool case has no expected_keywords.", warnings)


def _validate_out_of_scope_case(
    row: dict[str, Any],
    corpus_text: str,
    failures: list[str],
    warnings: list[str],
    *,
    strict_absent_keywords: bool,
) -> None:
    case_id = str(row.get("id") or "<unknown>")
    relevant_docs = _case_relevant_docs(row)
    if relevant_docs:
        _fail(f"{case_id}: out_of_scope case should not declare relevant_docs.", failures)

    absent_keywords = row.get("corpus_absent_keywords") or []
    absent_keywords = [str(item).strip() for item in absent_keywords if str(item).strip()]
    if not absent_keywords:
        message = (
            f"{case_id}: out_of_scope case has no corpus_absent_keywords; "
            "cannot prove the harmful/unsupported answer is absent from corpus."
        )
        if strict_absent_keywords:
            _fail(message, failures)
        else:
            _warn(message, warnings)
        return

    hits, _missing = _keyword_hits(corpus_text, absent_keywords)
    if hits:
        _fail(f"{case_id}: corpus_absent_keywords unexpectedly found in corpus: {hits}", failures)


def _validate_forbidden_keywords(
    row: dict[str, Any],
    requester_corpus_text: str,
    failures: list[str],
    warnings: list[str],
    corpus_cache: dict[str, tuple[dict[str, list[CorpusFile]], str]],
) -> None:
    case_id = str(row.get("id") or "<unknown>")
    forbidden = _case_forbidden_keywords(row)
    if not forbidden:
        return

    hits, _missing = _keyword_hits(requester_corpus_text, forbidden)
    if hits:
        _fail(f"{case_id}: forbidden_keywords leaked into current tenant corpus: {hits}", failures)

    target_tenant_id = str(row.get("target_tenant_id") or "").strip()
    if not target_tenant_id:
        return
    target_entry = corpus_cache.get(target_tenant_id)
    if target_entry is None:
        _warn(f"{case_id}: target tenant `{target_tenant_id}` corpus not available for positive check.", warnings)
        return
    _files, target_corpus_text = target_entry
    _hits, missing = _keyword_hits(target_corpus_text, forbidden)
    if missing:
        _fail(
            f"{case_id}: forbidden_keywords are missing from target tenant `{target_tenant_id}` corpus: {missing}",
            failures,
        )


def validate_dataset(
    dataset_path: Path,
    *,
    strict_absent_keywords: bool,
) -> tuple[list[str], list[str], dict[str, Any]]:
    rows = _load_rows(dataset_path)
    benchmark_tenants = sorted(
        {
            str(row.get("tenant_id") or "").strip()
            for row in rows
            if str(row.get("tenant_id") or "").strip()
        }
        | {
            str(row.get("target_tenant_id") or "").strip()
            for row in rows
            if str(row.get("target_tenant_id") or "").strip()
        }
    )

    corpus_cache: dict[str, tuple[dict[str, list[CorpusFile]], str]] = {}
    failures: list[str] = []
    warnings: list[str] = []
    for tenant_id in benchmark_tenants:
        files, collisions, unsupported = _collect_visible_files(tenant_id)
        for basename, paths in sorted(collisions.items()):
            _fail(
                f"tenant `{tenant_id}` has ambiguous visible basename `{basename}` across files: "
                f"{[str(path) for path in paths]}",
                failures,
            )
        for item in unsupported:
            _fail(
                f"tenant `{tenant_id}` has unsupported semantic-validation format `{item.name}`; "
                "convert `.doc` to `.docx` or `.pdf`, and `.xls` to `.xlsx` or `.csv`.",
                failures,
            )
        corpus_cache[tenant_id] = (files, _tenant_corpus_text(files))
    by_route: dict[str, int] = {}

    for row in rows:
        case_id = str(row.get("id") or "<unknown>")
        tenant_id = str(row.get("tenant_id") or "").strip()
        route = str(row.get("expected_route") or "").strip()
        by_route[route] = by_route.get(route, 0) + 1

        if not tenant_id:
            _fail(f"{case_id}: missing tenant_id.", failures)
            continue
        if tenant_id not in corpus_cache:
            _fail(f"{case_id}: tenant `{tenant_id}` has no collected corpus.", failures)
            continue

        files, corpus_text = corpus_cache[tenant_id]
        if not any(bucket for bucket in files.values()):
            _fail(f"{case_id}: tenant `{tenant_id}` has empty visible corpus.", failures)
            continue

        if row.get("requires_sources") and not _case_relevant_docs(row):
            _fail(f"{case_id}: requires_sources=true but no relevant_docs/relevant_sources were declared.", failures)

        if row.get("requires_denial"):
            _validate_forbidden_keywords(row, corpus_text, failures, warnings, corpus_cache)
            continue

        if route == "retrieval":
            _validate_retrieval_case(row, files, failures, warnings)
        elif route == "tool":
            _validate_tool_case(row, files, failures, warnings)
        elif route == "out_of_scope":
            _validate_out_of_scope_case(
                row,
                corpus_text,
                failures,
                warnings,
                strict_absent_keywords=strict_absent_keywords,
            )
        elif route == "general":
            if _case_relevant_docs(row):
                _warn(f"{case_id}: general case unexpectedly declares relevant_docs.", warnings)
        else:
            _fail(f"{case_id}: unsupported expected_route `{route}`.", failures)

        _validate_forbidden_keywords(row, corpus_text, failures, warnings, corpus_cache)

    summary = {
        "dataset": str(dataset_path),
        "rows": len(rows),
        "routes": by_route,
        "tenants": sorted(corpus_cache),
        "failure_count": len(failures),
        "warning_count": len(warnings),
    }
    return failures, warnings, summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate that dataset cases are semantically supported by local corpus content.")
    parser.add_argument("--dataset", required=True)
    parser.add_argument(
        "--strict-absent-keywords",
        action="store_true",
        help="Fail out_of_scope cases that do not declare corpus_absent_keywords.",
    )
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    failures, warnings, summary = validate_dataset(
        dataset_path,
        strict_absent_keywords=args.strict_absent_keywords,
    )

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {
                    "summary": summary,
                    "failures": failures,
                    "warnings": warnings,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    if failures:
        print("FAIL: Benchmark content semantic validation failed.")
        for item in failures:
            print(f"FAIL: {item}")
        for item in warnings:
            print(f"WARN: {item}")
        return 1

    print("PASS: Benchmark content semantic validation completed.")
    print(
        f"INFO: rows={summary['rows']} routes={summary['routes']} "
        f"tenants={summary['tenants']} warnings={summary['warning_count']}"
    )
    for item in warnings:
        print(f"WARN: {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
