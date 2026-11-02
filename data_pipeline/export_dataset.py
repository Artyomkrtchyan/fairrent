from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import statistics
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
import click
from sqlalchemy import func
from sqlalchemy.orm import Session
from database.models import IngestionRun, Listing, Property
from .config import DEFAULT_SOURCE_NAME, get_database_url
from .geography import DISTRICTS
from .normalizer import monthly_multiplier

DATASET_SCHEMA_VERSION = "a06-v1"
CONTRACT_VERSION = "C01-v0.2.0"
SPLIT_RATIOS = {"train": 0.70, "validation": 0.15, "test": 0.15}
SPLIT_MODES = ("chronological", "grouped-random")
DEFAULT_SPLIT_SEED = "fairrent-grouped-random-v1"

# Raw listing identifiers, URLs, addresses, titles, descriptions, images, and raw HTML are
# deliberately excluded. The hashed group key is the only cross-row identity in an export.
CSV_FIELDS = (
    "observation_date", "observation_at", "first_seen_at", "dedup_group_id",
    "price_usd", "latitude", "longitude", "area_sqm", "rooms", "building_type",
    "floor", "total_floors", "renovation", "district", "distance_metro_m", "distance_center_m",
    "distance_university_m", "utilities_included", "source", "ingestion_run_id",
    "original_price", "original_currency", "original_period", "exchange_rate",
    "rate_source", "rate_date", "coordinate_source", "coordinate_confidence",
    "geography_version",
)

FEATURE_DEFINITIONS = [
    {"name": "price_usd", "role": "target", "type": "number", "unit": "USD/month",
     "definition": "Observed monthly asking rent; never included as a model input."},
    {"name": "latitude", "role": "feature", "type": "number", "unit": "degrees",
     "definition": "WGS84 latitude from the linked property point."},
    {"name": "longitude", "role": "feature", "type": "number", "unit": "degrees",
     "definition": "WGS84 longitude from the linked property point."},
    {"name": "area_sqm", "role": "feature", "type": "number|null", "unit": "m²",
     "definition": "Reported apartment area; null when unknown."},
    {"name": "rooms", "role": "feature", "type": "integer|null", "unit": "rooms",
     "definition": "Reported room count; null when unknown."},
    {"name": "floor", "role": "feature", "type": "integer|null", "unit": "floor",
     "definition": "Reported apartment floor; null when unknown."},
    {"name": "total_floors", "role": "feature", "type": "integer|null", "unit": "floors",
     "definition": "Reported total building floors; null when unknown."},
    {"name": "building_type", "role": "feature", "type": "string|null", "unit": None,
     "definition": "Source building type when present; not inferred."},
    {"name": "renovation", "role": "feature", "type": "string|null", "unit": None,
     "definition": "Not currently collected; always null until a verified source mapping exists."},
    {"name": "district", "role": "feature", "type": "string|null", "unit": None,
     "definition": "Canonical district label from the A05 registry; null if unresolved."},
    {"name": "distance_metro_m", "role": "feature", "type": "number|null", "unit": "m",
     "definition": "Straight-line geodesic distance to nearest registered metro station."},
    {"name": "distance_center_m", "role": "feature", "type": "number|null", "unit": "m",
     "definition": "Straight-line geodesic distance to Republic Square."},
    {"name": "distance_university_m", "role": "feature", "type": "number|null", "unit": "m",
     "definition": "Straight-line geodesic distance to nearest registered university point."},
    {"name": "utilities_included", "role": "feature", "type": "boolean|null", "unit": None,
     "definition": "Source value; null means utility inclusion/cost is unknown."},
]

MISSINGNESS_FIELDS = (
    "price_usd", "latitude", "longitude", "area_sqm", "rooms", "building_type",
    "floor", "total_floors",
    "district", "distance_metro_m", "distance_center_m", "distance_university_m",
    "utilities_included", "observation_at", "dedup_group_id",
)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _canonical_label(district_id: str | None) -> str | None:
    aliases = DISTRICTS.get(district_id or "")
    return aliases[0] if aliases else None


