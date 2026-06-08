# Research Focus

This file is the main reference for the project’s current research positioning.

## North-Star Direction

The project is being aligned toward:

> adaptive orchestration for multi-domain, multi-tenant enterprise LLM serving, combining path routing and controlled model-tier selection on an official Qwen3-AWQ ladder

In short:

- it remains a **systems-and-application study**
- it is no longer confined to a single academic domain
- it no longer stops at path routing alone

## Core Research Aim

The active goal is to build a prototype that can:

1. serve at least **three document-centric enterprise domains**
2. support adaptive path selection across `retrieval`, `tool`, `general`, and `out_of_scope`
3. support controlled model-tier selection across three fixed tiers
4. evaluate the trade-offs among quality, latency, efficiency, overhead, and tenant/domain safety

## Final Paper-Facing Artifact

> A unified adaptive orchestration framework for multi-tenant enterprise LLM serving that combines path routing, controlled model selection, tenant-aware runtime isolation, and cross-domain systems evaluation.

## Concrete Target Problem

The central research question should be understood as:

> How can we build and evaluate a unified adaptive orchestration framework for multi-tenant enterprise LLM systems in which the runtime decides both **which execution path to use** and **which model tier to use** across multiple internal document-centric domains while preserving practical quality, latency, and isolation trade-offs?

Within this repository, “which model to use” should be interpreted carefully:

- the policy jointly decides `selected_route + selected_model_class`
- the official model-tier benchmark is executed through **controlled replay**
- the project does **not** claim live concurrent multi-model serving as its main contribution

## Target Paper Positioning

The paper should be positioned as:

- a systems-and-application study on adaptive enterprise LLM serving
- a multi-domain orchestration framework paper
- a reproducible benchmarked prototype

The paper should **not** be positioned as:

- a new foundation model paper
- a new LoRA method paper
- a new retrieval algorithm paper
- a pure learned-router paper
- a generic production gateway claiming state-of-the-art on every enterprise task

## Main Contributions To Claim

If the project follows the current direction, the contribution package should be:

1. a **joint adaptive orchestration architecture**
   - path routing and model selection in one runtime
2. a **tenant-aware multi-domain serving design**
   - shared serving, tenant boundaries, domain-specific corpora, route traces
3. a **cross-domain systems evaluation protocol**
   - at least three domains with distinct workloads and corpora
4. a **controlled comparison package**
   - adaptive vs fixed modes and explicitly scoped representative baselines
5. a **controlled replay evaluation protocol**
   - joint `path + model-tier` evaluation on the same hardware/backend without overstating deployment capability

## Scope In

The core scope includes:

- multi-tenant enterprise LLM serving
- document-grounded assistant workloads
- routing across `retrieval`, `tool`, `general`, and `out_of_scope`
- controlled model-tier selection
- tenant-aware runtime state
- route trace and benchmark telemetry
- cross-domain benchmarking across roughly three domains
- system metrics such as:
  - answer quality
  - route suitability
  - latency
  - efficiency / overhead
  - runtime footprint
  - isolation / safe refusal

## Scope Out

The main scope excludes:

- proposing a new foundation model
- training a new learned router and claiming strong algorithmic novelty
- general-purpose benchmarking across every enterprise task family
- large-scale multimodal routing
- a complete production platform
- full external reproduction of every commercial baseline
- state-of-the-art claims across the 2026 router/gateway landscape

## Domain Plan

The project should not use the word “enterprise” in a vague way. It should commit to three clearly document-centric benchmark domains:

1. `academic and administrative support`
   - regulations, forms, schedules, announcements, advising documents
2. `HR and internal policy support`
   - leave policy, onboarding, internal procedures, HR policy documents
3. `operations and compliance support`
   - SOPs, checklists, procurement flow, quality/compliance documents

Important note:

- the three domains must be genuinely different in both corpus and workload
- three tenants with nearly identical data do **not** justify a multi-domain claim

## Model And Backend Plan

The new direction may claim **controlled model-tier selection**, but it should not be overstated as universal multi-model optimization.

The intended model ladder is:

