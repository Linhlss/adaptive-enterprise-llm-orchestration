from __future__ import annotations

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from systems_evaluation.benchmark_corpus_blueprint import BENCHMARK_CORPUS_BLUEPRINT

TENANTS_DIR = BASE_DIR / "data" / "tenants"
PROSE_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md"}
STRUCTURED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


def _tenant_counts(tenant_id: str) -> tuple[int, int, int]:
    files_dir = TENANTS_DIR / tenant_id / "files"
    prose = 0
    structured = 0
    other = 0
    if not files_dir.exists():
        return prose, structured, other
    for path in files_dir.rglob("*"):
        if not path.is_file() or path.name.startswith("."):
            continue
        suffix = path.suffix.lower()
        if suffix in PROSE_EXTENSIONS:
            prose += 1
        elif suffix in STRUCTURED_EXTENSIONS:
            structured += 1
        else:
            other += 1
    return prose, structured, other


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit local Benchmark corpus counts per tenant.")
    parser.add_argument("--expected-prose", type=int, default=10)
    parser.add_argument("--expected-structured", type=int, default=3)
    args = parser.parse_args()

    failures = 0
    for tenant_id in sorted(BENCHMARK_CORPUS_BLUEPRINT):
        prose, structured, other = _tenant_counts(tenant_id)
        ok = prose >= args.expected_prose and structured >= args.expected_structured
        status = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1
        print(
            f"{status}: tenant={tenant_id} prose={prose}/{args.expected_prose} "
            f"structured={structured}/{args.expected_structured} other={other}"
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
