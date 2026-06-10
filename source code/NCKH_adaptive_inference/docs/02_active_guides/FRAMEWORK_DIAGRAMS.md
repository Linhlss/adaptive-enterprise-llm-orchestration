# Framework Diagrams

This file replaces the older framework figures that still reflected the earlier
`adaptive multi-path` framing. The diagrams below are aligned with the current
proposal-facing direction:

- multi-domain, multi-tenant enterprise LLM serving
- explicit `serving-policy layer`
- adaptive choice of `route + model_class`
- `Ollama` for development and smoke only
- `vLLM` for paper-facing benchmark runs
- controlled replay for joint `path + model-tier` evaluation

PlantUML export-oriented versions for the two densest diagrams are available at:

- [plantuml/unified_runtime_architecture.puml](plantuml/unified_runtime_architecture.puml)
- [plantuml/benchmark_controlled_replay_pipeline.puml](plantuml/benchmark_controlled_replay_pipeline.puml)

## 1. Adaptive Orchestration Runtime Workflow

```mermaid
flowchart TD
    A["Enterprise query<br/>tenant_id + domain_id + session"] --> B["Normalize request<br/>attach tenant and domain context"]
    B --> C["Serving-policy layer<br/>score route need, grounding need,<br/>tool suitability, safety, and cost envelope"]
    C --> D["Policy output<br/>selected_route + selected_model_class"]

    D --> E{"Selected route"}
    D --> M["Selected model class<br/>strong-quality | balanced | light-latency"]

    E --> R["Retrieval path<br/>tenant-scoped evidence retrieval<br/>draft -> verify -> rewrite"]
    E --> T["Tool path<br/>PDF / spreadsheet / link inspection<br/>structured synthesis"]
    E --> G["General path<br/>direct generation with guardrails"]
    E --> F["Safe refusal path<br/>out-of-scope / unsupported / unsafe"]

    M --> X["Active execution backend<br/>Ollama for dev/smoke<br/>vLLM for benchmark runs"]
    R --> X
    T --> X
    G --> X
    F --> O["Bounded refusal response"]

    X --> Y["Answer assembly<br/>evidence metadata + route trace + latency"]
    O --> Y
    Y --> Z["Final answer<br/>tenant-scoped state update<br/>runtime telemetry"]

    classDef policy fill:#dbeafe,stroke:#2563eb,stroke-width:1.5px,color:#111827;
    classDef route fill:#dcfce7,stroke:#16a34a,stroke-width:1.2px,color:#111827;
    classDef model fill:#fef3c7,stroke:#d97706,stroke-width:1.2px,color:#111827;
    classDef safe fill:#fee2e2,stroke:#dc2626,stroke-width:1.2px,color:#111827;

    class C,D policy;
    class R,T,G route;
    class M,X model;
    class F,O safe;
```

## 2. Unified Runtime Architecture

```mermaid
flowchart TB
    U["Client / benchmark request"] --> API["API serving layer"]
    API --> CTRL["Workflow controller"]
    CTRL --> TENANT["Tenant + domain context resolver"]
    TENANT --> POLICY["Serving-policy layer<br/>route scoring + model-class decision<br/>safety and scope enforcement"]

    subgraph RUNTIME["Unified Enterprise Serving Runtime"]
        POLICY --> EXEC{"Execution route"}
        EXEC --> RET["Retrieval execution<br/>tenant-scoped corpus access"]
        EXEC --> TOOL["Tool execution<br/>file/table/link inspection"]
        EXEC --> GEN["General execution<br/>guarded direct generation"]
        EXEC --> REF["Safe refusal"]

        MODEL["Model tier registry<br/>strong-quality / balanced / light-latency"] --> BACKEND["Active model backend"]
        RET --> BACKEND
        TOOL --> BACKEND
        GEN --> BACKEND

        STATE["Tenant-scoped runtime state<br/>memory, logs, storage, retrieval index"] --> POLICY
        STATE --> RET
        STATE --> TOOL
        STATE --> GEN

        PERS["Optional lightweight personalization<br/>supporting mechanism only"] -. adapter available .-> BACKEND

        BACKEND --> TRACE["Response assembly + route trace"]
        REF --> TRACE
        TRACE --> OBS["Telemetry + benchmark artifact emission"]
    end

    subgraph EVAL["Systems Evaluation Layer"]
        OBS --> PACK["Benchmark packs<br/>main / model / stability / isolation"]
        OBS --> REPLAY["Controlled replay<br/>policy pass -> per-tier replay -> merged artifact"]
        PACK --> TABLES["Tables and benchmark summaries"]
        REPLAY --> TABLES
    end

    subgraph BACKENDS["Backend Policy"]
        DEV["Ollama<br/>local smoke and development"]
        VLLM["vLLM<br/>official paper-facing benchmark backend"]
    end

    DEV --> BACKEND
    VLLM --> BACKEND

    classDef primary fill:#dbeafe,stroke:#2563eb,stroke-width:1.5px,color:#111827;
    classDef support fill:#ede9fe,stroke:#7c3aed,stroke-width:1.2px,color:#111827;
    classDef eval fill:#dcfce7,stroke:#16a34a,stroke-width:1.2px,color:#111827;
    classDef backend fill:#fef3c7,stroke:#d97706,stroke-width:1.2px,color:#111827;

    class POLICY,TRACE,OBS primary;
    class STATE,PERS support;
    class PACK,REPLAY,TABLES eval;
    class MODEL,BACKEND,DEV,VLLM backend;
```

