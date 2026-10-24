from datetime import date, datetime, timezone
import pytest

from .export_dataset import (
    CSV_FIELDS,
    create_artifacts,
    prepare_snapshot,
    write_versioned_snapshot,
)


def _row(property_id, observed, *, first_seen=None, external_id="private-id", **overrides):
    observed_at = datetime.fromisoformat(observed).replace(tzinfo=timezone.utc)
    first_seen_at = datetime.fromisoformat(first_seen or observed).replace(tzinfo=timezone.utc)
    row = {
        "source": "list.am",
        "_property_id": property_id,
        "price_usd": 600.0,
        "original_price": 600.0,
        "original_currency": "USD",
        "original_period": "month",
        "exchange_rate": 1.0,
        "rate_source": "identity",
        "rate_date": date(2026, 1, 1),
        "utilities_included": None,
        "area_sqm": 55.0,
        "rooms": 2,
        "floor": 5,
        "total_floors": 9,
        "building_type": "stone",
        "first_seen_at": first_seen_at,
        "observation_at": observed_at,
        "ingestion_run_id": 42,
        "raw_data": {"external_id": external_id, "url": "https://private.example.invalid/item/1",
                     "description": "private description", "rejected_fields": {}},
        "latitude": 40.1792 + property_id / 10000,
        "longitude": 44.5151,
        "district_id": "kentron",
        "distance_metro_m": 700.0,
        "distance_center_m": 300.0,
        "distance_university_m": 1200.0,
        "coordinate_source": "list.am:data-lat-data-lng",
        "coordinate_confidence": "approximate",
        "geography_version": "yerevan-geo-v1",
    }
    row.update(overrides)
    return row


def test_snapshot_excludes_invalid_training_rows_and_reports_invalid_values():
    valid = _row(1, "2026-01-01T10:00:00")
    valid["raw_data"]["rejected_fields"] = {"rooms_count": "2.5"}
    no_coordinates = _row(2, "2026-01-02T10:00:00", latitude=None, longitude=None)
    invalid_price = _row(3, "2026-01-03T10:00:00", price_usd=-1)

    splits, report = prepare_snapshot([valid, no_coordinates, invalid_price], date(2026, 12, 31))

    assert sum(map(len, splits.values())) == 1
    assert report["excluded_by_reason"] == {
        "invalid_or_missing_price": 1,
        "missing_coordinates": 1,
    }
    assert report["invalid_values_from_rejected_fields"] == {"rooms_count": 1}
    assert report["missingness"]["area_sqm"]["missing"] == 0


def test_daily_rentals_are_not_published_as_long_term_training_targets():
    daily = _row(1, "2026-01-01T10:00:00", original_period="day")

    splits, report = prepare_snapshot([daily], date(2026, 12, 31))

    assert sum(map(len, splits.values())) == 0
    assert report["excluded_by_reason"] == {"non_long_term_rental": 1}


def test_duplicate_group_is_kept_in_one_chronological_split_and_future_rows_are_excluded():
    rows = [
        _row(1, "2026-01-01T10:00:00", external_id="A"),
        _row(1, "2026-04-01T10:00:00", external_id="B", area_sqm=55.2),
        _row(2, "2026-02-01T10:00:00"),
        _row(3, "2026-03-01T10:00:00"),
    ]

    splits, report = prepare_snapshot(rows, date(2026, 12, 31))

    group_locations = {}
    for split, split_rows in splits.items():
        for row in split_rows:
            group_locations.setdefault(row["dedup_group_id"], set()).add(split)
    assert all(len(locations) == 1 for locations in group_locations.values())
    assert report["duplicates"]["groups_with_multiple_listings"] == 1
    assert report["duplicates"]["rows_in_duplicate_groups"] == 2
    assert report["splits"]["rows_excluded_after_group_split_boundary"] == {"train": 1}
    assert sum(map(len, splits.values())) == 3


def test_snapshot_artifacts_are_deterministic_and_do_not_export_raw_listing_fields():
    splits, quality = prepare_snapshot([_row(1, "2026-01-01T10:00:00")], date(2026, 12, 31))
    first = create_artifacts(splits, quality, "v1.0.0", date(2026, 12, 31))
    second = create_artifacts(splits, quality, "v1.0.0", date(2026, 12, 31))

    assert first == second
    assert set(CSV_FIELDS).issubset(first["train.csv"].decode("utf-8").splitlines()[0].split(","))
    exported = b"".join(first[name] for name in ("train.csv", "validation.csv", "test.csv"))
    assert b"private-id" not in exported
    assert b"private description" not in exported
    assert b"private.example.invalid" not in exported
    assert b"external_id" not in first["train.csv"]


def test_versioned_snapshot_is_idempotent_and_rejects_changed_content(tmp_path):
    splits, quality = prepare_snapshot([_row(1, "2026-01-01T10:00:00")], date(2026, 12, 31))
    artifacts = create_artifacts(splits, quality, "v1.0.0", date(2026, 12, 31))
    output = write_versioned_snapshot(tmp_path, "v1.0.0", artifacts)
    assert write_versioned_snapshot(tmp_path, "v1.0.0", artifacts) == output

    changed = dict(artifacts)
    changed["quality_report.json"] = b"{}\n"
    with pytest.raises(Exception, match="already exists with different content"):
        write_versioned_snapshot(tmp_path, "v1.0.0", changed)
