"""Pipeline configuration. Everything comes from the environment; no secrets live in code."""
import os
DEFAULT_SOURCE_NAME = "list.am"

DEFAULT_SOURCE_URL = os.environ.get("LISTINGS_SOURCE_URL", "https://www.list.am/category/56")
STALENESS_RUNS = int(os.environ.get("STALENESS_RUNS", "2"))
MIN_SEEN_RATIO = float(os.environ.get("MIN_SEEN_RATIO", "0.5"))


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Export it, e.g. "
            "DATABASE_URL=postgresql://user:password@host:5432/dbname"
        )
    return url
