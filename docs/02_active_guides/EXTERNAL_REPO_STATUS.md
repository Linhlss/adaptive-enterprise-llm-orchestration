# External Repo Status

This note is for external readers opening the repository for the first time.

## One-Line Summary

The repo already contains a runnable enterprise LLM orchestration prototype and a validated multi-domain benchmark-construction pipeline, while the final paper-facing benchmark runs on `vLLM` remain an active execution step.

## What Is Already Solid

- runtime code for multi-tenant path orchestration
- route telemetry and benchmark execution scripts
- source query-pack construction from real tenant corpora
- balanced dataset construction for main/model/stability/isolation packs
- strict semantic validation of the benchmark packs
- controlled replay preparation for joint `path + model-tier` evaluation

## What Is Not Yet Claimed As Finished

- clean final benchmark evidence for every paper-facing row
- stable `vLLM` deployment on every machine by default
- benchmark-complete cross-domain results ready for publication without further execution

## Safe Interpretation

Read this repository as:

- a serious research implementation
- a benchmark-ready construction pipeline
- an in-progress paper artifact with explicit claim discipline

Do not read it as:

- a polished product repository
- a production-serving platform
- a finished journal submission package

## Why The Repo Was Cleaned

Legacy artifacts for earlier `final24`, `final48`, `paper_real`, and `phase7` flows were removed from the public surface because they no longer represent the active proposal direction.

## If You Want To Reproduce The Current Scope

Use:

1. `make bootstrap`
2. `make build-benchmark-corpus`
3. `make prepare-benchmark-pack`
4. `make validate-benchmark-pack`
5. `make validate-benchmark-content`
6. `make check-benchmark-readiness`

Then move to the benchmark execution targets only after the target backend is verified.
