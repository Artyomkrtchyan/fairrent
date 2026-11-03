from datetime import date, datetime, timezone

import pytest

from backend.source_adapter import Unpublishable, adapt_source, listing_uuid


@pytest.fixture
def source_row():
    return dict(source="list.am", external_id="test-1", url="https://example.invalid/item/1",
                property_id=7, last_seen_run_id=1, original_price=600,
                original_currency="USD", original_period="month", is_active=True,
                first_seen_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
                last_seen_at=datetime(2026, 10, 21, tzinfo=timezone.utc),
                raw_data={}, area_sqm=50, rooms_count=2)


def test_usd_identity_is_observation_dated(source_row):
    record = adapt_source(source_row)
    assert record.conversion.rate_source == "identity"
    assert record.conversion.rate_date == date(2026, 10, 21)
    assert record.conversion.rate_to_usd == 1
    assert record.id == listing_uuid("list.am", "test-1")
    assert record.latitude is record.longitude is None
    assert record.coordinate_confidence == "unknown"


def test_amd_monthly_rate_direction_is_inverted(source_row):
    source_row.update(original_price=300000, original_currency="AMD", original_period="month",
                      exchange_rate=385, rate_date=date(2026, 10, 20), rate_source="static-config")
    record = adapt_source(source_row)
    assert record.price_original == 300000
    assert record.price_monthly_normalized == 779.22
    assert record.conversion.rate_to_usd == pytest.approx(1 / 385)
    assert record.conversion.rate_date == date(2026, 10, 20)


def test_decimal_half_up_rounding(source_row):
    source_row["original_price"] = 3.125
    assert adapt_source(source_row).price_monthly_normalized == 3.13


def test_unknown_historical_rate_never_becomes_current_rate(source_row):
    source_row.update(original_currency="AMD", exchange_rate=385, rate_source="static-config", rate_date=None)
    record = adapt_source(source_row)
    assert record.conversion is record.price_monthly_normalized is None


def test_current_raw_enrichment_and_unknown_materials(source_row):
    source_row.update(district=None, address_raw=None, building_type="new_building",
                      raw_data={"district": "Kentron", "address_raw": "Synthetic address"})
    record = adapt_source(source_row)
    assert record.district_id == "kentron"
    assert record.address == "Synthetic address"
    assert record.building_type is None and record.building_type_raw == "new_building"
    source_row["raw_data"]["district"] = "unregistered-area"
    assert adapt_source(source_row).district_id is None


@pytest.mark.parametrize('name,slug', [
    ('Աջափնյակ', 'ajapnyak'), ('Malatia Sebastia', 'malatia-sebastia'),
    ('Քանաքեռ-Զեյթուն', 'kanaker-zeytun'), ('nor-nork', 'nor-nork'),
    ('Nubarashen', 'nubarashen'), ('Davtashen', 'davtashen'),
])
def test_a05_district_names_publish_beyond_the_two_legacy_districts(source_row, name, slug):
    source_row['raw_data'] = {'district': name}
    assert adapt_source(source_row).district_id == slug


def test_persisted_a05_district_survives_missing_current_scrape_field(source_row):
    source_row.update(district_id='avan', district='unrecognized legacy text', raw_data={'district': None})
    assert adapt_source(source_row).district_id == 'avan'
    source_row['raw_data']['district'] = 'Shengavit'
    assert adapt_source(source_row).district_id == 'shengavit'


@pytest.mark.parametrize('confidence', ['exact', 'approximate', 'unknown'])
def test_a05_coordinate_confidence_is_not_replaced_by_approximate(source_row, confidence):
    source_row.update(latitude=40.18, longitude=44.51, coordinate_confidence=confidence)
    assert adapt_source(source_row).coordinate_confidence == confidence
    source_row.update(latitude=None, longitude=None)
    assert adapt_source(source_row).coordinate_confidence == 'unknown'


@pytest.mark.parametrize("changes,reason", [
    ({"last_seen_run_id": None}, "unobserved_legacy_record"),
    ({"original_price": None}, "missing_original_price"),
    ({"original_period": "fortnight"}, "unsupported_period"),
    ({"source": "demo"}, "unsupported_source"),
])
def test_insufficient_records_have_explicit_exclusion_reasons(source_row, changes, reason):
    with pytest.raises(Unpublishable, match=reason):
        adapt_source({**source_row, **changes})


@pytest.mark.parametrize("period", ["day", "daily", "week", "weekly", " DAILY "])
def test_short_term_quotes_are_not_long_term_evidence(source_row, period):
    source_row.update(original_period=period)
    with pytest.raises(Unpublishable, match="short_term_rental"):
        adapt_source(source_row)


@pytest.mark.parametrize("period", ["month", "monthly", "year", "yearly", "annual"])
def test_long_term_quotes_remain_eligible(source_row, period):
    source_row.update(original_period=period)
    expected = 50 if period in {"year", "yearly", "annual"} else 600
    assert adapt_source(source_row).price_monthly_normalized == expected