def _mode(values: list[Any]) -> Any:
    values = [value for value in values if value is not None]
    if not values:
        return None
    counts = Counter(values)
    return sorted(counts, key=lambda value: (-counts[value], str(value)))[0]


def _group_ids(rows: list[dict]) -> dict[int, str]:
    """Hash normalized location/structure plus DB property identity as a collision guard."""
    members: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        if row.get("_property_id") is not None:
            members[int(row["_property_id"])].append(row)

    signatures: dict[int, str] = {}
    for property_id, group in members.items():
        first = group[0]
        areas = [r["area_sqm"] for r in group if r.get("area_sqm") is not None]
        lat, lon = first.get("latitude"), first.get("longitude")
        signature = {
            "source": first.get("source"),
            "latitude": round(float(lat), 6) if lat is not None else None,
            "longitude": round(float(lon), 6) if lon is not None else None,
            "district_id": first.get("district_id"),
            "area_sqm": round(statistics.median(areas), 1) if areas else None,
            "rooms": _mode([r.get("rooms") for r in group]),
            "floor": _mode([r.get("floor") for r in group]),
            "total_floors": _mode([r.get("total_floors") for r in group]),
            # Keep distinct A04 property groups distinct when normalized features coincide.
            "property_group_disambiguator": property_id,
        }
        encoded = json.dumps(signature, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        signatures[property_id] = hashlib.sha256(
            ("fairrent-dedup-group-v1:" + encoded).encode("utf-8")
        ).hexdigest()
    return signatures


def _validate_row(row: dict) -> list[str]:
    reasons = []
    period = str(row.get("original_period") or "").strip().lower()
    try:
        monthly_multiplier(period)
    except ValueError:
        reasons.append("invalid_or_missing_rental_period")
    if any(token in period for token in ("day", "daily", "week", "weekly", "օրական", "շաբաթական")):
        reasons.append("non_long_term_rental")
    price = row.get("price_usd")
    if price is None or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
        reasons.append("invalid_or_missing_price")
    lat, lon = row.get("latitude"), row.get("longitude")
    if lat is None or lon is None:
        reasons.append("missing_coordinates")
    elif (not isinstance(lat, (int, float)) or not isinstance(lon, (int, float))
          or not math.isfinite(lat) or not math.isfinite(lon)
          or not -90 <= lat <= 90 or not -180 <= lon <= 180):
        reasons.append("invalid_coordinates")
    if row.get("observation_at") is None:
        reasons.append("missing_observation_date")
    if row.get("_property_id") is None:
        reasons.append("missing_duplicate_group")
    area = row.get("area_sqm")
    if area is not None and (not isinstance(area, (int, float)) or not math.isfinite(area) or area <= 0):
        reasons.append("invalid_area_sqm")
    rooms = row.get("rooms")
    if rooms is not None and (not isinstance(rooms, int) or rooms < 1):
        reasons.append("invalid_rooms")
    floor, total_floors = row.get("floor"), row.get("total_floors")
    if floor is not None and (not isinstance(floor, int) or floor < 0):
        reasons.append("invalid_floor")
    if total_floors is not None and (not isinstance(total_floors, int) or total_floors < 1):
        reasons.append("invalid_total_floors")
    if floor is not None and total_floors is not None and floor > total_floors:
        reasons.append("floor_exceeds_total_floors")
    return reasons


def _json_datetime(value: datetime | None) -> str | None:
    normalized = _utc(value)
    return normalized.isoformat().replace("+00:00", "Z") if normalized else None


def _grouped_random_assignment(group_ids: Iterable[str], seed: str) -> dict[str, str]:
    """Deterministic, seeded, duplicate-group-isolated 70/15/15 assignment.

    Groups are ordered by SHA-256(seed:group_id) -- independent of database row order, so
    the same inputs always give the same split -- then cut by SPLIT_RATIOS. This is NOT a
    temporal split and exists only for snapshots whose rows share (almost) one observation
    date, where a chronological split is impossible. It gives no forward-looking guarantee.
    """
    ordered = sorted(group_ids, key=lambda g: hashlib.sha256(f"{seed}:{g}".encode("utf-8")).hexdigest())
    total = len(ordered)
    if total == 0:
        return {}
    if total == 1:
        return {ordered[0]: "train"}
    if total == 2:
        return {ordered[0]: "train", ordered[1]: "test"}
    train_count = max(1, min(round(total * SPLIT_RATIOS["train"]), total - 2))
    validation_count = max(1, min(round(total * SPLIT_RATIOS["validation"]), total - train_count - 1))
    assignment = {}
    for index, group_id in enumerate(ordered):
        if index < train_count:
            assignment[group_id] = "train"
        elif index < train_count + validation_count:
            assignment[group_id] = "validation"
        else:
            assignment[group_id] = "test"
    return assignment


def _merge_near_duplicate_groups(valid: list[dict]) -> dict:
    """Merge dedup groups whose rows share a near-duplicate fingerprint, in place.

    The fingerprint is (latitude, longitude) rounded to 5 decimals, area to 0.1 m^2 and USD
    price to whole dollars -- the same definition the B04 leakage check uses. Scraped listings
    that repeat one apartment (or several identical units in one building) otherwise form many
    one-listing groups, and a split can then separate twins between train and test. Merged
    groups get a new SHA-256 id over their sorted member ids, so a merge is deterministic.
    Rows without an area cannot be fingerprinted and are left alone, as in the B04 check.
    """
    parent: dict[str, str] = {}

    def find(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    first_group_for: dict[tuple, str] = {}
    for row in valid:
        group_id = row["dedup_group_id"]
        parent.setdefault(group_id, group_id)
        area = row.get("area_sqm")
        if area is None:
            continue
        key = (round(row["latitude"], 5), round(row["longitude"], 5),
               round(float(area), 1), round(row["price_usd"], 0))
        if key in first_group_for:
            root_a, root_b = find(first_group_for[key]), find(group_id)
            if root_a != root_b:
                parent[root_b] = root_a
        else:
            first_group_for[key] = group_id

    components: dict[str, set[str]] = defaultdict(set)
    for group_id in parent:
        components[find(group_id)].add(group_id)
    mapping: dict[str, str] = {}
    for members in components.values():
        if len(members) > 1:
            merged_id = hashlib.sha256(
                ("fairrent-dedup-merge-v1:" + "|".join(sorted(members))).encode("utf-8")).hexdigest()
            for member in members:
                mapping[member] = merged_id
    merged_row_counts: Counter = Counter()
    for row in valid:
        if row["dedup_group_id"] in mapping:
            row["dedup_group_id"] = mapping[row["dedup_group_id"]]
            merged_row_counts[row["dedup_group_id"]] += 1
    return {
        "enabled": True,
        "fingerprint": "latitude/longitude rounded to 5 decimals, area_sqm to 0.1, price_usd to whole USD",
        "merged_groups_created": len(merged_row_counts),
        "groups_absorbed": len(mapping),
        "rows_in_merged_groups": sum(merged_row_counts.values()),
        "largest_merged_group_rows": max(merged_row_counts.values(), default=0),
    }


def prepare_snapshot(raw_rows: Iterable[dict], as_of: date, split_mode: str = "chronological",
                     split_seed: str = DEFAULT_SPLIT_SEED,
                     merge_near_duplicates: bool = False) -> tuple[dict[str, list[dict]], dict]:
    """Validate rows, enforce group-isolated splits, and build a quality report.

    ``split_mode="chronological"`` (default) is the A06 policy. ``"grouped-random"`` is an
    explicit, labeled fallback for one-observation-date snapshots; see _grouped_random_assignment.
    """
    if split_mode not in SPLIT_MODES:
        raise ValueError(f"split_mode must be one of {SPLIT_MODES}, got {split_mode!r}")
    cutoff = datetime.combine(as_of + timedelta(days=1), time.min, tzinfo=timezone.utc)
    rows = []
    for source_row in raw_rows:
        row = dict(source_row)
        row["observation_at"] = _utc(row.get("observation_at"))
        row["first_seen_at"] = _utc(row.get("first_seen_at"))
        if row["observation_at"] and row["observation_at"] >= cutoff:
            continue
        rows.append(row)

    groups = _group_ids(rows)
    valid, excluded = [], Counter()
    rejected_fields = Counter()
    for row in rows:
        raw_data = row.get("raw_data") or {}
        for field in (raw_data.get("rejected_fields") or {}):
            rejected_fields[field] += 1
        reasons = _validate_row(row)
        if reasons:
            excluded.update(reasons)
            continue
        property_id = int(row["_property_id"])
        dedup_id = groups[property_id]
        district = _canonical_label(row.get("district_id"))
        valid.append({
            "observation_date": row["observation_at"].date().isoformat(),
            "observation_at": _json_datetime(row["observation_at"]),
            "first_seen_at": _json_datetime(row["first_seen_at"]),
            "dedup_group_id": dedup_id,
            "price_usd": float(row["price_usd"]),
            "latitude": float(row["latitude"]),
            "longitude": float(row["longitude"]),
            "area_sqm": row.get("area_sqm"),
            "rooms": row.get("rooms"),
            "floor": row.get("floor"),
            "total_floors": row.get("total_floors"),
            "building_type": row.get("building_type"),
            "renovation": None,
            "district": district,
            "distance_metro_m": row.get("distance_metro_m"),
            "distance_center_m": row.get("distance_center_m"),
            "distance_university_m": row.get("distance_university_m"),
            "utilities_included": row.get("utilities_included"),
            "source": row.get("source"),
            "ingestion_run_id": row.get("ingestion_run_id"),
            "original_price": row.get("original_price"),
            "original_currency": row.get("original_currency"),
            "original_period": row.get("original_period"),
            "exchange_rate": row.get("exchange_rate"),
            "rate_source": row.get("rate_source"),
            "rate_date": row.get("rate_date").isoformat() if row.get("rate_date") else None,
            "coordinate_source": row.get("coordinate_source"),
            "coordinate_confidence": row.get("coordinate_confidence") or "unknown",
            "geography_version": row.get("geography_version"),
            "_property_id": property_id,
            "_anchor_date": row["observation_at"].date(),
            "_observation_date": row["observation_at"].date(),
        })

    merge_stats = _merge_near_duplicate_groups(valid) if merge_near_duplicates else None
    group_members = defaultdict(list)
    for row in valid:
        group_members[row["dedup_group_id"]].append(row)
    anchors = sorted((min(r["_anchor_date"] for r in members), group_id)
                     for group_id, members in group_members.items())
    group_count = len(anchors)
    groups_by_date = Counter(anchor_date for anchor_date, _ in anchors)
    anchor_dates = sorted(groups_by_date)

    # Choose split boundaries only between dates, so all groups anchored on
    # the same date remain together. Ratios may shift when dates are clustered.
    train_end_index = validation_end_index = None
    if split_mode == "grouped-random":
        pass  # assigned below; no date boundaries exist for a non-temporal split
    elif len(anchor_dates) >= 3:
        group_prefix = [0]
        for anchor_date in anchor_dates:
            group_prefix.append(group_prefix[-1] + groups_by_date[anchor_date])
        candidates = []
        for train_index in range(len(anchor_dates) - 2):
            train_groups = group_prefix[train_index + 1]
            for validation_index in range(train_index + 1, len(anchor_dates) - 1):
                validation_groups = group_prefix[validation_index + 1] - train_groups
                test_groups = group_count - group_prefix[validation_index + 1]
                proportions = (train_groups / group_count, validation_groups / group_count,
                               test_groups / group_count)
                error = sum((actual - target) ** 2 for actual, target in zip(
                    proportions, (SPLIT_RATIOS["train"], SPLIT_RATIOS["validation"],
                                  SPLIT_RATIOS["test"])))
                candidates.append((error, train_index, validation_index))
        _, train_end_index, validation_end_index = min(candidates)
    elif len(anchor_dates) == 2:
        # Three strict time windows cannot be formed from only two dates.
        # Keep the later date for a future test window and report validation empty.
        train_end_index = 0

    group_split = {}
    if split_mode == "grouped-random":
        group_split = _grouped_random_assignment(group_members, split_seed)
    else:
        for anchor_date, group_id in anchors:
            if train_end_index is None or anchor_date <= anchor_dates[train_end_index]:
                group_split[group_id] = "train"
            elif validation_end_index is not None and anchor_date <= anchor_dates[validation_end_index]:
                group_split[group_id] = "validation"
            else:
                group_split[group_id] = "test"

    split_groups: dict[str, list[dict]] = {"train": [], "validation": [], "test": []}
    split_excluded = Counter()
    split_ends = {}
    train_end = anchor_dates[train_end_index] if train_end_index is not None else None
    validation_end = (anchor_dates[validation_end_index]
                      if validation_end_index is not None else None)
    split_ends["train"] = train_end
    split_ends["validation"] = validation_end
    # A non-temporal split has no window ends, so no row is excluded as "after the boundary".
    split_ends["test"] = None if split_mode == "grouped-random" else as_of

    for row in valid:
        split = group_split[row["dedup_group_id"]]
        end = split_ends[split]
        if end is not None and row["_observation_date"] > end:
            split_excluded[split] += 1
            continue
        clean = {key: row[key] for key in CSV_FIELDS}
        split_groups[split].append(clean)

    for split in split_groups:
        split_groups[split].sort(key=lambda row: tuple("" if row[k] is None else str(row[k])
                                                       for k in CSV_FIELDS))

    missingness = {}
    for field in MISSINGNESS_FIELDS:
        missing = sum(row.get(field) is None for row in valid)
        missingness[field] = {"missing": missing,
                              "percent": round(missing * 100 / len(valid), 2) if valid else 0.0}

    all_group_sizes = Counter()
    for row in rows:
        property_id = row.get("_property_id")
        if property_id is not None and int(property_id) in groups:
            all_group_sizes[groups[int(property_id)]] += 1
    duplicate_sizes = all_group_sizes
    duplicate_groups = sum(size > 1 for size in duplicate_sizes.values())
    duplicate_rows = sum(size for size in duplicate_sizes.values() if size > 1)
    neighborhood = Counter(row["district"] or "unresolved" for row in valid)
    quality = {
        "input_rows_as_of": len(rows),
        "eligible_rows": len(valid),
        "excluded_rows": len(rows) - len(valid),
        "missingness_scope": "eligible records before temporal split; denominator is eligible_rows",
        "excluded_by_reason": dict(sorted(excluded.items())),
        "invalid_values_from_rejected_fields": dict(sorted(rejected_fields.items())),
        "invalid_value_rows_included": sum(bool((r.get("raw_data") or {}).get("rejected_fields")) for r in rows),
        "missingness": missingness,
        "duplicates": {
            "dedup_groups": len(duplicate_sizes),
            "groups_with_multiple_listings": duplicate_groups,
            "rows_in_duplicate_groups": duplicate_rows,
            "extra_rows_beyond_one_per_group": sum(max(size - 1, 0) for size in duplicate_sizes.values()),
        },
        "neighborhood_coverage": {
            "rows_by_district": dict(sorted(neighborhood.items())),
            "resolved_district_rows": len(valid) - neighborhood.get("unresolved", 0),
            "unresolved_district_rows": neighborhood.get("unresolved", 0),
        },
        "splits": {
            "group_counts": {name: len({r["dedup_group_id"] for r in values})
                              for name, values in split_groups.items()},
            "row_counts": {name: len(values) for name, values in split_groups.items()},
            "groups_assigned": dict(sorted(Counter(group_split.values()).items())),
            "rows_excluded_after_group_split_boundary": dict(sorted(split_excluded.items())),
            "train_end_date": train_end.isoformat() if train_end else None,
            "validation_end_date": validation_end.isoformat() if validation_end else None,
            "validation_start_date": (anchor_dates[train_end_index + 1].isoformat()
                                      if validation_end_index is not None else None),
            "test_start_date": (anchor_dates[validation_end_index + 1].isoformat()
                                if validation_end_index is not None else
                                anchor_dates[1].isoformat() if len(anchor_dates) == 2 else None),
            "test_end_date": as_of.isoformat(),
        },
    }
    if merge_stats is not None:
        quality["duplicates"]["near_duplicate_merge"] = merge_stats
    if split_mode == "grouped-random":
        # Overwrite date-window fields: they have no meaning without a temporal split.
        quality["splits"].update({
            "method": "grouped-random",
            "seed": split_seed,
            "temporal_validity": False,
            "distinct_observation_dates": len(anchor_dates),
            "train_end_date": None,
            "validation_end_date": None,
            "validation_start_date": None,
            "test_start_date": None,
            "test_end_date": None,
            "warning": ("Non-temporal split: train/validation/test are random duplicate-group-isolated "
                        "samples of one snapshot. Metrics are in-time estimates and are optimistic "
                        "relative to forecasting future listings."),
        })
    return split_groups, quality


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return format(value, ".12g")
    return str(value)


def csv_bytes(rows: list[dict]) -> bytes:
    from io import StringIO
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _csv_value(row.get(field)) for field in CSV_FIELDS})
    return stream.getvalue().encode("utf-8")


