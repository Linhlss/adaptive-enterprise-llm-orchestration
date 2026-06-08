# Relevance Brief

## Adaptive Orchestration for Multi-Domain, Multi-Tenant Enterprise LLM Serving

## 1. Purpose

This brief is intended for an academic reader whose work focuses on AI engineering, responsible AI, software architecture, and foundation-model-based agents.

Its purpose is not to present a finished paper. Its purpose is to present a concrete research direction that may complement that line of work by offering a runnable case study of enterprise LLM orchestration under multi-tenant and multi-domain constraints.

## 2. Working Framing

The project studies how a shared enterprise LLM runtime should decide when a request should be handled through:

- retrieval
- external tools
- direct generation
- explicit safe refusal

under multi-domain and multi-tenant constraints.

The central idea is that recent orchestration and agent frameworks provide strong workflow primitives, but enterprise deployments still need a reproducible **serving-policy layer** that decides which execution path should be used, what evidence should be recorded, and how tenant boundaries should be preserved and evaluated.

## 3. What the Project Is

This project is best understood as:

- an AI engineering / systems-and-application study
- a runnable orchestration prototype
- a benchmarked evaluation workspace under active development

The current implementation already includes:

- a multi-tenant serving runtime
- route selection across `retrieval`, `tool`, `general`, and `out_of_scope`
- route-level telemetry
- tenant-aware retrieval and file/tool handling
- Q2 multi-domain benchmark-pack construction
- strict benchmark validation
- controlled replay preparation for joint `path + model-tier` evaluation

## 4. What the Project Is Not

The project does **not** currently claim:

- a new foundation model
- a new retrieval algorithm
- a new learned router
- a low-level serving engine contribution
- online concurrent multi-model serving as the main evidence

The intended contribution is narrower and more practical:

> a runnable enterprise orchestration prototype with a disciplined systems evaluation design

## 5. Why It May Be Relevant

The project may be relevant to current AI engineering and agent engineering research for three main reasons.

### 5.1. It treats orchestration as a system-level research object

Rather than evaluating only answer outputs, it treats runtime decisions themselves as part of the artifact:

- selected route
- route rationale
- selected model tier
- evidence sources
- tool usage
- refusal behavior
- latency and trace metadata

### 5.2. It focuses on serving policy, not only workflow primitives

Recent work on foundation-model-based systems and agents has already advanced reference architectures, architectural patterns, runtime observability, and evaluation process models. This project focuses on a narrower but practical question that still seems comparatively under-operationalised in shared enterprise runtime settings:

> how should a shared enterprise runtime decide which path should serve a request, and how should that decision be evaluated?

### 5.3. It includes tenant-boundary probes as controlled safety scenarios

The benchmark design includes isolation-oriented cases intended to test whether the runtime crosses tenant boundaries through retrieval, references, or tool pathways.

This is not presented as a formal security proof, but as controlled systems evidence.

## 6. Current Status

The repository should currently be described conservatively.

What is already solid:

- the runtime implementation
- the Q2 benchmark-construction pipeline
- strict dataset and semantic validation
- controlled replay preparation for joint policy evaluation

What is still in progress:

- full paper-facing benchmark execution on the intended `vLLM` backend
- final main-table evidence for all benchmark rows
- final paper wording and comparison discipline

Because of that, the fairest summary is:

> the project is already runnable and methodologically structured, but its final benchmark evidence is still being completed

## 7. Main Question for Feedback

The specific feedback I would most value is:

**Does this distinction between general agent/orchestration primitives and an enterprise serving-policy layer seem like a legitimate AI engineering research framing, especially as a concrete case study for architecture, observability, and responsible runtime behavior?**

## 8. Repository Note

The associated repository is being curated to match this exact framing:

- active scope only
- explicit benchmark limitations
- no claim of benchmark-complete evidence yet
- no legacy benchmark artifacts surfaced as current evidence
