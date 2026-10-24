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


def prepare_snapshot(raw_rows: Iterable[dict], as_of: date) -> tuple[dict[str, list[dict]], dict]:
    """Validate rows, enforce group-isolated chronological splits, and build a quality report."""
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

    group_members = defaultdict(list)
    for row in valid:
        group_members[row["dedup_group_id"]].append(row)
    anchors = sorted((min(r["_anchor_date"] for r in members), group_id)
                     for group_id, members in group_members.items())
    group_count = len(anchors)
    if group_count >= 3:
        train_count = max(1, math.floor(group_count * SPLIT_RATIOS["train"]))
        validation_count = max(1, math.floor(group_count * SPLIT_RATIOS["validation"]))
        if train_count + validation_count >= group_count:
            train_count, validation_count = group_count - 2, 1
    elif group_count == 2:
        train_count, validation_count = 1, 0
    elif group_count == 1:
        train_count, validation_count = 1, 0
    else:
        train_count, validation_count = 0, 0

    group_split = {}
    for index, (_, group_id) in enumerate(anchors):
        if index < train_count:
            group_split[group_id] = "train"
        elif index < train_count + validation_count:
            group_split[group_id] = "validation"
        else:
            group_split[group_id] = "test"

    split_groups: dict[str, list[dict]] = {"train": [], "validation": [], "test": []}
    split_excluded = Counter()
    split_ends = {}
    train_end = anchors[train_count - 1][0] if train_count else None
    val_end_index = train_count + validation_count - 1
    validation_end = anchors[val_end_index][0] if val_end_index >= 0 else None
    split_ends["train"] = train_end
    split_ends["validation"] = validation_end
    split_ends["test"] = as_of

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
            "test_end_date": as_of.isoformat(),
        },
    }
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
    manifest = {
        "dataset_schema_version": DATASET_SCHEMA_VERSION,
        "dataset_version": version,
        "contract_version": CONTRACT_VERSION,
        "as_of_date": as_of.isoformat(),
        "source": source,
        "observation_policy": "one latest listing state per source listing, observed at last_seen_at <= as_of; price is monthly asking USD",
        "historical_limit": "Price history stores changes, not a full feature snapshot per observation. This export does not treat old price changes as independent rows with current features.",
        "split_policy": {
            "method": "chronological by earliest observation_date per dedup group; all group members stay in one split",
            "ratios": SPLIT_RATIOS,
            "future_row_policy": "exclude rows observed after their assigned split end date",
        },
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
def cli(as_of_text: str, version: str, output_dir: Path, source: str) -> None:
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

    splits, quality = prepare_snapshot(rows, as_of)
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
