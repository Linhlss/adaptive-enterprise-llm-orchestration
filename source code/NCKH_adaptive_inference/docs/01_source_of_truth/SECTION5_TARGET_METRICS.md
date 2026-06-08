# Section 5 Target Metrics

This document defines the benchmark framework for the project’s current direction:

- multi-domain
- multi-tenant
- adaptive path selection plus controlled model-tier evaluation
- systems-and-application positioning
- Q2-oriented evidence quality

Its purpose is to:

- define a benchmark that is strong enough to support practical claims
- separate a **minimum defensible** benchmark from a **Q2-strong** benchmark
- avoid overclaiming from an undersized benchmark
- avoid inflating the benchmark without adding proportionate evidential value

## 1. General Principle

There is no single benchmark size that automatically makes the project “Q2.”

For the current direction, the evidence should establish four things:

1. the adaptive framework is not locked to one domain
2. path choice and model choice create meaningful trade-offs
3. tenant isolation and safe fallback matter in an enterprise context
4. the adaptive design is more useful than fixed execution modes on the same runtime

Because of that, the evidence priority should be:

1. cross-domain usefulness
2. quality-latency-efficiency trade-off
3. model sensitivity
4. tenant isolation and refusal correctness
5. runtime footprint scaling
6. stability and reproducibility

## 2. Benchmark Tiers

### Minimum Defensible

This is the minimum evidence level required to write the paper in the new direction without the evidence collapsing immediately under scrutiny.

### Q2-Strong Target

This is the target level if the goal is a stronger systems/applied Q2 submission.

If only the minimum level is achieved, the paper can still be written, but its claims must remain very disciplined.

## 3. Core Benchmark Matrix

| Component | Minimum Defensible | Q2-Strong Target | Notes |
| --- | --- | --- | --- |
| Number of domains | 3 | 3 | Going below 3 weakens the multi-domain claim |
| Content-bearing tenants per domain | 2 | 2 | Six tenants with real content |
| Shared corpus per domain | 4-6 documents | 6-10 documents | PDF/MD/DOCX/links |
| Tenant-private prose docs per tenant | 6-8 | 8-15 | Internal docs, policy, SOP, memo |
| Structured files per tenant | 2 | 3-4 | CSV/XLSX matters for tool routing |
| Core benchmark cases per domain | 36 | 48 | Balanced across the four routes |
| Cases per route per domain | 9 | 12 | `retrieval` / `tool` / `general` / `out_of_scope` |
| Model tiers | 2 | 3 | `Qwen3-14B-AWQ`, `Qwen3-8B-AWQ`, `Qwen3-4B-AWQ` |
| Core methods in the main table | 5 | 6-7 | See Section 6 |
| Stability repeats | 2 runs | 3 runs | On a controlled subset |

## 4. Domain And Corpus Requirements

To claim “multi-domain,” the three domains must genuinely differ in corpus and workload.

Recommended domain set:

1. academic and administrative support
2. HR and internal policy support
3. operations and compliance support

### Corpus minimum per domain

Each domain should have:

- one shared domain corpus
- two tenant-private corpora

### Corpus target per tenant

Each tenant should have at least:

- `8-15` prose documents with real content
- `3-4` structured files
- `0-5` links if needed

If the corpus is too small, both `retrieval` and `tool` routes become weak, which makes the benchmark less convincing.

## 5. Core Evaluation Packs

The benchmark should be organized into six packs.

### Pack A. Cross-Domain Core Benchmark

Purpose:

- this is the main practical evidence for the project
- it shows that the system works across three domains rather than one

Size:

- minimum defensible: `36 cases / domain`
- Q2-strong target: `48 cases / domain`

Total cases:

- minimum: `108`
- target: `144`

Per-domain route distribution:

- retrieval: `9` or `12`
- tool: `9` or `12`
- general: `9` or `12`
- out_of_scope: `9` or `12`

Avoid dropping below `8 cases / route / domain`.

### Pack B. Stability Subset

Purpose:

- lock in the stability of the adaptive method and the main baselines
- avoid reviewer criticism that the result depends on a lucky run

Recommended size:

- `24 cases / domain`
- balanced `6 / route / domain`

Total subset:

- `72 cases`

Repeats:

- minimum: `2 runs`
- target: `3 runs`

### Pack C. Model Sensitivity Benchmark

Purpose:

- show that model choice affects quality, latency, and efficiency
- this is required if the paper claims controlled model-tier selection

Recommended size:

- `24 cases / domain`
- total `72 cases`

Model tiers:

- minimum: `2`
  - `Qwen3-14B-AWQ`
  - `Qwen3-4B-AWQ`
