# Data pipeline

Collection, normalization, deduplication, and geographic enrichment. Preserve data provenance and collection logs; do not commit real raw data exports.

Stack: Python, HTTPX, and BeautifulSoup; Playwright when JavaScript rendering is required. Weekly runs use EventBridge Scheduler and ECS Tasks. See the [technology stack](../docs/technology-stack.md).
