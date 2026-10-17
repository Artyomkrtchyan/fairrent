# Data pipeline

Collection, normalization, deduplication, and geographic enrichment. Preserve data provenance and collection logs; do not commit real raw data exports.

Alisa owns the pipeline. Mane verifies untrusted-input and URL-fetching boundaries, sensitive-data handling and dataset artifact integrity with the data owner (E01, E03–E04). Testing targets project-owned environments rather than external listing websites.

Stack: Python, HTTPX, and BeautifulSoup; Playwright when JavaScript rendering is required. Weekly runs use EventBridge Scheduler and ECS Tasks. See the [technology stack](../docs/technology-stack.md).
