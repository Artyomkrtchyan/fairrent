import json
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


def test_groups_with_tied_anchor_dates_stay_in_one_chronological_split():
    rows = [
        _row(1, "2026-01-01T08:00:00"),
        _row(2, "2026-01-01T10:00:00"),
        _row(3, "2026-01-01T14:00:00"),
        _row(4, "2026-01-01T18:00:00"),
        _row(5, "2026-01-01T20:00:00"),
        _row(6, "2026-01-01T22:00:00"),
        _row(7, "2026-02-01T10:00:00"),
        _row(8, "2026-03-01T10:00:00"),
    ]

    splits, report = prepare_snapshot(rows, date(2026, 4, 10))

    date_splits = {}
    for split_name, split_rows in splits.items():
        for row in split_rows:
            date_splits.setdefault(row["observation_date"], set()).add(split_name)
    assert date_splits["2026-01-01"] == {"train"}
    assert all(len(assigned_splits) == 1 for assigned_splits in date_splits.values())
    train_dates = {row["observation_date"] for row in splits["train"]}
    validation_dates = {row["observation_date"] for row in splits["validation"]}
    test_dates = {row["observation_date"] for row in splits["test"]}
    assert max(train_dates) < min(validation_dates)
    assert max(validation_dates) < min(test_dates)
    assert report["splits"]["train_end_date"] < report["splits"]["validation_start_date"]
    assert report["splits"]["validation_end_date"] < report["splits"]["test_start_date"]
    assert report["splits"]["row_counts"] == {"train": 6, "validation": 1, "test": 1}


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


def _one_day_rows(count=40):
    # One observation date for every listing, like a single-scrape import.
    return [_row(i, "2026-10-31T09:47:00") for i in range(1, count + 1)]


def test_grouped_random_split_works_on_one_observation_date_and_is_labeled_non_temporal():
    splits, report = prepare_snapshot(_one_day_rows(), date(2026, 10, 31), split_mode="grouped-random")

    counts = {name: len(rows) for name, rows in splits.items()}
    assert all(count > 0 for count in counts.values()), counts
    assert sum(counts.values()) == 40
    assert counts == {"train": 28, "validation": 6, "test": 6}
    assert report["splits"]["method"] == "grouped-random"
    assert report["splits"]["temporal_validity"] is False
    assert report["splits"]["distinct_observation_dates"] == 1
    assert report["splits"]["train_end_date"] is None
    assert report["splits"]["test_start_date"] is None
    assert "optimistic" in report["splits"]["warning"]
    assert report["splits"]["rows_excluded_after_group_split_boundary"] == {}


def test_default_chronological_mode_still_cannot_split_one_observation_date():
    splits, report = prepare_snapshot(_one_day_rows(), date(2026, 10, 31))

    assert len(splits["train"]) == 40
    assert len(splits["validation"]) == len(splits["test"]) == 0
    assert "method" not in report["splits"]


def test_grouped_random_split_is_deterministic_and_keeps_groups_together():
    rows = _one_day_rows(30) + [_row(5, "2026-10-31T10:00:00", external_id="repost", area_sqm=55.2)]

    first, _ = prepare_snapshot(rows, date(2026, 10, 31), split_mode="grouped-random")
    second, _ = prepare_snapshot(list(reversed(rows)), date(2026, 10, 31), split_mode="grouped-random")

    assert first == second  # independent of input row order
    locations = {}
    for split_name, split_rows in first.items():
        for row in split_rows:
            locations.setdefault(row["dedup_group_id"], set()).add(split_name)
    assert all(len(value) == 1 for value in locations.values())
    other_seed, _ = prepare_snapshot(rows, date(2026, 10, 31), split_mode="grouped-random", split_seed="other")
    assert other_seed != first


def test_grouped_random_manifest_records_non_temporal_policy_and_default_manifest_is_unchanged():
    rows = _one_day_rows(12)
    splits, quality = prepare_snapshot(rows, date(2026, 10, 31), split_mode="grouped-random")
    manifest = json.loads(create_artifacts(splits, quality, "v1.0.0-grouped", date(2026, 10, 31))["manifest.json"])
    policy = manifest["split_policy"]
    assert policy["temporal"] is False
    assert policy["seed"] == quality["splits"]["seed"]
    assert "A and B owners" in policy["approval"]

    default_splits, default_quality = prepare_snapshot(rows, date(2026, 10, 31))
    default = json.loads(create_artifacts(default_splits, default_quality, "v1.0.0", date(2026, 10, 31))["manifest.json"])
    assert "temporal" not in default["split_policy"]
    assert default["split_policy"]["method"].startswith("chronological")