## 3. Benchmark And Controlled Replay Pipeline

```mermaid
flowchart LR
    A["Benchmark corpora<br/>3 domains<br/>2 content-bearing tenants per domain"] --> B["Source query-pack construction"]
    B --> C["Balanced benchmark construction<br/>main / model / stability / isolation"]
    C --> D["Pack validation<br/>structure + semantics + readiness"]

    D --> E["Online policy pass<br/>route decision + selected_model_class + trace"]
    E --> F["Paper-facing benchmark rows<br/>fixed routes / adaptive path-only"]
    E --> G["Controlled replay branch<br/>replay same cases across model tiers"]

    G --> H["Per-tier replay artifacts<br/>14B / 8B / 4B under one backend policy"]
    H --> I["Merged joint artifact<br/>path + model-tier evaluation"]

    F --> J["Main comparison tables"]
    I --> J
    J --> K["Claim-safe reporting<br/>no overclaim of live concurrent multi-model serving"]

    classDef data fill:#dbeafe,stroke:#2563eb,stroke-width:1.3px,color:#111827;
    classDef eval fill:#dcfce7,stroke:#16a34a,stroke-width:1.3px,color:#111827;
    classDef caution fill:#fee2e2,stroke:#dc2626,stroke-width:1.3px,color:#111827;

    class A,B,C,D data;
    class E,F,G,H,I,J eval;
    class K caution;
```

## 4. Tenant Runtime And Supporting Personalization

```mermaid
flowchart LR
    Q["Tenant request<br/>tenant_id + domain_id + session"] --> MGR["Tenant runtime manager<br/>scope resolution + isolation + policy attachment"]
    MGR --> CORE["Shared orchestration runtime<br/>one serving backbone for many tenants"]

    CORE --> MEM["Tenant-scoped state<br/>memory, logs, retrieval index, storage"]
    CORE --> ISO["Isolation guardrails<br/>per-tenant storage and trace boundaries"]
    CORE --> RESP["Answer + tenant-scoped state update"]

    REG["Adapter registry<br/>optional per-tenant adapter availability"] -. optional .-> ADAPT["Lightweight personalization<br/>loaded on demand only when policy allows"]
    ADAPT -. supporting mechanism .-> CORE

    NOTE["Primary paper claim<br/>unified orchestration + tenant isolation + cross-domain evaluation<br/>not adapter novelty"] --- ADAPT

    classDef core fill:#dbeafe,stroke:#2563eb,stroke-width:1.4px,color:#111827;
    classDef support fill:#ede9fe,stroke:#7c3aed,stroke-width:1.2px,color:#111827;
    classDef state fill:#dcfce7,stroke:#16a34a,stroke-width:1.2px,color:#111827;
    classDef note fill:#fef3c7,stroke:#d97706,stroke-width:1.2px,color:#111827;

    class MGR,CORE core;
    class REG,ADAPT support;
    class MEM,ISO,RESP state;
    class NOTE note;
```

## 5. Proposal-Facing Roadmap

```mermaid
flowchart LR
    P1["Phase 1<br/>Scope and claim discipline<br/>lock multi-domain framing<br/>remove legacy overclaim"] --> P2["Phase 2<br/>Corpus and benchmark construction<br/>3 domains<br/>balanced benchmark packs"]
    P2 --> P3["Phase 3<br/>Serving runtime alignment<br/>policy layer<br/>route + model_class decision<br/>telemetry and safety"]
    P3 --> P4["Phase 4<br/>Paper-facing evaluation<br/>vLLM runs<br/>controlled replay<br/>main tables"]
    P4 --> OUT["Final artifact<br/>adaptive orchestration for multi-domain,<br/>multi-tenant enterprise LLM serving"]

    B1["Representative baselines<br/>fixed retrieval<br/>fixed general<br/>path-only adaptive<br/>joint replay row"] -. compared in Phase 4 .-> P4
    B2["Backend split<br/>Ollama for development<br/>vLLM for official benchmark"] -. operational policy .-> P3
    B3["Supporting mechanism only<br/>personalization may remain optional<br/>not the core claim"] -. scope guard .-> P3

    classDef phase fill:#dbeafe,stroke:#2563eb,stroke-width:1.4px,color:#111827;
    classDef outcome fill:#dcfce7,stroke:#16a34a,stroke-width:1.4px,color:#111827;
    classDef note fill:#fef3c7,stroke:#d97706,stroke-width:1.2px,color:#111827;

    class P1,P2,P3,P4 phase;
    class OUT outcome;
    class B1,B2,B3 note;
```
