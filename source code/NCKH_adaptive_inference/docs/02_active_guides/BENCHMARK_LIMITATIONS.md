# Benchmark Limitations

This document states the current benchmark limitations conservatively for the cleaned repo surface.

## 1. Scope Discipline

The repository should be read as:

- a runnable enterprise LLM orchestration prototype
- a validated multi-domain benchmark-construction pipeline
- an active benchmark execution workspace

It should not yet be read as:

- a benchmark-complete journal artifact
- a production-readiness proof
- an online concurrent multi-model serving system

## 2. Backend Readiness

The paper-facing backend policy is:

- `Ollama` for development and smoke
- `vLLM` for official benchmark runs

If `vLLM` is not correctly serving the intended Qwen3-AWQ model ladder from the benchmark container, the benchmark is not ready for final evidence collection even if all dataset validators pass.

## 3. Metric Limitations

Current answer evaluation remains lightweight and rubric-driven.

Implications:

- answer quality is useful for relative comparison inside the same pipeline
- groundedness and source compliance are heuristic checks, not human judgment
- latency is end-to-end wall-clock latency, not isolated model inference latency

Do not claim:

- human-level semantic evaluation
- exact orchestration-layer micro-overhead
- production SLA readiness from current latency numbers alone

## 4. Baseline Discipline

The strongest public-facing comparisons in this repo are:

- fixed-model rows on the Qwen3-AWQ ladder
- fixed-path rows such as `fixed retrieval` and `fixed general`
- `adaptive path-only`
- `joint adaptive path+model replay`

If additional baselines are discussed elsewhere, they should be marked as:

- representative
- planned
- or internal comparison modes

unless the repo contains a clear runnable artifact for them.

## 5. Controlled Replay Limitation

Joint `path + model-tier` evaluation is executed through controlled replay because the target setup assumes a single GPU.

Interpretation rule:

- the policy may jointly decide `selected_route + selected_model_class`
- execution is still replay-based, not live multi-model concurrent serving

## 6. Dataset Interpretation

The benchmark packs are designed for orchestration evaluation:

- route suitability
- grounded answer behavior
- safe refusal behavior
- tenant isolation probes
- cross-domain robustness

They are not a universal enterprise QA benchmark over all task families.

## 7. Current Hidden Risk Still Worth Checking

Even after validation passes, the final benchmark may still drift if:

- route prompts accidentally trigger tool inspectors instead of retrieval
- backend identity or model exposure differs from what the benchmark policy expects
- corpora change without regenerating the source pack

For that reason, the safe sendable claim is:

> benchmark construction is validated; benchmark execution evidence is still an active step.
