from __future__ import annotations

import argparse
from dataclasses import replace
import json
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from enterprise_runtime.api_helpers import parse_sources_from_answer
from enterprise_runtime.config import (
    OLLAMA_BASE_URL,
    VLLM_API_KEY,
    VLLM_BASE_URL,
    bootstrap_dirs,
    ensure_default_config,
    init_embedding_settings,
)
from enterprise_runtime.llm_service import get_or_create_profile, normalize_backend, resolve_model_selection
from enterprise_runtime.memory_store import MemoryStore
from enterprise_runtime.router import RouterResult, route_question
from enterprise_runtime.utils import sanitize_id
from enterprise_runtime.workflow import run_workflow_with_trace

from systems_evaluation.evaluate_answers import evaluate_predictions as evaluate_answer_predictions
from systems_evaluation.evaluate_answers import render_markdown as render_answer_markdown
from systems_evaluation.evaluate_retrieval import load_cases
from systems_evaluation.backend_preflight import probe_backend_http


def _warmup_runtime(
    cases,
    benchmark_label: str = "benchmark",
    fixed_route_mode: str | None = None,
    model_class: str | None = None,
    llm_backend: str | None = None,
    fast_mode: bool = False,
    route_only: bool = False,
    comparison_mode: str = "standard",
    max_tenants: int = 10,
) -> None:
    tenant_ids: list[str] = []
    for case in cases:
        if case.tenant_id not in tenant_ids:
            tenant_ids.append(case.tenant_id)
    tenant_ids = tenant_ids[: max(1, max_tenants)]

    for tenant_id in tenant_ids:
        profile = get_or_create_profile(tenant_id)
        if fixed_route_mode:
            profile = replace(profile, fixed_route_mode=fixed_route_mode)
        if model_class:
            profile = replace(profile, model_class=model_class)
        if llm_backend:
            profile = replace(profile, llm_backend=llm_backend)
        # Preload runtime/index cache in-process for this benchmark run.
        if not route_only:
            from enterprise_runtime.runtime_manager import get_runtime

            _ = get_runtime(profile)

    if route_only:
        return

    seeded_routes: set[str] = set()
    warmup_user_id = f"warmup_{sanitize_id(benchmark_label, 'benchmark')}"
    for case in cases:
        if case.expected_route in seeded_routes:
            continue
        profile = get_or_create_profile(case.tenant_id)
        if fixed_route_mode:
            profile = replace(profile, fixed_route_mode=fixed_route_mode)
        if model_class:
            profile = replace(profile, model_class=model_class)
        if llm_backend:
            profile = replace(profile, llm_backend=llm_backend)
        MemoryStore(profile.tenant_id, warmup_user_id).reset()
        base_route = route_question(case.query, profile, warmup_user_id)
        effective_route = _apply_comparison_mode(base_route, comparison_mode)
        _answer, _trace = run_workflow_with_trace(
            profile=profile,
            user_id=warmup_user_id,
            question=case.query,
            show_sources=False,
            route_result=effective_route,
            fast_mode=fast_mode,
        )
        seeded_routes.add(case.expected_route)
        if len(seeded_routes) >= 4:
            break


def _apply_comparison_mode(route_result: RouterResult, mode: str) -> RouterResult:
    if mode == "standard":
        return route_result

    if mode == "adaptive_retrieval_only":
        if route_result.route == "tool":
            return RouterResult(
                route="retrieval",
                reason="Representative adaptive retrieval-only: tool path remapped to retrieval.",
                score=route_result.score,
                candidates=route_result.candidates,
                features=route_result.features,
                policy="representative_adaptive_retrieval_only",
            )
        return RouterResult(
            route=route_result.route,
            reason=f"Representative adaptive retrieval-only: {route_result.reason}",
            score=route_result.score,
            candidates=route_result.candidates,
            features=route_result.features,
            policy="representative_adaptive_retrieval_only",
            direct_answer=route_result.direct_answer,
        )

    if mode == "tool_centric_workflow":
        if route_result.route == "out_of_scope":
            return RouterResult(
                route="out_of_scope",
                reason="Representative tool-centric workflow: keep out_of_scope fallback.",
                score=route_result.score,
                candidates=route_result.candidates,
                features=route_result.features,
                policy="representative_tool_centric_workflow",
            )
        if route_result.route == "tool" and route_result.direct_answer:
            return RouterResult(
                route="tool",
                reason="Representative tool-centric workflow: direct tool match.",
                score=route_result.score,
                candidates=route_result.candidates,
                features=route_result.features,
                policy="representative_tool_centric_workflow",
                direct_answer=route_result.direct_answer,
            )
        return RouterResult(
            route="retrieval",
            reason="Representative tool-centric workflow: non-tool routes fallback to retrieval.",
            score=route_result.score,
            candidates=route_result.candidates,
            features=route_result.features,
            policy="representative_tool_centric_workflow",
        )

    raise ValueError(f"Unsupported comparison mode: {mode}")


