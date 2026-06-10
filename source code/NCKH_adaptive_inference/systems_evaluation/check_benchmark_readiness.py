from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
TENANT_CONFIG = BASE_DIR / "config" / "tenants.json"
TENANTS_DIR = BASE_DIR / "data" / "tenants"
REQUIRED_ROUTES = ["retrieval", "tool", "general", "out_of_scope"]
PROSE_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md"}
STRUCTURED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from systems_evaluation.backend_preflight import probe_backend_http

OLLAMA_QWEN3_4B_MODEL = os.getenv("OLLAMA_QWEN3_4B_MODEL", "qwen3:4b")
OLLAMA_QWEN3_8B_MODEL = os.getenv("OLLAMA_QWEN3_8B_MODEL", "qwen3:8b")
OLLAMA_QWEN3_14B_MODEL = os.getenv("OLLAMA_QWEN3_14B_MODEL", "qwen3:14b")
VLLM_QWEN3_4B_MODEL = os.getenv("VLLM_QWEN3_4B_MODEL", "Qwen/Qwen3-4B-AWQ")
VLLM_QWEN3_8B_MODEL = os.getenv("VLLM_QWEN3_8B_MODEL", "Qwen/Qwen3-8B-AWQ")
VLLM_QWEN3_14B_MODEL = os.getenv("VLLM_QWEN3_14B_MODEL", "Qwen/Qwen3-14B-AWQ")
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "EMPTY")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw = _load_json(path)
    if not isinstance(raw, list):
        raise SystemExit(f"{path} must be a JSON list.")
    return [dict(row) for row in raw]


