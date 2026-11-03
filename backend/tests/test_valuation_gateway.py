from datetime import datetime, timezone

import pandas as pd
import pytest

from backend.valuation_gateway import BaselineGateway, ModelUnavailable

NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)
QUERY = dict(latitude=40.18, longitude=44.51, area_sqm=70, district="Kentron")


def snapshot():
    return pd.DataFrame([dict(price_usd=p, area_sqm=50, latitude=40.18,
        longitude=44.51, district="Kentron", rooms=2, listing_date="2026-10-20",
        dedup_group_id=str(i)) for i, p in enumerate([500, 600, 700])])


def test_success_versions_and_actual_freshness():
    result = BaselineGateway(snapshot(), dataset_version="synthetic-v1").assess(QUERY, as_of=NOW)
    assert result["valuation_assessment"]["estimated_price_usd"] == 840
    assert result["observed_market_statistics"]["data_freshness_days"] == 1
    assert result["versions"]["dataset_version"] == "synthetic-v1"
    assert result["ml_prediction_interval"] is None


@pytest.mark.parametrize("changes", [
    {"latitude": 50}, {"listing_date": "2020-01-01"},
    {"listing_date": "2027-01-01"}, {"area_sqm": 0},
    {"price_usd": float("inf")}, {"dedup_group_id": "same"},
])
def test_unusable_or_duplicate_reference_abstains(changes):
    frame = snapshot().assign(**changes)
    result = BaselineGateway(frame, dataset_version="test").assess(QUERY, as_of=NOW)
    assert result["valuation_assessment"]["estimated_price_usd"] is None


def test_excludes_subject_duplicate_group():
    result = BaselineGateway(snapshot(), dataset_version="test").assess(QUERY, as_of=NOW, exclude_group="0")
    assert result["observed_market_statistics"]["comparables_count"] == 2


def test_model_failure_is_not_insufficient_data():
    class Broken:
        def __init__(self, frame, **kwargs):
            raise RuntimeError("failure")
    with pytest.raises(ModelUnavailable):
        BaselineGateway(snapshot(), dataset_version="test", predictor=Broken).assess(QUERY, as_of=NOW)