def _source_item_to_name(item) -> str:
    if hasattr(item, "name"):
        return str(item.name)
    if isinstance(item, dict):
        return str(item.get("name") or item.get("source") or "")
    return str(item)


def _benchmark_eval_user_id(case_id: str, benchmark_label: str) -> str:
    safe_label = sanitize_id(benchmark_label, "benchmark")
    safe_case = sanitize_id(case_id, "case")
    return f"eval_{safe_label}_{safe_case}"


def _replay_route_result(case, profile, user_id: str) -> RouterResult | None:
    replay_route = str(getattr(case, "replay_selected_route", "") or "").strip()
    if not replay_route:
        return None

    direct_answer = str(getattr(case, "replay_direct_answer", "") or "").strip() or None
    direct_answer_detected = bool(getattr(case, "replay_direct_answer_detected", False))
    if replay_route == "tool" and direct_answer_detected and not direct_answer:
        raise SystemExit(
            f"Case {case.id} recorded a tool direct-answer decision in the replay trace but no direct_answer payload."
        )

    return RouterResult(
        route=replay_route,
        reason=str(getattr(case, "replay_route_reason", "") or "Controlled replay route from policy trace."),
        score=float(getattr(case, "replay_route_score", 0.0) or 0.0),
        candidates=dict(getattr(case, "replay_route_candidates", {}) or {}),
        features=dict(getattr(case, "replay_route_features", {}) or {}),
        policy=str(getattr(case, "replay_route_policy", "") or "controlled_replay_policy_trace"),
        direct_answer=direct_answer,
    )

