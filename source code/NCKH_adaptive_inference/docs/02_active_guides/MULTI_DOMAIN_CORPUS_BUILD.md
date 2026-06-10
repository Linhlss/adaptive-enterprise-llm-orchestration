# Multi-Domain Corpus Build

Target corpus profile for each active tenant:

- about `10` prose or unstructured documents relevant to the domain (`.md`, `.txt`, `.pdf`, `.docx`, ...)
- about `3` structured files (`.csv`, `.xlsx`, `.xls`)
- existing isolation fixtures preserved for tenant-isolation benchmarking

Key implementation pieces:

- the public-source corpus blueprint
- the corpus builder
- the corpus audit utility

Commands:

```bash
make build-benchmark-corpus
make audit-benchmark-corpus
```

If you need to redownload or overwrite generated files:

```bash
make build-benchmark-corpus-force
```

## Operational Notes

- The builder downloads HTML pages locally and stores them as `.md` so ingestion is more stable and reproducible.
- URLs that point directly to `pdf/docx/xlsx/csv` files are stored in their original binary format.
- The `3` structured files per tenant are currently provided as starter benchmark fixtures with domain-appropriate schemas for the tool-route benchmark. If exact institutional data becomes available, these files can be replaced while keeping the same filenames.
- The source inventory is saved at `data/tenants/<tenant_id>/source_manifest.json`.
- URLs are not written to `links.txt` by default in order to avoid duplicated ingestion from both live web links and local files.
