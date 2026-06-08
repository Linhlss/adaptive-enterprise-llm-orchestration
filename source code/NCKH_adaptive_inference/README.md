# Adaptive Orchestration for Multi-Domain, Multi-Tenant Enterprise LLM Serving

This repository contains a runnable research prototype for adaptive enterprise LLM orchestration and the current Q2 benchmark-construction pipeline.

Current interpretation:

- multi-tenant runtime that decides among retrieval, tool use, general generation, and safe refusal
- Q2 benchmark workflow for multi-domain evaluation
- controlled replay for joint `path + model-tier` evaluation under single-GPU constraints

This repository should be read as:

- a serious research implementation
- a validated benchmark-construction pipeline
- an in-progress paper artifact with explicit claim discipline

This repository should not be read as:

- a production platform
- a benchmark-complete publication artifact
- a finished journal package

## Repository Map

- runtime code: `enterprise_runtime/`
- evaluation and benchmark scripts: `systems_evaluation/`
- active docs: `docs/`
- container setup: `Dockerfile`, `docker-compose.yml`, `Makefile`

Start here:

1. [docs/02_active_guides/EXTERNAL_REPO_STATUS.md](docs/02_active_guides/EXTERNAL_REPO_STATUS.md)
2. [docs/02_active_guides/SETUP_AND_DEV_GUIDE.md](docs/02_active_guides/SETUP_AND_DEV_GUIDE.md)
3. [docs/02_active_guides/FRAMEWORK_DIAGRAMS.md](docs/02_active_guides/FRAMEWORK_DIAGRAMS.md)
4. [docs/01_source_of_truth/RESEARCH_FOCUS.md](docs/01_source_of_truth/RESEARCH_FOCUS.md)

## Quick Start

```bash
cp .env.example .env
make bootstrap
make build-q2-corpus
make prepare-q2-pack
make validate-q2-pack
make validate-q2-content
make check-q2-readiness
```

Move to `benchmark-q2-*` targets only after backend readiness is verified.

## Scope Notes

- `Ollama` is for local smoke and development.
- `vLLM` is the intended backend for official Q2 benchmark runs.
- Joint online multi-model serving is not claimed; model-tier experiments use controlled replay unless explicitly stated otherwise.

## External Proposal Materials

- [Cold email draft for Dr. Qinghua Lu](docs/02_active_guides/COLD_EMAIL_PROPOSAL_DR_LU.md)
- [Relevance brief for Dr. Qinghua Lu](docs/02_active_guides/RELEVANCE_BRIEF_DR_LU.md)
