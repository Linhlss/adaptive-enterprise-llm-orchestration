from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
TENANT_CONFIG = BASE_DIR / "config" / "tenants.json"
TENANTS_DIR = BASE_DIR / "data" / "tenants"
REQUIRED_ROUTES = ["retrieval", "tool", "general", "out_of_scope"]
ALLOWED_MODEL_CLASSES = {"strong-quality", "balanced", "light-latency", "adaptive", "custom"}


def _fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_cases(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        _fail(f"Dataset not found: {path}")
    rows = _load_json(path)
    if not isinstance(rows, list):
        _fail("Dataset must be a JSON list.")
    return [dict(row) for row in rows]


def _load_tenant_configs() -> dict[str, dict[str, Any]]:
    if not TENANT_CONFIG.exists():
        _fail(f"Tenant config not found: {TENANT_CONFIG}")
    raw = _load_json(TENANT_CONFIG)
    if not isinstance(raw, dict):
        _fail("Tenant config must be a JSON object.")
    return {str(k): dict(v) for k, v in raw.items()}


def _tenant_domain(tenant_id: str, configs: dict[str, dict[str, Any]]) -> tuple[str, str]:
    cfg = configs.get(tenant_id)
    if not cfg:
        _fail(f"Tenant `{tenant_id}` exists in dataset but not in config/tenants.json.")
    q2_only = any(bool(item.get("q2_domain_pack")) for item in configs.values())
    if q2_only and not bool(cfg.get("q2_domain_pack")):
        _fail(f"Tenant `{tenant_id}` is not marked q2_domain_pack=true.")
    domain_id = str(cfg.get("domain_id") or "").strip()
    domain_name = str(cfg.get("domain_name") or "").strip()
    if not domain_id or not domain_name:
        _fail(f"Tenant `{tenant_id}` is missing domain_id/domain_name.")
    return domain_id, domain_name


def _has_content(tenant_id: str) -> bool:
    root = TENANTS_DIR / tenant_id
    if not root.exists():
        return False
    files_dir = root / "files"
    links_file = root / "links.txt"
    has_file = files_dir.exists() and any(p.is_file() and not p.name.startswith(".") for p in files_dir.rglob("*"))
    has_link = links_file.exists() and any(line.strip() for line in links_file.read_text(encoding="utf-8", errors="ignore").splitlines())
    return bool(has_file or has_link)


def _validate_model_policy(configs: dict[str, dict[str, Any]]) -> None:
    classes = {str(cfg.get("model_class") or "").strip() for cfg in configs.values()}
    unsupported_classes = sorted(value for value in classes if value and value not in ALLOWED_MODEL_CLASSES)
    if unsupported_classes:
        _fail(f"Unsupported model_class values in tenant config: {unsupported_classes}")
    backends = {str(cfg.get("llm_backend") or "").strip() for cfg in configs.values()}
    if not backends <= {"ollama", "vllm"}:
        _fail(f"Unsupported llm_backend values in tenant config: {sorted(backends)}")


def _validate_isolation_pack(
    path: Path,
    configs: dict[str, dict[str, Any]],
    *,
    domains: int,
    tenants_per_domain: int,
    min_probes: int,
) -> None:
    if not path.exists():
        print(f"WARN: isolation dataset not found: {path}", file=sys.stderr)
        return

    rows = _load_cases(path)
    if len(rows) < min_probes:
        _fail(f"Isolation dataset has {len(rows)} probes, requires at least {min_probes}.")

    by_domain: Counter[str] = Counter()
    by_domain_route: Counter[tuple[str, str]] = Counter()
    by_domain_route_tenant: Counter[tuple[str, str, str]] = Counter()
    tenants_by_domain: dict[str, set[str]] = defaultdict(set)
    targets_by_domain: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        tenant_id = str(row.get("tenant_id") or "").strip()
        target_tenant_id = str(row.get("target_tenant_id") or "").strip()
        route = str(row.get("expected_route") or "").strip()
        if route not in {"retrieval", "tool"}:
            _fail(f"Isolation case {row.get('id')} must use retrieval/tool expected_route, got {route}.")
        config_domain_id, _ = _tenant_domain(tenant_id, configs)
        row_domain_id = str(row.get("domain_id") or config_domain_id).strip()
        if row_domain_id != config_domain_id:
            _fail(
                f"Isolation case {row.get('id')} domain_id={row_domain_id} conflicts with tenant config domain_id={config_domain_id}."
            )
        if not target_tenant_id:
            _fail(f"Isolation case {row.get('id')} missing target_tenant_id.")
        target_domain_id, _ = _tenant_domain(target_tenant_id, configs)
        if target_domain_id != row_domain_id:
            _fail(
                f"Isolation case {row.get('id')} crosses domain {row_domain_id}->{target_domain_id}; "
                "Q2 core isolation probes must stay within domain tenant pairs."
            )
        if target_tenant_id == tenant_id:
            _fail(f"Isolation case {row.get('id')} targets the same tenant.")
        if not row.get("requires_denial"):
            _fail(f"Isolation case {row.get('id')} must require denial.")
        if not row.get("forbidden_keywords"):
            _fail(f"Isolation case {row.get('id')} missing forbidden_keywords.")
        by_domain[row_domain_id] += 1
        by_domain_route[(row_domain_id, route)] += 1
        by_domain_route_tenant[(row_domain_id, route, tenant_id)] += 1
        tenants_by_domain[row_domain_id].add(tenant_id)
        targets_by_domain[row_domain_id].add(target_tenant_id)

    if len(by_domain) != domains:
        _fail(f"Isolation dataset expected {domains} domains, found {len(by_domain)}: {sorted(by_domain)}")
    expected_per_domain = min_probes // domains
    for domain_id, count in sorted(by_domain.items()):
        if count < expected_per_domain:
            _fail(f"Isolation domain {domain_id} has {count} probes, requires at least {expected_per_domain}.")
        active_tenants = tenants_by_domain[domain_id] | targets_by_domain[domain_id]
        if len(active_tenants) != tenants_per_domain:
            _fail(
                f"Isolation domain {domain_id} uses {len(active_tenants)} tenants, "
                f"expected {tenants_per_domain}: {sorted(active_tenants)}"
            )
        for route in ("retrieval", "tool"):
            route_count = by_domain_route[(domain_id, route)]
            if route_count < expected_per_domain // 2:
                _fail(
                    f"Isolation domain {domain_id} route {route} has {route_count} probes, "
                    f"requires at least {expected_per_domain // 2}."
                )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the Q2-strong multi-domain benchmark pack.")
    parser.add_argument("--dataset", default="systems_evaluation/test_queries_q2_multidomain.json")
    parser.add_argument("--domains", type=int, default=3)
    parser.add_argument("--tenants-per-domain", type=int, default=2)
    parser.add_argument("--cases-per-domain", type=int, default=48)
    parser.add_argument("--cases-per-route-domain", type=int, default=12)
    parser.add_argument("--min-isolation-probes", type=int, default=48)
    parser.add_argument("--isolation-dataset", default="systems_evaluation/test_queries_q2_isolation.json")
    parser.add_argument("--isolation-only", action="store_true", help="Validate only the Q2 isolation dataset.")
    parser.add_argument("--skip-isolation-check", action="store_true")
    parser.add_argument(
        "--skip-corpus-check",
        action="store_true",
        help="Skip physical tenant corpus presence checks. Use only while authoring the dataset.",
    )
    args = parser.parse_args()

    configs = _load_tenant_configs()
    if args.isolation_only:
        _validate_isolation_pack(
            Path(args.isolation_dataset),
            configs,
            domains=args.domains,
            tenants_per_domain=args.tenants_per_domain,
            min_probes=args.min_isolation_probes,
        )
        _validate_model_policy(configs)
        print("PASS: Q2 isolation pack validation completed.")
        return 0

    rows = _load_cases(Path(args.dataset))
    if not rows:
        _fail("Dataset is empty.")

    ids = [str(row.get("id") or "") for row in rows]
    if any(not value for value in ids):
        _fail("Every case must have a non-empty id.")
    if len(ids) != len(set(ids)):
        _fail("Duplicate case ids detected.")

    by_domain: Counter[str] = Counter()
    by_domain_route: Counter[tuple[str, str]] = Counter()
    by_domain_route_tenant: Counter[tuple[str, str, str]] = Counter()
    tenants_by_domain: dict[str, set[str]] = defaultdict(set)

    required_fields = {"id", "tenant_id", "query", "expected_route", "category", "difficulty"}
    for row in rows:
        missing = sorted(required_fields - set(row))
        if missing:
            _fail(f"Case {row.get('id', '<unknown>')} missing fields: {', '.join(missing)}")
        route = str(row.get("expected_route") or "").strip()
        if route not in REQUIRED_ROUTES:
            _fail(f"Case {row.get('id')} has unsupported expected_route: {route}")
        tenant_id = str(row.get("tenant_id") or "").strip()
        config_domain_id, config_domain_name = _tenant_domain(tenant_id, configs)
        row_domain_id = str(row.get("domain_id") or config_domain_id).strip()
        row_domain_name = str(row.get("domain_name") or config_domain_name).strip()
        if row_domain_id != config_domain_id:
            _fail(
                f"Case {row.get('id')} domain_id={row_domain_id} conflicts with tenant config domain_id={config_domain_id}."
            )
        if not row_domain_name:
            _fail(f"Case {row.get('id')} has empty domain_name.")
        by_domain[row_domain_id] += 1
        by_domain_route[(row_domain_id, route)] += 1
        by_domain_route_tenant[(row_domain_id, route, tenant_id)] += 1
        tenants_by_domain[row_domain_id].add(tenant_id)

    if len(by_domain) != args.domains:
        _fail(f"Expected {args.domains} domains, found {len(by_domain)}: {sorted(by_domain)}")

    for domain_id, count in sorted(by_domain.items()):
        if count != args.cases_per_domain:
            _fail(f"Domain {domain_id} has {count} cases, expected {args.cases_per_domain}.")
        tenant_count = len(tenants_by_domain[domain_id])
        if tenant_count != args.tenants_per_domain:
            _fail(
                f"Domain {domain_id} has {tenant_count} tenants, expected {args.tenants_per_domain}: "
                f"{sorted(tenants_by_domain[domain_id])}"
            )
        for route in REQUIRED_ROUTES:
            route_count = by_domain_route[(domain_id, route)]
            if route_count != args.cases_per_route_domain:
                _fail(
                    f"Domain {domain_id} route {route} has {route_count} cases, "
                    f"expected {args.cases_per_route_domain}."
                )
            if args.cases_per_route_domain % args.tenants_per_domain != 0:
                _fail(
                    "cases_per_route_domain must be divisible by tenants_per_domain for balanced validation: "
                    f"{args.cases_per_route_domain} vs {args.tenants_per_domain}."
                )
            tenant_quota = args.cases_per_route_domain // args.tenants_per_domain
            for tenant_id in sorted(tenants_by_domain[domain_id]):
                tenant_route_count = by_domain_route_tenant[(domain_id, route, tenant_id)]
                if tenant_route_count != tenant_quota:
                    _fail(
                        f"Domain {domain_id} route {route} tenant {tenant_id} has {tenant_route_count} cases, "
                        f"expected {tenant_quota}."
                    )

    if not args.skip_corpus_check:
        for domain_id, tenants in sorted(tenants_by_domain.items()):
            for tenant_id in sorted(tenants):
                if not _has_content(tenant_id):
                    _fail(f"Tenant `{tenant_id}` in domain `{domain_id}` has no local corpus files or links.")

    if not args.skip_isolation_check:
        _validate_isolation_pack(
            Path(args.isolation_dataset),
            configs,
            domains=args.domains,
            tenants_per_domain=args.tenants_per_domain,
            min_probes=args.min_isolation_probes,
        )

    _validate_model_policy(configs)
    print("PASS: Q2 benchmark pack validation completed.")
    print(
        f"INFO: total={len(rows)} domains={dict(by_domain)} "
        f"tenant_counts={ {k: len(v) for k, v in tenants_by_domain.items()} }"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
