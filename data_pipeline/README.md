# Data pipeline

Collection, normalization, deduplication, and geographic enrichment. Preserve data provenance and collection logs; do not commit real raw data exports.

Stack: Python, HTTPX, and BeautifulSoup; Playwright when JavaScript rendering is required. Weekly runs use EventBridge Scheduler and ECS Tasks. See the [technology stack](../docs/technology-stack.md).

For versioned, leakage-aware, privacy-safe ML snapshots and the accompanying quality report, see
[A06 dataset export](docs/dataset-export.md). Generate snapshots with `python -m data_pipeline.export_dataset`;
outputs default to the Git-ignored `data/processed/` directory.
