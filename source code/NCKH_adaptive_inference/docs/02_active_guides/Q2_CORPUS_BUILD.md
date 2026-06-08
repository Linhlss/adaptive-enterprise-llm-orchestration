# Q2 Corpus Build

Target corpus profile for each Q2 tenant:

- about `10` prose or unstructured documents relevant to the domain (`.md`, `.txt`, `.pdf`, `.docx`, ...)
- about `3` structured files (`.csv`, `.xlsx`, `.xls`)
- existing isolation fixtures preserved for tenant-isolation benchmarking

Resources and scripts:

- public-source blueprint: `systems_evaluation/q2_corpus_blueprint.py`
- builder: `systems_evaluation/build_q2_corpus.py`
- quick audit: `systems_evaluation/audit_q2_corpus.py`

Commands:

```bash
make build-q2-corpus
make audit-q2-corpus
```

If you need to redownload or overwrite generated files:

```bash
make build-q2-corpus-force
```

## Operational Notes

- The builder downloads HTML pages locally and stores them as `.md` so ingestion is more stable and reproducible.
- URLs that point directly to `pdf/docx/xlsx/csv` files are stored in their original binary format.
- The `3` structured files per tenant are currently scaffolded with domain-appropriate schemas for the tool-route benchmark. If exact institutional data becomes available, these files can be replaced while keeping the same filenames.
- The source inventory is saved at `data/tenants/<tenant_id>/source_manifest.json`.
- URLs are not written to `links.txt` by default in order to avoid duplicated ingestion from both live web links and local files.