- `Qwen3-14B-AWQ`: `strong-quality`
- `Qwen3-8B-AWQ`: `balanced`
- `Qwen3-4B-AWQ`: `light-latency`

Why this ladder is appropriate:

- one family and one official quantization format
- clear quality/latency/compute differences
- realistic for a `RTX 4090 24GB` budget

Backend role split:

- `Ollama`: local development, smoke, early validation
- `vLLM`: official benchmark backend and paper-facing tables

The paper should interpret model flexibility as:

- the runtime can choose a model class under policy control
- the benchmark measures how model choice affects quality and latency
- the core benchmark remains inside one model family
- the joint row is executed as `route-only policy pass -> per-tier replay -> merged artifact`

The paper should not imply:

- a solved large-scale multi-provider orchestration problem
- a verified advantage over all existing AI gateway systems

## Current Implementation Status Versus The New Aim

The repository already contains:

- an adaptive multi-path runtime
- tenant-aware retrieval and isolation mechanisms
- file/table/link tool paths
- a benchmark runner and route trace pipeline

It still needs to be interpreted carefully for the new aim:

- the benchmark story depends on the Q2 multi-domain packs
- some comparison rows remain representative rather than external canonical reproductions
- the router and prompts are more domain-portable than before, but the benchmark evidence still depends on the actual three-domain corpora

The model-tier problem has been handled pragmatically:

- it does not rely on one live `vLLM` endpoint serving `14B/8B/4B` concurrently
- the joint benchmark is scripted through controlled replay
- the claim should remain at the level of **joint policy decision**, not live multi-model serving

## Evaluation Objectives

The new direction should be evaluated along four main axes:

1. **Cross-domain usefulness**
   - does adaptive orchestration remain useful across distinct domains?
2. **Quality-latency trade-off**
   - does the adaptive design achieve a more practical balance than fixed strategies?
3. **Model sensitivity**
   - how do route policy and system behavior change across model tiers?
4. **Isolation and safety**
   - are tenant boundaries, unsupported-request handling, and safe fallback stable?

## Comparison Structure

The main comparison package should prioritize:

- strongest fixed model
- lightest fixed model
- fixed retrieval
- fixed general
- fixed tool where the domain warrants it
- adaptive path-only
- joint adaptive `path + model-tier` replay

Representative comparison modes may still be included, such as:

- adaptive retrieval-only
- tool-centric workflow

but they must be labeled clearly as **representative** rather than external canonical reproductions.

## Claim Discipline

Safe claim level:

- we propose an adaptive orchestration framework for enterprise LLM serving
- the framework combines path routing, controlled model flexibility, and tenant-aware runtime behavior
- benchmark results suggest usefulness across multiple document-centric domains

Unsafe claim level:

- the newest or best router in the literature
- the most general framework for every enterprise domain
- better than all current systems in 2026
- comprehensive production readiness

## Execution Roadmap

The roadmap can be understood in three phases:

### Phase A: Repositioning And Cleanup

- finalize claim, aim, and scope
- distinguish current implementation from target direction
- remove overclaiming language

### Phase B: Backend And Multi-Domain Upgrade

- stabilize the backend interface
- keep `Ollama` for local smoke
- move the official benchmark to `vLLM`
- finalize the `Qwen3-14B-AWQ / 8B-AWQ / 4B-AWQ` ladder
- lock controlled replay as the official joint-evaluation protocol
- prepare the three domain packs
- make prompts and datasets domain-portable

### Phase C: Q2 Benchmark Completion

- benchmark the three fixed model tiers
- benchmark fixed and adaptive comparisons
- execute the `policy pass + per-tier replay + merged artifact` pipeline
- report quality, latency, efficiency, and safety by domain

## Practical Conclusion

The project should still be viewed as:

> an adaptive enterprise LLM systems project

But under the new direction, the paper should move from:

> an adaptive multi-path prototype for a narrow multi-tenant academic setting

to:

> an adaptive orchestration framework that scales across multiple document-centric domains and a controlled Qwen3-AWQ model ladder, evaluated as a systems artifact through `vLLM` and controlled replay