def json_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, separators=(",", ": ")) + "\n").encode("utf-8")


def snapshot_digest(artifacts: dict[str, bytes], manifest_metadata: dict | None = None) -> str:
    digest = hashlib.sha256()
    for name in sorted(name for name in artifacts if name != "manifest.json"):
        digest.update(name.encode("utf-8") + b"\0" + artifacts[name] + b"\0")
    if manifest_metadata is not None:
        digest.update(b"manifest-metadata\0" + json_bytes(manifest_metadata))
    return digest.hexdigest()


def create_artifacts(split_rows: dict[str, list[dict]], quality: dict, version: str, as_of: date,
                     source: str = DEFAULT_SOURCE_NAME) -> dict[str, bytes]:
    artifacts = {
        f"{name}.csv": csv_bytes(rows) for name, rows in split_rows.items()
    }
    artifacts["quality_report.json"] = json_bytes(quality)
    split_policy = {
        "method": "chronological by earliest observation_date per dedup group; all group members and tied anchor dates stay in one split",
        "ratios": SPLIT_RATIOS,
        "date_tie_policy": "split boundaries fall only between distinct anchor dates; ratios may deviate to keep tied dates together",
        "future_row_policy": "exclude rows observed after their assigned split end date",
    }
    if quality.get("splits", {}).get("method") == "grouped-random":
        split_policy = {
            "method": ("grouped-random: dedup groups ordered by SHA-256(seed:dedup_group_id) and cut "
                       "70/15/15; all members of a group stay in one split"),
            "temporal": False,
            "seed": quality["splits"]["seed"],
            "ratios": SPLIT_RATIOS,
            "distinct_observation_dates": quality["splits"]["distinct_observation_dates"],
            "future_row_policy": "not applicable (no temporal windows)",
            "limitation": ("Not a forward-looking evaluation. Intended only for snapshots with too few "
                           "distinct observation dates for a chronological split."),
            "approval": ("Using this fallback as project evidence requires explicit agreement of the "
                         "A and B owners (docs/contract-semantics.md)."),
        }
    manifest = {
        "dataset_schema_version": DATASET_SCHEMA_VERSION,
        "dataset_version": version,
        "contract_version": CONTRACT_VERSION,
        "as_of_date": as_of.isoformat(),
        "source": source,
        "observation_policy": "one latest listing state per source listing, observed at last_seen_at <= as_of; price is monthly asking USD",
        "historical_limit": "Price history stores changes, not a full feature snapshot per observation. This export does not treat old price changes as independent rows with current features.",
        "split_policy": split_policy,
        "dedup_group_policy": "SHA-256 of normalized location and group-level structure, with persistent property id as disambiguator; used only for split isolation",
        "features": FEATURE_DEFINITIONS,
        "provenance_fields": ["source", "ingestion_run_id", "original_price", "original_currency",
                              "original_period", "exchange_rate", "rate_source", "rate_date",
                              "coordinate_source", "coordinate_confidence", "geography_version"],
        "privacy": {
            "raw_listing_fields_exported": False,
            "excluded_fields": ["external_id", "url", "title", "description", "address_raw", "images", "raw_data"],
            "identifier_note": "No direct listing/property primary key is exported; dedup_group_id is a SHA-256 pseudonymous group key.",
        },
        "quality_report": "quality_report.json",
    }
    if quality.get("duplicates", {}).get("near_duplicate_merge"):
        manifest["dedup_group_policy"] += (
            "; groups whose rows share rounded coordinates (5 dp), area (0.1 m2) and price (whole USD) are "
            "merged into one group so near-duplicate listings cannot straddle splits "
            "(see quality_report.json duplicates.near_duplicate_merge)")
    manifest["snapshot_sha256"] = snapshot_digest(artifacts, manifest)
    artifacts["manifest.json"] = json_bytes(manifest)
    return artifacts