def _benchmark_tenants(configs: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {tenant_id: cfg for tenant_id, cfg in configs.items() if bool(cfg.get("benchmark_domain_pack"))}


def _tenant_content_counts(tenant_id: str) -> tuple[int, int, int]:
    files_dir = TENANTS_DIR / tenant_id / "files"
    prose = 0
    structured = 0
    other = 0
    if files_dir.exists():
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


def _source_case_counts(inputs: list[Path], benchmark_tenant_ids: set[str]) -> Counter[tuple[str, str]]:
    counts: Counter[tuple[str, str]] = Counter()
    for path in inputs:
        for row in _load_rows(path):
            tenant_id = str(row.get("tenant_id") or "").strip()
            if tenant_id not in benchmark_tenant_ids:
                continue
            domain_id = str(row.get("domain_id") or "").strip()
            route = str(row.get("expected_route") or "").strip()
            if domain_id and route in REQUIRED_ROUTES:
                counts[(domain_id, route)] += 1
    return counts


def _generated_dataset_counts(path: Path) -> tuple[int, Counter[str], Counter[tuple[str, str]]]:
    rows = _load_rows(path)
    by_domain = Counter(str(row.get("domain_id") or "") for row in rows)
    by_domain_route = Counter(
        (str(row.get("domain_id") or ""), str(row.get("expected_route") or ""))
        for row in rows
    )
    return len(rows), by_domain, by_domain_route


def _print_status(ok: bool, message: str) -> None:
    prefix = "PASS" if ok else "FAIL"
    print(f"{prefix}: {message}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check readiness before running the benchmark pack.")
    parser.add_argument(
        "--input",
        nargs="+",
        default=[
            "systems_evaluation/test_queries_source.json",
        ],
        help="Source query files used by prepare_benchmark_dataset.py.",
    )
    parser.add_argument("--dataset", default="systems_evaluation/test_queries_multidomain.json")
    parser.add_argument("--model-dataset", default="systems_evaluation/test_queries_model_sensitivity.json")
    parser.add_argument("--stability-dataset", default="systems_evaluation/test_queries_stability_subset.json")
    parser.add_argument("--isolation-dataset", default="systems_evaluation/test_queries_isolation.json")
    parser.add_argument("--cases-per-route-domain", type=int, default=12)
    parser.add_argument("--subset-cases-per-route-domain", type=int, default=6)
    parser.add_argument("--check-backend", action="store_true")
    parser.add_argument("--llm-backend", choices=["ollama", "vllm"], default="vllm")
    parser.add_argument("--vllm-base-url", default="http://host.docker.internal:8001")
    parser.add_argument("--ollama-base-url", default="http://host.docker.internal:11434")
    parser.add_argument("--required-model", action="append", default=[])
    parser.add_argument("--backend-timeout", type=float, default=3.0)
    args = parser.parse_args()

    failures: list[str] = []
    warnings: list[str] = []

    if not TENANT_CONFIG.exists():
        failures.append(f"missing tenant config: {TENANT_CONFIG}")
        print("\n".join(f"FAIL: {item}" for item in failures))
        return 1

    configs = {str(k): dict(v) for k, v in _load_json(TENANT_CONFIG).items()}
    benchmark_configs = _benchmark_tenants(configs)
    domains: dict[str, set[str]] = defaultdict(set)
    for tenant_id, cfg in benchmark_configs.items():
        domains[str(cfg.get("domain_id") or "")].add(tenant_id)

    if len(domains) != 3:
        failures.append(f"expected 3 benchmark domains, found {len(domains)}: {sorted(domains)}")
    for domain_id, tenants in sorted(domains.items()):
        if len(tenants) != 2:
            failures.append(f"domain {domain_id} expected 2 benchmark tenants, found {len(tenants)}: {sorted(tenants)}")

    for tenant_id in sorted(benchmark_configs):
        prose, structured, other = _tenant_content_counts(tenant_id)
        if prose + structured + other == 0:
            failures.append(f"tenant {tenant_id} has no corpus files under data/tenants/{tenant_id}/files")
        if prose < 8:
            warnings.append(f"tenant {tenant_id} has {prose} prose files; Benchmark target is 8-15")
        if structured < 3:
            warnings.append(f"tenant {tenant_id} has {structured} structured files; Benchmark target is 3-4")

    source_inputs = [BASE_DIR / value if not Path(value).is_absolute() else Path(value) for value in args.input]
    source_counts = _source_case_counts(source_inputs, set(benchmark_configs))
    for domain_id in sorted(domains):
        for route in REQUIRED_ROUTES:
            count = source_counts[(domain_id, route)]
            if count < args.cases_per_route_domain:
                failures.append(
                    f"source queries for domain={domain_id} route={route}: "
                    f"{count}/{args.cases_per_route_domain}"
                )

    generated_specs = [
        (BASE_DIR / args.dataset, 144, args.cases_per_route_domain),
        (BASE_DIR / args.model_dataset, 72, args.subset_cases_per_route_domain),
        (BASE_DIR / args.stability_dataset, 72, args.subset_cases_per_route_domain),
    ]
    for path, expected_total, expected_per_route_domain in generated_specs:
        if not path.exists():
            failures.append(f"generated dataset missing: {path.relative_to(BASE_DIR)}")
            continue
        total, by_domain, by_domain_route = _generated_dataset_counts(path)
        if total != expected_total:
            failures.append(f"{path.name} expected {expected_total} rows, found {total}")
        for domain_id in sorted(domains):
            for route in REQUIRED_ROUTES:
                count = by_domain_route[(domain_id, route)]
                if count != expected_per_route_domain:
                    failures.append(
                        f"{path.name} domain={domain_id} route={route}: "
                        f"{count}/{expected_per_route_domain}"
                    )

    isolation_path = BASE_DIR / args.isolation_dataset
    if not isolation_path.exists():
        failures.append(f"isolation dataset missing: {isolation_path.relative_to(BASE_DIR)}")
    else:
        rows = _load_rows(isolation_path)
        route_counts = Counter(str(row.get("expected_route") or "") for row in rows)
        if len(rows) < 48:
            failures.append(f"isolation dataset expected at least 48 probes, found {len(rows)}")
        if route_counts["retrieval"] < 24 or route_counts["tool"] < 24:
            failures.append(f"isolation route balance expected 24 retrieval and 24 tool, found {dict(route_counts)}")

    if args.check_backend:
        if args.required_model:
            required_models = [str(item).strip() for item in args.required_model if str(item).strip()]
        elif args.llm_backend == "vllm":
            required_models = [VLLM_QWEN3_14B_MODEL, VLLM_QWEN3_8B_MODEL, VLLM_QWEN3_4B_MODEL]
        else:
            required_models = [OLLAMA_QWEN3_14B_MODEL, OLLAMA_QWEN3_8B_MODEL, OLLAMA_QWEN3_4B_MODEL]

        probe = probe_backend_http(
            backend=args.llm_backend,
            base_url=args.vllm_base_url if args.llm_backend == "vllm" else args.ollama_base_url,
            expected_models=required_models,
            api_key=VLLM_API_KEY if args.llm_backend == "vllm" else "",
            timeout=args.backend_timeout,
        )
        if not probe.ok:
            failures.append(
                f"{probe.backend} backend preflight failed at {probe.endpoint}: "
                f"missing_models={probe.missing_models or '[]'} error={probe.error or 'none'}"
            )

    _print_status(not failures, "benchmark readiness check")
    for item in failures:
        print(f"FAIL: {item}")
    for item in warnings:
        print(f"WARN: {item}")

    if failures:
        backend_failure = args.check_backend and any("backend preflight failed" in item for item in failures)
        print("")
        print("Next required steps:")
        if backend_failure:
            print("1. Start or point to a real vLLM server on a dedicated port (the repository defaults assume `8001`, not the app API port `8000`).")
            print("2. Verify that `/v1/models` exposes the expected Qwen3-AWQ ladder.")
            print("3. Re-run this command with `--check-backend` after updating `VLLM_BASE_URL` or `--vllm-base-url`.")
        else:
            print("1. Add corpus files under each data/tenants/<benchmark_tenant>/files/")
            print("2. Add source query cases for each benchmark tenant/domain/route")
            print("3. Run: make prepare-benchmark-pack")
            print("4. Run: make validate-benchmark-pack validate-model-sensitivity-pack validate-stability-pack validate-isolation-pack")
            print("5. Run: make validate-benchmark-content-pack validate-benchmark-content-model validate-benchmark-content-stability validate-benchmark-content-isolation")
        return 1

    print("Ready to run: make benchmark-full-suite")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
