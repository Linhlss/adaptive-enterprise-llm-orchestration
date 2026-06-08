# Adaptive Orchestration for Multi-Domain, Multi-Tenant Enterprise LLM Serving

This repository is the implementation workspace for a systems-and-application study on adaptive enterprise LLM orchestration.

The current paper-facing scope is:

- multi-domain, multi-tenant enterprise serving
- adaptive execution-path selection across `retrieval`, `tool`, `general`, and `out_of_scope`
- controlled model-tier evaluation on the `Qwen3-AWQ` ladder
- tenant-aware runtime boundaries and route-level evidence
- reproducible benchmark construction for cross-domain evaluation

The repo does **not** claim:

- a new foundation model
- a new retrieval algorithm
- a new learned router
- online concurrent multi-model serving as the main evidence

For joint `path + model-tier` evaluation, the policy decision is recorded once and executed through controlled replay on the same backend and hardware.

## Current Status

What is implemented:

- FastAPI-based serving runtime in `enterprise_runtime/`
- heuristic path router with route telemetry
- tenant-aware retrieval, file/tool path, memory, and runtime metadata
- Q2 multi-domain corpus scaffold with 6 tenants across 3 domains
- benchmark builders, validators, isolation pack, and controlled replay pipeline

What is validated:

- Q2 source-pack generation from the current tenant corpora
- balanced Q2 benchmark-pack construction
- strict semantic validation for main/model/stability/isolation packs
- controlled replay data preparation for joint `path + model-tier` evaluation

What is still in progress:

- paper-facing full benchmark execution on `vLLM`
- retrieval/source prompts and routing behavior hardening across all Q2 cases
- final benchmark tables backed by clean end-to-end runs

This is best read as a runnable prototype with a validated benchmark construction pipeline, not as a benchmark-complete artifact.

## Repository Layout

- `enterprise_runtime/`: serving runtime, router, workflow, retrieval, tools, API
- `systems_evaluation/`: benchmark preparation, validation, execution, replay, reporting
- `data/tenants/`: tenant-scoped corpora for the Q2 benchmark packs
- `config/tenants.json`: tenant/domain metadata
- `docs/`: research framing, setup, validation, limitations, public-facing status

Supporting personalization code remains in the repo as a secondary layer, not the core contribution.

## Recommended Reading

Start here:

1. [docs/README.md](source%20code/NCKH_adaptive_inference/docs/README.md)
2. [docs/01_source_of_truth/RESEARCH_FOCUS.md](source%20code/NCKH_adaptive_inference/docs/01_source_of_truth/RESEARCH_FOCUS.md)
3. [docs/02_active_guides/EXTERNAL_REPO_STATUS.md](source%20code/NCKH_adaptive_inference/docs/02_active_guides/EXTERNAL_REPO_STATUS.md)
4. [docs/02_active_guides/SETUP_AND_DEV_GUIDE.md](source%20code/NCKH_adaptive_inference/docs/02_active_guides/SETUP_AND_DEV_GUIDE.md)
5. [docs/02_active_guides/BENCHMARK_LIMITATIONS.md](source%20code/NCKH_adaptive_inference/docs/02_active_guides/BENCHMARK_LIMITATIONS.md)

## Quick Start

Create `.env`:

```bash
cp .env.example .env
```

Build and start the core services:

```bash
make bootstrap
make ps
```

Open a shell in the dev container:

```bash
make dev-shell
```

## Q2 Workflow

Build or audit the Q2 corpora:

```bash
make build-q2-corpus
make audit-q2-corpus
```

Prepare and validate the paper-facing Q2 packs:

```bash
make prepare-q2-pack
make validate-q2-pack
make validate-q2-content
make check-q2-readiness
```

Run paper-facing benchmark stages:

```bash
make benchmark-q2-routeonly
make benchmark-q2-e2e
make benchmark-q2-joint-replay
make benchmark-q2-model-sensitivity
make benchmark-q2-stability
make benchmark-q2-isolation
```

Build tables from completed runs:

```bash
make build-q2-main-table
make build-q2-model-sensitivity-table
make build-q2-stability-table
make build-q2-isolation-table
```

## Backend Policy

- `Ollama`: local development and smoke checks
- `vLLM`: official benchmark backend for paper-facing runs

The intended model ladder is:

- `Qwen3-14B-AWQ` as `strong-quality`
- `Qwen3-8B-AWQ` as `balanced`
- `Qwen3-4B-AWQ` as `light-latency`

The repository currently assumes:

- route-only policy passes may use `--model-class adaptive`
- end-to-end adaptive model-tier execution must go through controlled replay

## Public-Facing Claim Discipline

If you are reading this repository externally, the safe summary is:

> This project implements a tenant-aware enterprise LLM runtime and a validated multi-domain benchmark-construction pipeline for studying adaptive orchestration. The codebase already supports route-level evaluation and controlled replay for joint path-and-model policy analysis, while the final paper-facing benchmark runs remain an active execution task.