def write_versioned_snapshot(output_dir: Path, version: str, artifacts: dict[str, bytes]) -> Path:
    target = output_dir / version
    output_dir.mkdir(parents=True, exist_ok=True)
    if target.exists():
        existing = target / "manifest.json"
        if existing.is_file():
            saved = json.loads(existing.read_text(encoding="utf-8"))
            current = json.loads(artifacts["manifest.json"].decode("utf-8"))
            saved_metadata = {key: value for key, value in saved.items() if key != "snapshot_sha256"}
            current_metadata = {key: value for key, value in current.items() if key != "snapshot_sha256"}
            existing_artifacts = {
                name: (target / name).read_bytes()
                for name in artifacts if name != "manifest.json" and (target / name).is_file()
            }
            if (saved_metadata == current_metadata
                    and saved.get("snapshot_sha256") == current.get("snapshot_sha256")
                    and snapshot_digest(existing_artifacts, saved_metadata) == saved.get("snapshot_sha256")
                    and snapshot_digest(artifacts, current_metadata) == current.get("snapshot_sha256")):
                return target
        raise click.ClickException(
            f"Snapshot {target} already exists with different content; choose a new --version."
        )

    with tempfile.TemporaryDirectory(prefix=f".{version}-", dir=output_dir) as temporary:
        staging = Path(temporary)
        for name, payload in artifacts.items():
            (staging / name).write_bytes(payload)
        os.replace(staging, target)
    return target


