from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
TENANT_CONFIG = BASE_DIR / "config" / "tenants.json"
REQUIRED_ROUTES = ["retrieval", "tool", "general", "out_of_scope"]


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise SystemExit(f"{path} must contain a JSON list.")
    return [dict(row) for row in rows]


def _load_tenant_domains() -> dict[str, dict[str, str]]:
    raw = json.loads(TENANT_CONFIG.read_text(encoding="utf-8")) if TENANT_CONFIG.exists() else {}
    out: dict[str, dict[str, str]] = {}
    benchmark_only = any(bool(cfg.get("benchmark_domain_pack")) for cfg in raw.values())
    for tenant_id, cfg in raw.items():
        if benchmark_only and not bool(cfg.get("benchmark_domain_pack")):
            continue
        out[str(tenant_id)] = {
            "domain_id": str(cfg.get("domain_id") or "academic_admin"),
            "domain_name": str(cfg.get("domain_name") or "Academic and administrative support"),
        }
    return out


def _case_domain(row: dict[str, Any], tenant_domains: dict[str, dict[str, str]]) -> tuple[str, str]:
    tenant_id = str(row.get("tenant_id") or "default")
    cfg = tenant_domains.get(tenant_id, {})
    domain_id = str(row.get("domain_id") or cfg.get("domain_id") or "").strip()
    domain_name = str(row.get("domain_name") or cfg.get("domain_name") or domain_id).strip()
    if not domain_id:
        raise SystemExit(f"Case {row.get('id', '<unknown>')} has no domain_id and tenant has no domain config.")
    return domain_id, domain_name


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        key = (
            str(row.get("tenant_id", "")).strip(),
            str(row.get("expected_route", "")).strip(),
            str(row.get("query", "")).strip(),
            str(row.get("category", "")).strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _rewrite_ids(rows: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    counters: Counter[tuple[str, str]] = Counter()
    out: list[dict[str, Any]] = []
    for row in rows:
        domain_id = str(row["domain_id"])
        route = str(row["expected_route"])
        counters[(domain_id, route)] += 1
        item = dict(row)
        item["id"] = f"{prefix}_{domain_id.upper()}_{route.upper()}_{counters[(domain_id, route)]:02d}"
        out.append(item)
    return out


def _balanced_pick(rows: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    by_difficulty: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    for row in rows:
        by_difficulty[str(row.get("difficulty") or "medium")].append(row)

    ordered_difficulties = sorted(by_difficulty)
    picked: list[dict[str, Any]] = []
    while len(picked) < count:
        progressed = False
        for difficulty in ordered_difficulties:
            bucket = by_difficulty[difficulty]
            if not bucket:
                continue
            picked.append(bucket.popleft())
            progressed = True
            if len(picked) >= count:
                break
        if not progressed:
            break
    return picked


def _interleave_tenants(rows_by_tenant: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    queues = {tenant_id: deque(rows) for tenant_id, rows in sorted(rows_by_tenant.items())}
    ordered: list[dict[str, Any]] = []
    while True:
        progressed = False
        for tenant_id in sorted(queues):
            bucket = queues[tenant_id]
            if not bucket:
                continue
            ordered.append(bucket.popleft())
            progressed = True
        if not progressed:
            break
    return ordered


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a strong-evidence balanced multi-domain benchmark dataset from source query files."
    )
    parser.add_argument(
        "--input",
        nargs="+",
        default=[
            "systems_evaluation/test_queries_source.json",
        ],
    )
    parser.add_argument("--output", default="systems_evaluation/test_queries_multidomain.json")
    parser.add_argument("--cases-per-route-domain", type=int, default=12)
    parser.add_argument("--min-tenants-per-domain", type=int, default=2)
    parser.add_argument("--required-domains", type=int, default=3)
    parser.add_argument(
        "--domains",
        nargs="*",
        default=[],
        help="Optional domain_id allow-list. If omitted, all domains found in the source rows are considered.",
    )
    parser.add_argument("--id-prefix", default="BENCH")
    args = parser.parse_args()

    tenant_domains = _load_tenant_domains()
    source_rows: list[dict[str, Any]] = []
    for value in args.input:
        path = Path(value)
        if path.exists():
            source_rows.extend(_load_json_list(path))

    rows = _dedupe_rows(source_rows)
    if not rows:
        raise SystemExit("No source rows found.")

    allowed_domains = {d.strip() for d in args.domains if d.strip()}
    by_domain_route: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    tenants_by_domain: dict[str, set[str]] = defaultdict(set)

    for row in rows:
        route = str(row.get("expected_route") or "").strip()
        if route not in REQUIRED_ROUTES:
            continue
        tenant_id = str(row.get("tenant_id") or "default").strip()
        if tenant_id not in tenant_domains:
            continue
        domain_id, domain_name = _case_domain(row, tenant_domains)
        if allowed_domains and domain_id not in allowed_domains:
            continue
        item = dict(row)
        item["tenant_id"] = tenant_id
        item["domain_id"] = domain_id
        item["domain_name"] = domain_name
        by_domain_route[(domain_id, route)].append(item)
        tenants_by_domain[domain_id].add(tenant_id)

    domains = sorted(tenants_by_domain)
    if len(domains) != args.required_domains:
        raise SystemExit(f"Need exactly {args.required_domains} domains, found {len(domains)}: {domains}")

    selected: list[dict[str, Any]] = []
    for domain_id in domains:
        tenant_count = len(tenants_by_domain[domain_id])
        if tenant_count < args.min_tenants_per_domain:
            raise SystemExit(
                f"Domain {domain_id} has {tenant_count} tenants, "
                f"requires at least {args.min_tenants_per_domain}."
            )
        for route in REQUIRED_ROUTES:
            candidates = by_domain_route.get((domain_id, route), [])
            if len(candidates) < args.cases_per_route_domain:
                raise SystemExit(
                    f"Domain {domain_id} route {route} has {len(candidates)} cases, "
                    f"requires {args.cases_per_route_domain}."
                )
            tenant_ids = sorted({str(row["tenant_id"]) for row in candidates})
            if len(tenant_ids) < args.min_tenants_per_domain:
                raise SystemExit(
                    f"Domain {domain_id} route {route} uses only {len(tenant_ids)} tenants: {tenant_ids}"
                )
            if args.cases_per_route_domain % args.min_tenants_per_domain != 0:
                raise SystemExit(
                    "cases-per-route-domain must be divisible by min-tenants-per-domain "
                    f"for balanced sampling: {args.cases_per_route_domain} vs {args.min_tenants_per_domain}"
                )

            tenant_quota = args.cases_per_route_domain // args.min_tenants_per_domain
            by_tenant: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for item in candidates:
                by_tenant[str(item["tenant_id"])].append(item)

            selected_by_tenant: dict[str, list[dict[str, Any]]] = {}
            for tenant_id in sorted(by_tenant):
                picked = _balanced_pick(by_tenant[tenant_id], tenant_quota)
                if len(picked) < tenant_quota:
                    raise SystemExit(
                        f"Domain {domain_id} route {route} tenant {tenant_id} has only {len(picked)} "
                        f"balanced candidates, requires {tenant_quota}."
                    )
                selected_by_tenant[tenant_id] = picked

            selected.extend(_interleave_tenants(selected_by_tenant))

    selected = _rewrite_ids(selected, prefix=args.id_prefix)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")

    route_counts = Counter(row["expected_route"] for row in selected)
    domain_counts = Counter(row["domain_id"] for row in selected)
    print(
        f"Saved {len(selected)} Benchmark cases to {output_path} | "
        f"domains={dict(domain_counts)} | routes={dict(route_counts)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