def test_grouped_random_rejects_unknown_mode_and_handles_tiny_inputs():
    with pytest.raises(ValueError):
        prepare_snapshot(_one_day_rows(3), date(2026, 10, 31), split_mode="shuffle")
    one, _ = prepare_snapshot(_one_day_rows(1), date(2026, 10, 31), split_mode="grouped-random")
    assert (len(one["train"]), len(one["validation"]), len(one["test"])) == (1, 0, 0)
    three, _ = prepare_snapshot(_one_day_rows(3), date(2026, 10, 31), split_mode="grouped-random")
    assert all(len(rows) == 1 for rows in three.values())


def _twin(property_id, observed="2026-10-31T09:47:00", **overrides):
    # Same coordinates / area / price as _row(1, ...) but a different property (own group).
    base = _row(1, observed)
    return _row(property_id, observed, latitude=base["latitude"], longitude=base["longitude"], **overrides)


def test_merge_near_duplicates_puts_identical_fingerprints_in_one_group():
    rows = [_row(1, "2026-10-31T09:47:00"), _twin(2), _twin(3, external_id="repost"), _row(4, "2026-10-31T09:47:00")]

    plain, _ = prepare_snapshot(rows, date(2026, 10, 31), split_mode="grouped-random")
    merged, quality = prepare_snapshot(rows, date(2026, 10, 31), split_mode="grouped-random",
                                       merge_near_duplicates=True)

    plain_groups = {r["dedup_group_id"] for part in plain.values() for r in part}
    merged_groups = {r["dedup_group_id"] for part in merged.values() for r in part}
    assert len(plain_groups) == 4
    assert len(merged_groups) == 2  # properties 1,2,3 merge; 4 differs in latitude
    stats = quality["duplicates"]["near_duplicate_merge"]
    assert stats["merged_groups_created"] == 1
    assert stats["groups_absorbed"] == 3
    assert stats["rows_in_merged_groups"] == 3
    assert stats["largest_merged_group_rows"] == 3
    locations = {}
    for split_name, part in merged.items():
        for row in part:
            locations.setdefault(row["dedup_group_id"], set()).add(split_name)
    assert all(len(value) == 1 for value in locations.values())


def test_merge_near_duplicates_is_deterministic_and_chains_through_shared_groups():
    # A~B share a fingerprint and B~C share another, so all three must collapse into one group.
    a = _row(1, "2026-10-31T09:47:00")
    b = _twin(2)
    c = _twin(3, area_sqm=60.0)
    b2 = _twin(2, area_sqm=60.0)  # a second row of property 2 with C's fingerprint
    first, _ = prepare_snapshot([a, b, c, b2], date(2026, 10, 31), merge_near_duplicates=True)
    second, _ = prepare_snapshot([b2, c, b, a], date(2026, 10, 31), merge_near_duplicates=True)
    ids = {r["dedup_group_id"] for part in first.values() for r in part}
    assert len(ids) == 1
    assert first == second


def test_merge_ignores_rows_without_area_and_default_output_has_no_merge_fields():
    no_area_a = _row(1, "2026-10-31T09:47:00", area_sqm=None)
    no_area_b = _twin(2, area_sqm=None)
    splits, quality = prepare_snapshot([no_area_a, no_area_b], date(2026, 10, 31), merge_near_duplicates=True)
    assert len({r["dedup_group_id"] for part in splits.values() for r in part}) == 2
    assert quality["duplicates"]["near_duplicate_merge"]["merged_groups_created"] == 0

    _, default_quality = prepare_snapshot([no_area_a], date(2026, 10, 31))
    assert "near_duplicate_merge" not in default_quality["duplicates"]


def test_merge_is_recorded_in_manifest_only_when_enabled():
    rows = [_row(1, "2026-10-31T09:47:00"), _twin(2)]
    splits, quality = prepare_snapshot(rows, date(2026, 10, 31), merge_near_duplicates=True)
    on = json.loads(create_artifacts(splits, quality, "v1", date(2026, 10, 31))["manifest.json"])
    assert "merged into one group" in on["dedup_group_policy"]
    splits, quality = prepare_snapshot(rows, date(2026, 10, 31))
    off = json.loads(create_artifacts(splits, quality, "v1", date(2026, 10, 31))["manifest.json"])
    assert "merged" not in off["dedup_group_policy"]