- target: `3`
  - `Qwen3-14B-AWQ`
  - `Qwen3-8B-AWQ`
  - `Qwen3-4B-AWQ`

Backend policy:

- `Ollama` for development and smoke only
- `vLLM` for the benchmark evidence used in main paper tables

If this pack is missing, the paper should not make a strong model-flexibility claim.

### Pack D. Joint Adaptive Replay Benchmark

Purpose:

- evaluate the system when path adaptation and model adaptation are combined
- keep the claim at the level of **joint policy decision**
- execute the model-tier benchmark through controlled replay on the same hardware/backend

Size:

- same cases as Pack A
- minimum `108`
- target `144`

Recommended execution flow:

1. route-only policy pass with `model_class=adaptive`
2. split dataset by `selected_model_class`
3. execute replay passes and merge the artifacts

### Pack E. Isolation And Safety Benchmark

Purpose:

- show that tenant boundaries and safe refusal matter in practice

Suggested size:

- `16 probes / domain`

Suggested structure:

- retrieval leakage probes in both directions
- tool/reference leakage probes in both directions

Total:

- `48 probes` across three domains

### Pack F. Runtime Scaling Benchmark

Purpose:

- show runtime footprint scaling
- not to support broad semantic-quality claims

Suggested checkpoints:

- `1`
- `3`
- `6`
- `12`

Repeats:

- minimum: `2 snapshots / checkpoint`
- target: `3 snapshots / checkpoint`

Interpretation:

- shared-runtime behavior
- memory/load-time footprint scaling

Not:

- a substitute for the quality benchmark

## 6. Required Methods In The Main Table

### Minimum defensible rows

1. `Fixed Qwen3-14B-AWQ`
2. `Fixed Qwen3-4B-AWQ`
3. `Fixed retrieval`
4. `Fixed general`
5. `Adaptive path-only`

### Q2-strong target rows

1. `Fixed Qwen3-14B-AWQ`
2. `Fixed Qwen3-8B-AWQ`
3. `Fixed Qwen3-4B-AWQ`
4. `Fixed retrieval`
5. `Fixed general`
6. `Adaptive path-only`
7. `Joint adaptive path+model replay`

Optional supporting rows:

- representative adaptive retrieval-only
- representative tool-centric workflow

Important note:

- if `joint adaptive path+model replay` is not actually implemented and executed, it must not appear in the final table
- if it appears, it must be explicitly labeled as **controlled replay under a single-GPU constraint**

## 7. Required Metrics

### Main table

Required:

- answer quality
- route suitability
- average latency
- P95 latency
- overhead proxy or route-only latency

Recommended:

- groundedness for retrieval/tool-heavy packs
- refusal correctness for safety-oriented rows

Backend note:

- main tables should be read from `vLLM` benchmark runs
- `Ollama` smoke runs are development evidence only

### Stability table

Report:

- mean
- standard deviation

for:

- quality
- route suitability
- average latency

### Model sensitivity table

Report:

- quality
- average latency
- P95 latency
- token or cost proxy if available

### Isolation table

Report:

- leak success count
- leak blocked count
- safe refusal correctness

### Scaling table

Report:

- load time
- RSS delta
- runtime count

## 8. Claim-Ready Evidence Thresholds

These are not universal truths. They are practical thresholds for deciding when the evidence is strong enough to support a claim.

### 8.1 Cross-domain claim

To claim that the framework works across multiple domains:

- adaptive should win or remain competitive across **all three domains**
- there should be no domain-level collapse

Domain collapse here means:

- major quality loss
- or major latency regression
- or obviously weaker route suitability than a reasonable fixed baseline

### 8.2 Quality-preserving claim

To claim that adaptive orchestration preserves quality:

- adaptive quality should remain within roughly `3-5 percentage points` of the strongest fixed-model row

If the gap is consistently larger, the paper should avoid saying it “maintains quality.”

### 8.3 Practical efficiency claim

To claim that adaptive orchestration is more practical than fixed strategies:

- adaptive should reduce average latency by roughly `15-25%` relative to a stronger fixed baseline or a heavy fixed retrieval mode

### 8.4 Isolation claim

To claim meaningful tenant-boundary protection:

- the isolation pack should show clean blocking behavior on explicit leakage probes
- the paper should still avoid equating controlled probes with a full security proof

## 9. Final Interpretation Rule

Section 5 should remain aligned with this principle:

> the benchmark is designed to show that adaptive orchestration is practically useful across multiple enterprise-like domains under realistic trade-offs, not to prove universal superiority or full production readiness.