def _database_rows(session: Session, as_of: date, source: str) -> list[dict]:
    cutoff = datetime.combine(as_of + timedelta(days=1), time.min, tzinfo=timezone.utc)
    statement = (
        session.query(
            Listing.source.label("source"), Listing.property_id.label("_property_id"),
            Listing.price_usd.label("price_usd"), Listing.original_price.label("original_price"),
            Listing.original_currency.label("original_currency"), Listing.original_period.label("original_period"),
            Listing.exchange_rate.label("exchange_rate"), Listing.rate_source.label("rate_source"),
            Listing.rate_date.label("rate_date"), Listing.utilities_included.label("utilities_included"),
            Listing.area_sqm.label("area_sqm"), Listing.rooms_count.label("rooms"),
            Listing.floor.label("floor"), Listing.total_floors.label("total_floors"),
            Listing.building_type.label("building_type"), Listing.first_seen_at.label("first_seen_at"),
            Listing.last_seen_at.label("observation_at"), Listing.last_seen_run_id.label("ingestion_run_id"),
            Listing.raw_data.label("raw_data"),
            func.ST_Y(Property.geom).label("latitude"), func.ST_X(Property.geom).label("longitude"),
            Property.district_id.label("district_id"), Property.distance_metro_m.label("distance_metro_m"),
            Property.distance_center_m.label("distance_center_m"),
            Property.distance_university_m.label("distance_university_m"),
            Property.coordinate_source.label("coordinate_source"),
            Property.coordinate_confidence.label("coordinate_confidence"),
            Property.geography_version.label("geography_version"),
        )
        .outerjoin(Property, Listing.property_id == Property.id)
        .filter(Listing.source == source, Listing.last_seen_at < cutoff)
        .order_by(Listing.last_seen_at, Listing.id)
    )
    return [dict(row._mapping) for row in statement.all()]


