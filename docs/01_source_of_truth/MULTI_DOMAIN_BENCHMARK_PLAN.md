# Multi-Domain Benchmark Plan

This document records the active plan for the current paper direction.

## 1. One-Line Thesis

Build an adaptive enterprise LLM orchestration framework that can serve multiple document-centric domains while making controlled decisions about both execution path and model tier. The main benchmark should run on `vLLM` with the official `Qwen3-AWQ` ladder (`14B / 8B / 4B`), while `Ollama` remains a development and smoke backend only. Under a single-GPU constraint, joint `path + model-tier` evaluation is reported through controlled replay rather than as live concurrent multi-model serving.

## 2. Aim

High-level aim:

- build a benchmarkable systems prototype
- avoid framing the project as a pure algorithm paper
- avoid framing the project as a full production gateway platform

Concrete research goals:

1. show that adaptive orchestration can generalize across **three domains**
2. show that model choice materially affects quality, latency, and efficiency
3. show that joint adaptation is more informative than fixed-path or fixed-model serving for document-centric enterprise workloads

## 3. Scope

### In scope

- document-grounded enterprise assistant workloads
- multi-tenant corpus separation
- routing across `retrieval`, `tool`, `general`, and `out_of_scope`
- fixed versus adaptive comparisons
- three document-centric domains
- three model tiers within one family
- system-level metrics

### Out of scope

- realtime transactional agent platforms
- a full production operating layer for enterprise AI
- multimodal enterprise operating systems
- large-scale fleet optimization across many model providers
- claims of superiority over all commercial orchestration gateways

## 4. Recommended Domain Set

Domain 1:

- academic and administrative support

Domain 2:

- HR and internal policy support

Domain 3:

- operations and compliance support

Why this set is appropriate:

- all three are document-centric
- all three exercise retrieval, file/table inspection, and safe fallback
- they can be benchmarked under one runtime without forcing the project outside its intended scope

## 5. Model Set And Backend Policy

Target model ladder:

- `Qwen3-14B-AWQ` -> `strong-quality`
- `Qwen3-8B-AWQ` -> `balanced`
- `Qwen3-4B-AWQ` -> `light-latency`

Why this ladder is preferred:

- same family, lower provider confounding
- clear quality/latency/compute tiers
- consistent AWQ quantization for a single-GPU benchmark

Backend policy:

- `Ollama` for development, smoke, and early validation
- `vLLM` for official benchmark runs and paper-facing tables

If adapter-based personalization cannot be benchmarked convincingly, it should remain a supporting mechanism rather than a main contribution claim.

## 6. Evaluation Matrix

Each domain should ideally include:

- fixed `Qwen3-14B-AWQ`
- fixed `Qwen3-8B-AWQ`
- fixed `Qwen3-4B-AWQ`
- fixed retrieval
- fixed general
- adaptive path-only
- joint adaptive `path + model-tier` replay

Optional rows if time and compute allow:

- representative tool-centric workflow
- representative adaptive retrieval-only mode

## 7. Metrics

The main evidence should revolve around:

- answer quality
- route suitability
- latency
- runtime overhead proxy
- retrieval grounding behavior
- refusal correctness and isolation behavior

## 8. What The Paper Should Claim

Safe claims:

- the adaptive orchestration framework can operate across multiple document-centric domains
- path choice and model choice both affect system trade-offs
- the joint design is practically meaningful for enterprise-serving research
- the policy may jointly decide `selected_route + selected_model_class`, while model-tier execution is reported through controlled replay on the same backend and hardware

Unsafe claims:

- the best router in the literature
- a universal enterprise gateway
- stronger than every existing routing system across all dimensions

## 9. Repo Change Status

Already completed in code/config:

1. `Ollama` development path plus `vLLM` benchmark path
2. Qwen3-AWQ benchmark model matrix
3. more domain-portable router features
4. broader prompt wording beyond one academic-only scope
5. tenant and trace metadata with `domain_id` / `domain_name`
6. benchmark prepare/validate scripts
7. model-sensitivity pipeline
8. stability pipeline
9. domain-aware isolation pipeline
10. multi-domain tenant initialization
11. controlled replay pipeline for joint adaptive `path + model-tier`

Still required at the benchmark/evidence level:

1. lock the three final domains and corpora
2. maintain two content-bearing tenants per domain
3. maintain forty-eight balanced cases per domain in the main pack
4. maintain smaller controlled subsets for model sensitivity and stability
5. maintain a domain-aware isolation pack
6. run the main benchmark on `vLLM`
7. keep the paper wording aligned with the new scope

## 10. Final Positioning Sentence

If a single positioning sentence is needed for a supervisor, proposal note, or opening paragraph:

> The project is being repositioned as an adaptive orchestration framework for enterprise LLM serving that scales across multiple document-centric domains and a controlled Qwen3-AWQ model ladder, with `Ollama` used for development and smoke validation and `vLLM` used for the main benchmark. The policy may jointly decide path and model tier, while the model-tier benchmark itself is executed through controlled replay on the same backend and hardware rather than being overclaimed as live multi-model serving.
