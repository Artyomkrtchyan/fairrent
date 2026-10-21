import json
from pathlib import Path

import pytest


@pytest.fixture
def listing_document():
    path = Path(__file__).resolve().parents[2] / "contracts" / "fixtures.json"
    document = json.loads(path.read_text(encoding="utf-8"))["listings"]["value"]["items"][0]
    return {key: value for key, value in document.items() if key not in ("freshness", "price_status")}
