# Setup And Dev Guide

This guide describes how to use the repository under its current paper-facing scope.

Project framing:

`Adaptive orchestration for multi-domain, multi-tenant enterprise LLM serving`

Interpretation rules:

- `Docker-first` for runtime and benchmark work
- `Ollama` for local smoke and development only
- `vLLM` for official benchmark runs
- `controlled replay` for joint `path + model-tier` evaluation under single-GPU constraints

## 1. Core Services

Main runtime:

- `enterprise_runtime/`
- API entrypoint: `enterprise_runtime.api:app`

Evaluation stack:

- `systems_evaluation/`

Benchmark corpora:

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

## 5. Benchmark Build And Validation Flow

Build or refresh the corpora:

```bash
make build-benchmark-corpus
make audit-benchmark-corpus
```

Prepare the benchmark packs:

```bash
make prepare-benchmark-pack
```

Validate dataset structure:

```bash
make validate-benchmark-pack
make validate-model-sensitivity-pack
make validate-stability-pack
make validate-isolation-pack
```

Validate content semantics:

```bash
make validate-benchmark-content
```

Check operational readiness:

```bash
make check-benchmark-readiness
```

## 6. Benchmark Flow

Route-only benchmark rows:

```bash
make benchmark-route-policy
```

End-to-end fixed and path-only rows:

```bash
make benchmark-end-to-end
```

Joint adaptive replay:

```bash
make benchmark-joint-replay
```

Model sensitivity:

```bash
make benchmark-model-sensitivity
```

Stability:

```bash
make benchmark-stability
```

Isolation:

```bash
make benchmark-isolation
```

Build tables:

```bash
make build-main-table
make build-model-sensitivity-table
make build-stability-table
make build-isolation-table
```

## 7. Important Caveat

The repository currently supports:

- validated benchmark construction
- route-level and replay-level orchestration evaluation
- paper-facing command paths for the official benchmark workflow

The repository does not currently guarantee:

- that `vLLM` is already correctly serving the target Qwen3-AWQ ladder on the current machine
- that every generated benchmark query has already been empirically stress-tested under the final backend

Read [EXTERNAL_REPO_STATUS.md](EXTERNAL_REPO_STATUS.md) before treating the repo as benchmark-complete.
