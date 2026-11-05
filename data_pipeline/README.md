# Data pipeline

Collection, normalization, deduplication, and geographic enrichment. Preserve data provenance and collection logs; do not commit real raw data exports.

Stack: Python, HTTPX, and BeautifulSoup; Playwright when JavaScript rendering is required. Weekly runs use EventBridge Scheduler and ECS Tasks. See the [technology stack](../docs/technology-stack.md).

For A07 weekly neighborhood asking-price aggregates, see the
[index contract, sparse-data policy, generator, and backend database view](docs/neighborhood-price-index.md).
For versioned, leakage-aware, privacy-safe ML snapshots and the accompanying quality report, see
[A06 dataset export](docs/dataset-export.md). Generate snapshots with `python -m data_pipeline.export_dataset`;
outputs default to the Git-ignored `data/processed/` directory.

## Backfill List.am photos

From a host that can reach PostgreSQL and List.am, install the pipeline dependencies
and `psycopg[binary]` in a virtual environment. Set `PGHOST`, `PGPORT`, `PGDATABASE`,
`PGUSER`, and use a PostgreSQL password file or an interactive shell prompt to supply
`PGPASSWORD`. Start with a read-only check on a known listing:

```bash
python -m data_pipeline.backfill_photos --external-id 21373392
```

If JavaScript rendering is needed, install Playwright and its Chromium browser, then
add `--browser`. The command stops if the source blocks the requests. When the check
finds the expected photos, add `--apply` to save their URLs. For a batch use
`--limit 100` and pass the reported `--after-id` to the next batch. Schedule the
backfill outside an active import. After deployment, run the usual listing publication
to copy the photos into the API projection.
