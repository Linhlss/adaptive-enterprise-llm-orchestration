# Setup And Dev Guide

This guide describes how to use the repository under its current paper-facing scope.

Project framing:

`Adaptive orchestration for multi-domain, multi-tenant enterprise LLM serving`

Interpretation rules:

- `Docker-first` for runtime and benchmark work
- `Ollama` for local smoke and development only
- `vLLM` for official Q2 benchmark runs
- `controlled replay` for joint `path + model-tier` evaluation under single-GPU constraints

## 1. Core Services

Main runtime:

- `enterprise_runtime/`
- API entrypoint: `enterprise_runtime.api:app`

Evaluation stack:

- `systems_evaluation/`

Q2 corpora:

- `data/tenants/<tenant_id>/files/`

## 2. Bootstrap

Create `.env`:

```bash
cp .env.example .env
```

Build and start services:

```bash
make bootstrap
make ps
```

Open a shell in the dev container:

```bash
make dev-shell
```

Default local endpoints:

- API: `http://127.0.0.1:8000`
- UI: `http://127.0.0.1:8501`

## 3. Recommended Environment Variables

Important variables:

- `LLM_BACKEND`
- `DEFAULT_MODEL_CLASS`
- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`
- `VLLM_BASE_URL`
- `VLLM_API_KEY`
- `ALLOW_VLLM_ONLINE_JOINT_MODEL_SELECTION`
- `FIXED_ROUTE_MODE`

Recommended default:

```env
FIXED_ROUTE_MODE=adaptive
```

Only override fixed route mode intentionally for benchmark rows.

## 4. Runtime Checks

Health:

- `GET /health`

Status:

- `GET /status?tenant_id=academic_department&user_id=guest`

Chat telemetry of interest:

- `route_reason`
- `route_score`
- `route_candidates`
- `route_mode`
- `route_policy`
- `shared_model_name`
- `adapter_enabled`
- `adapter_available`

## 5. Q2 Build And Validation Flow

Build or refresh the corpora:

```bash
make build-q2-corpus
make audit-q2-corpus
```

Prepare the benchmark packs:

```bash
make prepare-q2-pack
```

Validate dataset structure:

```bash
make validate-q2-pack
make validate-q2-model-sensitivity
make validate-q2-stability-subset
make validate-q2-isolation
```

Validate content semantics:

```bash
make validate-q2-content
```

Check operational readiness:

```bash
make check-q2-readiness
```

## 6. Benchmark Flow

Route-only benchmark rows:

```bash
make benchmark-q2-routeonly
```

End-to-end fixed and path-only rows:

```bash
make benchmark-q2-e2e
```

Joint adaptive replay:

```bash
make benchmark-q2-joint-replay
```

Model sensitivity:

```bash
make benchmark-q2-model-sensitivity
```

Stability:

```bash
make benchmark-q2-stability
```

Isolation:

```bash
make benchmark-q2-isolation
```

Build tables:

```bash
make build-q2-main-table
make build-q2-model-sensitivity-table
make build-q2-stability-table
make build-q2-isolation-table
```

## 7. Important Caveat

The repository currently supports:

- validated Q2 benchmark construction
- route-level and replay-level orchestration evaluation
- paper-facing command paths for the official Q2 workflow

The repository does not currently guarantee:

- that `vLLM` is already correctly serving the target Qwen3-AWQ ladder on the current machine
- that every generated Q2 query has already been empirically stress-tested under the final backend

Read [EXTERNAL_REPO_STATUS.md](EXTERNAL_REPO_STATUS.md) before treating the repo as benchmark-complete.