def _quarantine_event_count(session: Session, as_of: date, source: str) -> int:
    cutoff = datetime.combine(as_of + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return int(session.query(func.coalesce(func.sum(IngestionRun.listings_quarantined), 0))
               .filter(IngestionRun.source == source, IngestionRun.started_at < cutoff).scalar() or 0)


@click.command()
@click.option("--as-of", "as_of_text", required=True, help="Inclusive UTC snapshot date (YYYY-MM-DD).")
@click.option("--version", required=True, help="Immutable dataset version label, for example v1.0.0.")
@click.option("--output-dir", type=click.Path(path_type=Path), default=Path("data/processed"),
              show_default=True, help="Ignored output root; versioned artifacts are written beneath it.")
@click.option("--source", default=DEFAULT_SOURCE_NAME, show_default=True)
@click.option("--split-mode", type=click.Choice(SPLIT_MODES), default="chronological", show_default=True,
              help="'grouped-random' is a labeled NON-temporal fallback for one-date snapshots; "
                   "it needs explicit A/B owner agreement before being used as evidence.")
@click.option("--split-seed", default=DEFAULT_SPLIT_SEED, show_default=True,
              help="Seed string for --split-mode grouped-random (recorded in the manifest).")
@click.option("--merge-near-duplicates", is_flag=True,
              help="Merge groups whose rows share rounded coordinates, area and USD price so "
                   "near-duplicate listings cannot straddle splits (counts reported in quality_report.json).")
def cli(as_of_text: str, version: str, output_dir: Path, source: str,
        split_mode: str, split_seed: str, merge_near_duplicates: bool) -> None:
    """Export privacy-safe, group-isolated training/evaluation CSVs and quality metadata."""
    try:
        as_of = date.fromisoformat(as_of_text)
    except ValueError as error:
        raise click.BadParameter("Expected YYYY-MM-DD", param_hint="--as-of") from error
    if (not version or version in {".", ".."} or version.startswith(".")
            or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for char in version)):
        raise click.BadParameter("Use letters, digits, dot, underscore, or hyphen", param_hint="--version")

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    try:
        engine = create_engine(get_database_url(), pool_pre_ping=True)
    except RuntimeError as error:
        raise click.ClickException(str(error)) from error
    session = sessionmaker(bind=engine)()
    try:
        rows = _database_rows(session, as_of, source)
        quarantine_events = _quarantine_event_count(session, as_of, source)
    finally:
        session.close()
        engine.dispose()

    splits, quality = prepare_snapshot(rows, as_of, split_mode=split_mode, split_seed=split_seed,
                                       merge_near_duplicates=merge_near_duplicates)
    if split_mode == "grouped-random":
        click.echo("WARNING: grouped-random split is NOT temporal; results are not forward-looking.", err=True)
    quality["quarantined_record_events_reported_by_ingestion_runs"] = quarantine_events
    artifacts = create_artifacts(splits, quality, version, as_of, source=source)
    output_path = write_versioned_snapshot(output_dir, version, artifacts)
    manifest = json.loads(artifacts["manifest.json"])
    click.echo(f"Snapshot: {output_path}")
    click.echo(f"SHA-256: {manifest['snapshot_sha256']}")
    click.echo(f"Eligible rows: {quality['eligible_rows']} / {quality['input_rows_as_of']}")
    click.echo(f"Split rows: {quality['splits']['row_counts']}")


if __name__ == "__main__":
    cli()
