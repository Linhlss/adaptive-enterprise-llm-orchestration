# Benchmark Resource Planning

## 1. Purpose

This document summarizes the **external resources** required for the benchmark program.

It is not a code-design document. Its role is to keep the repository, environment configuration, benchmark scripts, and paper claims aligned with the actual hardware and deployment budget.

The main risks this document tries to prevent are:

- selecting models that do not fit the intended GPU budget
- writing benchmark code for `vLLM` but only being able to execute on `Ollama`
- mixing incompatible model families or quantization schemes
- underestimating storage and download requirements
- making claims in the paper that exceed the actual hardware setup

## 2. Project Framing

The project should be framed as:

> an adaptive orchestration framework for multi-domain, multi-tenant enterprise LLM serving

The benchmark program should support six core claims:

1. adaptive path routing is more useful than fixed execution modes on the same runtime
2. the evidence spans multiple domains and multiple tenants
3. tenant isolation is explicitly probed
4. model-tier choice affects quality, latency, and efficiency
5. the paper-facing benchmark is executed on one coherent hardware/backend setup
6. joint `path + model-tier` evaluation is reported through controlled replay, not overclaimed as live concurrent multi-model serving

## 3. Required Resource Groups

| Resource Group | Role | Cost Status | Priority |
| --- | --- | --- | --- |
| Cloud GPU | Main paper-facing benchmark execution | Paid | Required |
| `vLLM` runtime | OpenAI-compatible model serving for official runs | Free software, GPU required | Required |
| Hugging Face model repositories | Source of official Qwen3-AWQ checkpoints | Usually free | Required |
| Qwen3-AWQ model ladder | `strong-quality`, `balanced`, `light-latency` tiers | Model files free, execution costs GPU time | Required |
| Disk and storage | Model weights, Docker layers, logs, reports | Small paid cost or bundled | Required |
| Multi-domain corpora | Three domains, two content-bearing tenants per domain | Can be self-curated | Required |
| Benchmark packs | Main/model/stability/isolation datasets | Internal effort | Required |
| Local development machine | Code, validation, smoke testing | Already available | Required |
| Report storage | JSON artifacts, tables, logs | Low cost | Required |

## 4. Official Benchmark Hardware

### Recommended setup

Recommended paper-facing setup:

```text
1 × RTX 4090 24GB
Backend: vLLM
Model ladder: Qwen3-14B-AWQ / Qwen3-8B-AWQ / Qwen3-4B-AWQ
```

Why this setup is reasonable:

- much cheaper than A100/H100-class benchmarking
- large enough to support the core orchestration claim
- compatible with the intended AWQ model ladder
- suitable for controlled replay under a single-GPU constraint

The project should **not** treat a MacBook or CPU-only environment as the main benchmark platform.

### Backend interpretation

Recommended role split:

- `Ollama`: local development, smoke tests, early validation
- `vLLM`: official paper-facing benchmark runs

## 5. GPU Budget Estimate

Typical execution groups:

| Benchmark Cluster | Goal | Estimated Time |
| --- | --- | --- |
| Environment setup and model downloads | Bring up runtime and verify API | 2-4 hours |
| Route-only validation | Check routing and artifacts on the target backend | 1-2 hours |
| Main cross-domain benchmark | Fixed rows + adaptive path-only | 6-12 hours |
| Model sensitivity benchmark | Fixed tiers across the Qwen3-AWQ ladder | 6-12 hours |
| Stability and isolation | Repeated runs and leakage probes | 4-8 hours |
| Contingency and reruns | OOM, config errors, schema fixes, reruns | 4-8 hours |

Recommended GPU budget:

```text
Minimum: 20 GPU hours
Recommended: 30 GPU hours
Safe budget: 40 GPU hours
```

## 6. Cost Envelope

The exact price changes with the provider and date, but an RTX 4090-class rental typically keeps the entire benchmark within a modest research budget.

Practical recommendation:

```text
Prepare at least: 30 USD
Comfortable rerun budget: 50 USD
```

The paper should avoid fine-grained claims about exact cost if the environment has not been frozen and logged carefully.

## 7. `vLLM` Runtime Requirements

The benchmark code should assume a clear `vLLM` configuration path, for example:

```env
LLM_BACKEND=vllm
VLLM_BASE_URL=http://127.0.0.1:8001/v1
VLLM_API_KEY=EMPTY
ALLOW_VLLM_ONLINE_JOINT_MODEL_SELECTION=false
DEFAULT_MODEL_CLASS=adaptive
STRONG_MODEL=Qwen/Qwen3-14B-AWQ
BALANCED_MODEL=Qwen/Qwen3-8B-AWQ
LIGHT_MODEL=Qwen/Qwen3-4B-AWQ
```

If the benchmark container talks to a host-side `vLLM` server, a setup such as this may be needed:

```env
VLLM_BASE_URL=http://host.docker.internal:8001/v1
```

The benchmark outputs should always record:

- backend identity
- model class
- resolved model name
- whether the run is fixed-model, adaptive path-only, or controlled replay

## 8. Hugging Face Model Source

Recommended model repositories:

- `Qwen/Qwen3-14B-AWQ`
- `Qwen/Qwen3-8B-AWQ`
- `Qwen/Qwen3-4B-AWQ`

Why this model ladder is preferred:

- same model family
- same quantization family
- cleaner comparison across quality/latency tiers
- lower confounding than mixing unrelated providers and model families

## 9. Storage Considerations

The repository and benchmark plan should assume enough space for:

- three AWQ checkpoints
- Docker images and layers
- generated corpora
- prediction artifacts and answer reports
- replay shards and merged outputs

The paper should not ignore storage constraints when presenting reproducibility.

## 10. Claim Discipline

Safe claim:

> the benchmark is executed on a controlled single-GPU setup with a unified model family and a controlled replay protocol for joint `path + model-tier` evaluation

Unsafe claim:

> the system has already solved general online multi-model orchestration at production scale

## 11. Practical Conclusion

The benchmark program should remain aligned with the following principles:

- one coherent backend policy
- one coherent model-family ladder
- explicit budget awareness
- explicit replay-based interpretation for joint adaptation
- paper claims that match the real deployment setup