def run_predictions(
    dataset_path: Path,
    benchmark_label: str = "benchmark",
    fixed_route_mode: str | None = None,
    model_class: str | None = None,
    llm_backend: str | None = None,
    fast_mode: bool = False,
    route_only: bool = False,
    comparison_mode: str = "standard",
    warmup: bool = False,
    warmup_max_tenants: int = 10,
    replay_route_from_dataset: bool = False,
) -> list[dict]:
    bootstrap_dirs()
    ensure_default_config()
    init_embedding_settings()

    cases = load_cases(dataset_path)
    if warmup:
        _warmup_runtime(
            cases=cases,
            benchmark_label=benchmark_label,
            fixed_route_mode=fixed_route_mode,
            model_class=model_class,
            llm_backend=llm_backend,
            fast_mode=fast_mode,
            route_only=route_only,
            comparison_mode=comparison_mode,
            max_tenants=warmup_max_tenants,
        )

    predictions = []
    for index, case in enumerate(cases, start=1):
        profile = get_or_create_profile(case.tenant_id)
        if fixed_route_mode:
            profile = replace(profile, fixed_route_mode=fixed_route_mode)
        if model_class:
            profile = replace(profile, model_class=model_class)
        if llm_backend:
            profile = replace(profile, llm_backend=llm_backend)
        started = time.perf_counter()
        explicit_user_id = str(getattr(case, "user_id", "") or "").strip()
        default_eval_user = f"eval_{case.id}"
        generated_eval_user = (not explicit_user_id) or (explicit_user_id == default_eval_user)
        if generated_eval_user:
            explicit_user_id = ""
        eval_user_id = explicit_user_id or _benchmark_eval_user_id(case.id, benchmark_label)
        if generated_eval_user:
            MemoryStore(profile.tenant_id, eval_user_id).reset()
        if replay_route_from_dataset:
            if not model_class and getattr(case, "replay_model_class", ""):
                profile = replace(profile, model_class=str(case.replay_model_class))
            base_route = _replay_route_result(case, profile, eval_user_id)
            if base_route is None:
                raise SystemExit(
                    f"Case {case.id} missing replay_selected_route while --replay-route-from-dataset is enabled."
                )
        else:
            base_route = route_question(case.query, profile, eval_user_id)
        if route_only and fixed_route_mode == "tool":
            base_route = RouterResult(
                route="tool",
                reason="Route-only fixed tool baseline: force tool route for controlled comparison.",
                score=1.0,
                policy="fixed_route",
                direct_answer=base_route.direct_answer,
                candidates=base_route.candidates,
                features=base_route.features,
            )
        effective_route = _apply_comparison_mode(base_route, comparison_mode)

        if route_only:
            latency_ms = int((time.perf_counter() - started) * 1000)
            selection = resolve_model_selection(profile, route_result=effective_route, question=case.query)
            predictions.append({
                "id": case.id,
                "tenant_id": case.tenant_id,
                "domain_id": profile.domain_id,
                "domain_name": profile.domain_name,
                "user_id": eval_user_id,
                "query": case.query,
                "route": effective_route.route,
                "answer": "",
                "sources": [],
                "latency_ms": latency_ms,
                "route_reason": effective_route.reason,
                "route_score": effective_route.score,
                "route_mode": "fixed" if effective_route.policy == "fixed_route" else "adaptive",
                "route_policy": effective_route.policy,
                "used_adapter": "base",
                "adapter_available": False,
                "model_class": selection.model_class,
                "llm_backend": selection.backend,
                "shared_model_name": selection.model_name,
                "model_name": selection.model_name,
                "model_selection_policy": selection.selection_policy,
                "direct_answer": effective_route.direct_answer or "",
            })
            print(f"[{index}/{len(cases)}] {case.id} route={effective_route.route} latency={latency_ms}ms")
            continue

        answer, trace = run_workflow_with_trace(
            profile=profile,
            user_id=eval_user_id,
            question=case.query,
            show_sources=not fast_mode,
            route_result=effective_route,
            fast_mode=fast_mode,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        sources = parse_sources_from_answer(answer)

        predictions.append({
            "id": case.id,
            "tenant_id": case.tenant_id,
            "domain_id": profile.domain_id,
            "domain_name": profile.domain_name,
            "user_id": eval_user_id,
            "query": case.query,
            "route": trace.route,
            "answer": answer,
            "sources": [_source_item_to_name(item) for item in sources],
            "retrieved_context": trace.retrieved_context or "",
            "retrieved_sources": trace.retrieved_sources or [],
            "latency_ms": latency_ms,
            "route_reason": trace.route_reason,
            "route_score": trace.route_score,
            "route_mode": trace.route_mode,
            "route_policy": trace.route_policy,
            "used_adapter": trace.used_adapter,
            "adapter_available": trace.adapter_available,
            "model_class": trace.model_class,
            "llm_backend": trace.llm_backend,
            "shared_model_name": trace.shared_model_name,
            "model_name": trace.model_name,
            "model_selection_policy": trace.model_selection_policy,
        })
        print(f"[{index}/{len(cases)}] {case.id} route={trace.route} latency={latency_ms}ms")
    return predictions

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="systems_evaluation/test_queries_multidomain.json")
    parser.add_argument("--label", default="baseline_real")
    parser.add_argument("--output-dir", default="systems_evaluation/generated_reports")
    parser.add_argument("--fixed-route-mode", choices=["adaptive", "tool", "retrieval", "general", "out_of_scope"], default=None)
    parser.add_argument(
        "--model-class",
        choices=["strong-quality", "balanced", "light-latency", "adaptive", "custom"],
        default=None,
        help="Override profile model class for fixed-model runs or controlled-replay benchmark rows.",
    )
    parser.add_argument(
        "--llm-backend",
        choices=["ollama", "vllm"],
        default=None,
        help="Override LLM backend for this benchmark run.",
    )
    parser.add_argument("--fast-mode", action="store_true", help="Reduce chain depth for faster benchmark iteration.")
    parser.add_argument("--route-only", action="store_true", help="Evaluate routing/trace only without LLM generation.")
    parser.add_argument("--warmup", action="store_true", help="Warm caches/model/index in-process before timed loop.")
    parser.add_argument("--warmup-max-tenants", type=int, default=10)
    parser.add_argument(
        "--replay-route-from-dataset",
        action="store_true",
        help="Use replay_selected_route metadata embedded in dataset rows instead of rerunning the router.",
    )
    parser.add_argument(
        "--comparison-mode",
        choices=["standard", "adaptive_retrieval_only", "tool_centric_workflow"],
        default="standard",
        help="Representative comparison mode for non-fixed baselines.",
    )
    args = parser.parse_args()

    if args.replay_route_from_dataset and args.route_only:
        raise SystemExit("--replay-route-from-dataset is only valid for end-to-end controlled replay passes.")
    if args.model_class == "adaptive" and not args.route_only:
        raise SystemExit(
            "Adaptive end-to-end model-tier benchmarking must use the controlled replay pipeline. "
            "Run a route-only policy pass first, then execute per-tier replay datasets."
        )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = Path(args.dataset)

    if not args.route_only:
        backend = normalize_backend(args.llm_backend)
        cases = load_cases(dataset_path)
        required_models: set[str] = set()
        if args.replay_route_from_dataset:
            for case in cases:
                replay_model_class = str(getattr(case, "replay_model_class", "") or "").strip()
                if replay_model_class:
                    profile = get_or_create_profile(case.tenant_id)
                    profile = replace(profile, model_class=replay_model_class)
                    if args.llm_backend:
                        profile = replace(profile, llm_backend=args.llm_backend)
                    required_models.add(resolve_model_selection(profile, question=case.query).model_name)
        elif args.model_class and args.model_class != "adaptive":
            if cases:
                profile = get_or_create_profile(cases[0].tenant_id)
                profile = replace(profile, model_class=args.model_class)
                if args.llm_backend:
                    profile = replace(profile, llm_backend=args.llm_backend)
                required_models.add(resolve_model_selection(profile, question=cases[0].query).model_name)
        required_models = {item for item in required_models if item}

        probe = probe_backend_http(
            backend=backend,
            base_url=VLLM_BASE_URL if backend == "vllm" else OLLAMA_BASE_URL,
            expected_models=sorted(required_models),
            api_key=VLLM_API_KEY if backend == "vllm" else "",
        )
        if not probe.ok:
            missing_models = f" missing_models={probe.missing_models}" if probe.missing_models else ""
            detail = probe.error or f"available_models={probe.available_models}"
            print(f"{backend} backend preflight failed at {probe.endpoint}:{missing_models} {detail}".strip(), file=sys.stderr)
            return 2

    predictions = run_predictions(
        dataset_path,
        benchmark_label=args.label,
        fixed_route_mode=args.fixed_route_mode,
        model_class=args.model_class,
        llm_backend=args.llm_backend,
        fast_mode=args.fast_mode,
        route_only=args.route_only,
        comparison_mode=args.comparison_mode,
        warmup=args.warmup,
        warmup_max_tenants=args.warmup_max_tenants,
        replay_route_from_dataset=args.replay_route_from_dataset,
    )
    pred_path = output_dir / f"{args.label}_predictions.json"
    pred_path.write_text(json.dumps(predictions, ensure_ascii=False, indent=2), encoding="utf-8")

    cases = load_cases(dataset_path)
    answer_report = evaluate_answer_predictions(cases, predictions)

    (output_dir / f"{args.label}_answer_report.json").write_text(
        json.dumps(answer_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / f"{args.label}_answer_report.md").write_text(
        render_answer_markdown(answer_report, args.label),
        encoding="utf-8",
    )

    print(f"Saved predictions to {pred_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
