from datetime import date, datetime, timedelta, timezone

import pytest

from .aggregate_neighborhoods import (
    MINIMUM_SAMPLE_COUNT,
    build_weekly_aggregates,
    week_window,
)


WEEK = date(2026, 10, 19)  # Monday
OBSERVED = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)


def _listing(property_id, price, area=50, **overrides):
    row = {
        "property_id": property_id,
        "district_id": "kentron",
        "price_usd": price,
        "area_sqm": area,
        "original_period": "month",
        "last_seen_at": OBSERVED,
        "is_active": True,
        "source": "list.am",
    }
    row.update(overrides)
    return row


def test_weekly_medians_match_known_active_property_dataset_and_deduplicate_ads():
    rows = [_listing(index, price) for index, price in enumerate((500, 600, 700, 800, 900), start=1)]
    rows.append(_listing(1, 500))  # second active ad for one already-counted property

    result = build_weekly_aggregates(rows, WEEK, generated_at=OBSERVED)

    assert len(result) == 1
    aggregate = result[0]
    assert aggregate["period_start"] == WEEK
    assert aggregate["period_end"] == date(2026, 10, 25)
    assert aggregate["median_price_usd_month"] == 700
    assert aggregate["median_price_usd_per_sqm"] == 14
    assert aggregate["sample_count"] == aggregate["per_sqm_sample_count"] == 5
    assert aggregate["price_status"] == aggregate["per_sqm_status"] == "available"
    assert aggregate["data_as_of"] == OBSERVED
    assert aggregate["price_basis"] == "asking"


def test_sparse_district_keeps_counts_but_suppresses_unstable_medians():
    result = build_weekly_aggregates([_listing(1, 500), _listing(2, 700)], WEEK)

    assert result[0]["sample_count"] == 2
    assert result[0]["median_price_usd_month"] is None
    assert result[0]["price_status"] == "insufficient_data"
    assert result[0]["median_price_usd_per_sqm"] is None
    assert result[0]["per_sqm_status"] == "insufficient_data"
    assert result[0]["minimum_sample_count"] == MINIMUM_SAMPLE_COUNT


def test_unit_price_can_be_sparse_independently_of_monthly_price():
    rows = [_listing(index, 500 + index * 100, area=None if index in (1, 2) else 50)
            for index in range(1, 7)]

    result = build_weekly_aggregates(rows, WEEK)

    assert result[0]["sample_count"] == 6
    assert result[0]["median_price_usd_month"] == 850
    assert result[0]["price_status"] == "available"
    assert result[0]["per_sqm_sample_count"] == 4
    assert result[0]["median_price_usd_per_sqm"] is None
    assert result[0]["per_sqm_status"] == "insufficient_data"


def test_only_active_observed_long_term_inventory_with_valid_prices_and_districts_counts():
    rows = [
        *[_listing(index, 500 + index * 100) for index in range(1, 6)],
        _listing(6, 10_000, original_period="day"),
        _listing(7, 10_000, original_period="week"),
        _listing(8, 900, is_active=False),
        _listing(9, -1),
        _listing(10, 900, district_id=None),
        _listing(11, 900, last_seen_at=datetime(2026, 10, 26, tzinfo=timezone.utc)),
    ]

    result = build_weekly_aggregates(rows, WEEK)

    assert result[0]["sample_count"] == 5
    assert result[0]["median_price_usd_month"] == 800


def test_reporting_window_is_monday_through_sunday_in_yerevan_converted_to_utc():
    start, end_exclusive, period_end = week_window(WEEK)
    assert start == datetime(2026, 10, 18, 20, tzinfo=timezone.utc)
    assert end_exclusive == datetime(2026, 10, 25, 20, tzinfo=timezone.utc)
    assert period_end == date(2026, 10, 25)
    with pytest.raises(ValueError, match="Monday"):
        week_window(date(2026, 10, 20))


def test_reporting_window_includes_yerevan_monday_and_sunday_boundaries():
    start, end_exclusive, _ = week_window(WEEK)
    rows = [
        _listing(1, 500, last_seen_at=start - timedelta(seconds=1)),
        _listing(2, 600, last_seen_at=start),
        _listing(3, 700, last_seen_at=end_exclusive - timedelta(seconds=1)),
        _listing(4, 800, last_seen_at=end_exclusive),
    ]

    result = build_weekly_aggregates(rows, WEEK)

    assert len(result) == 1
    assert result[0]["sample_count"] == 2
    assert result[0]["data_as_of"] == end_exclusive - timedelta(seconds=1)


def test_latest_eligible_duplicate_observation_is_used_instead_of_ad_median():
    rows = [
        _listing(1, 1_500, last_seen_at=OBSERVED + timedelta(days=1), listing_id=20),
        _listing(1, 500, last_seen_at=OBSERVED - timedelta(days=1), listing_id=10),
        *[_listing(index, price) for index, price in enumerate((600, 700, 800, 900), start=2)],
    ]

    result = build_weekly_aggregates(rows, WEEK)

    assert result[0]["sample_count"] == 5
    assert result[0]["median_price_usd_month"] == 800
    assert result[0]["median_price_usd_per_sqm"] == 16
    assert result[0]["data_as_of"] == OBSERVED + timedelta(days=1)
