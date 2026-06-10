# Benchmark Content Validation

Structural validation alone is not enough for the paper-facing benchmark.

Semantic validation is needed to answer three questions:

- does the ground-truth file actually exist in the tenant corpus?
- do the expected keywords actually appear in the intended ground-truth file?
- does the current tenant corpus accidentally contain forbidden or leakage markers?

Core validator:

- the benchmark semantic validation utility

Commands:

```bash
make validate-benchmark-content
```

## What The Script Checks

- `retrieval`: `relevant_docs` exist, are vectorizable, and the `expected_keywords` appear in the intended ground-truth file
- `tool`: `relevant_docs` exist, are structured files such as `csv/xlsx`, and the `expected_keywords` appear in the intended structured file
- `out_of_scope`: if `corpus_absent_keywords` are provided, the script verifies that they do **not** appear in the current tenant corpus
- `forbidden_keywords`: verifies that blocked markers do not appear in the current tenant corpus; for isolation cases with `target_tenant_id`, the script also checks that the marker really exists in the target tenant corpus

## Limitations

- `out_of_scope` checking is strongest when the case includes explicit `corpus_absent_keywords`
- the script scans local corpus files and snapshots only; it does not treat live web URLs as the source of truth
