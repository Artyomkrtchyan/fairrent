"""Build weekly, deduplicated neighborhood asking-price aggregates."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from statistics import median
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import click
from sqlalchemy.orm import Session

from database.models import Listing, Property, WeeklyNeighborhoodPriceIndex
from .config import DEFAULT_SOURCE_NAME, get_database_url
from .geography import DISTRICTS
from .normalizer import monthly_multiplier

MINIMUM_SAMPLE_COUNT = 5
FRESHNESS_MAX_AGE_DAYS = 14
CENT = Decimal("0.01")
REPORTING_TIMEZONE = ZoneInfo("Asia/Yerevan")


def week_window(week_start: date) -> tuple[datetime, datetime, date]:
    """Return UTC bounds for a Monday-Sunday reporting week in Yerevan time."""
    if week_start.weekday() != 0:
        raise ValueError("week_start must be a Monday")
    local_start = datetime.combine(week_start, time.min, tzinfo=REPORTING_TIMEZONE)
    local_next_start = datetime.combine(week_start + timedelta(days=7), time.min,
                                        tzinfo=REPORTING_TIMEZONE)
    start = local_start.astimezone(timezone.utc)
    next_start = local_next_start.astimezone(timezone.utc)
    return start, next_start, week_start + timedelta(days=6)


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return result if result.is_finite() else None


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _supported_long_term_period(value: Any) -> bool:
    period = str(value or "").strip().lower()
    if not period or any(token in period for token in ("day", "daily", "օրական", "week", "weekly", "շաբաթական")):
        return False
    try:
        monthly_multiplier(period)
    except ValueError:
        return False
    return True


def _rounded(value: Decimal | None) -> Decimal | None:
    return value.quantize(CENT, rounding=ROUND_HALF_UP) if value is not None else None


def build_weekly_aggregates(
    rows: Iterable[dict],
    week_start: date,
    *,
    generated_at: datetime | None = None,
    minimum_sample_count: int = MINIMUM_SAMPLE_COUNT,
    source: str = DEFAULT_SOURCE_NAME,
) -> list[dict]:
    """Calculate district medians, counting each deduplicated property once.

    A listing must be active, observed during the Yerevan reporting week, have a known Yerevan
    district, a supported long-term period and a positive normalized USD/month price.
    Of eligible ads linked to one property, only the most recently observed one is used.
    """
    if minimum_sample_count < 1:
        raise ValueError("minimum_sample_count must be positive")
    start, next_start, period_end = week_window(week_start)
    generated_at = _utc(generated_at or datetime.now(timezone.utc))
    assert generated_at is not None
    latest_by_property: dict[tuple[str, int], tuple[datetime, int, Decimal, Decimal | None]] = {}

    for row in rows:
        if row.get("is_active") is not True or row.get("source", source) != source:
            continue
        district_id = row.get("district_id")
        if district_id not in DISTRICTS:
            continue
        property_id = row.get("property_id")
        if property_id is None:
            continue
        observed_at = _utc(row.get("last_seen_at"))
        if observed_at is None or not start <= observed_at < next_start:
            continue
        if not _supported_long_term_period(row.get("original_period")):
            continue
        price = _decimal(row.get("price_usd"))
        if price is None or price <= 0:
            continue

        area = _decimal(row.get("area_sqm"))
        unit_price = price / area if area is not None and area > 0 else None
        try:
            listing_id = int(row.get("listing_id", row.get("id", -1)))
        except (TypeError, ValueError):
            listing_id = -1
        key = (district_id, int(property_id))
        candidate = (observed_at, listing_id, price, unit_price)
        previous = latest_by_property.get(key)
        if previous is None or candidate[:2] > previous[:2]:
            latest_by_property[key] = candidate

    by_district: dict[str, dict[str, list]] = defaultdict(
        lambda: {"monthly_prices": [], "unit_prices": [], "last_seen": []}
    )
    for (district_id, _property_id), (observed_at, _listing_id, price, unit_price) in latest_by_property.items():
        district = by_district[district_id]
        district["monthly_prices"].append(price)
        district["last_seen"].append(observed_at)
        if unit_price is not None:
            district["unit_prices"].append(unit_price)

    results = []
    for district_id, values in sorted(by_district.items()):
        sample_count = len(values["monthly_prices"])
        unit_count = len(values["unit_prices"])
        price_status = "available" if sample_count >= minimum_sample_count else "insufficient_data"
        per_sqm_status = "available" if unit_count >= minimum_sample_count else "insufficient_data"
        results.append({
            "source": source,
            "district_id": district_id,
            "period_start": week_start,
            "period_end": period_end,
            "median_price_usd_month": (
                _rounded(median(values["monthly_prices"]))
                if price_status == "available" else None
            ),
            "median_price_usd_per_sqm": (
                _rounded(median(values["unit_prices"]))
                if per_sqm_status == "available" else None
            ),
            "sample_count": sample_count,
            "per_sqm_sample_count": unit_count,
            "minimum_sample_count": minimum_sample_count,
            "price_status": price_status,
            "per_sqm_status": per_sqm_status,
            "data_as_of": max(values["last_seen"]),
            "generated_at": generated_at,
            "price_basis": "asking",
        })
    return results


def _source_rows(session: Session, week_start: date, source: str) -> list[dict]:
    start, next_start, _ = week_window(week_start)
    rows = session.query(
        Listing.id.label("listing_id"), Listing.property_id.label("property_id"),
        Property.district_id.label("district_id"),
        Listing.price_usd.label("price_usd"), Listing.area_sqm.label("area_sqm"),
        Listing.original_period.label("original_period"), Listing.last_seen_at.label("last_seen_at"),
        Listing.is_active.label("is_active"), Listing.source.label("source"),
    ).join(Property, Listing.property_id == Property.id).filter(
        Listing.source == source,
        Listing.is_active.is_(True),
        Listing.last_seen_at >= start,
        Listing.last_seen_at < next_start,
        Listing.property_id.is_not(None),
        Property.district_id.is_not(None),
    ).order_by(Listing.id).all()
    return [dict(row._mapping) for row in rows]


def publish_week(session: Session, week_start: date, source: str = DEFAULT_SOURCE_NAME) -> list[dict]:
    """Atomically replace one week's aggregates without changing source tables."""
    rows = _source_rows(session, week_start, source)
    aggregates = build_weekly_aggregates(rows, week_start, source=source)
    if not aggregates:
        raise ValueError("No eligible active long-term listings for this source and week; existing aggregates preserved")
    session.query(WeeklyNeighborhoodPriceIndex).filter(
        WeeklyNeighborhoodPriceIndex.period_start == week_start,
        WeeklyNeighborhoodPriceIndex.source == source,
    ).delete(synchronize_session=False)
    session.add_all(WeeklyNeighborhoodPriceIndex(**aggregate) for aggregate in aggregates)
    session.flush()
    return aggregates


@click.command()
@click.option("--week-start", required=True, help="Monday that starts the Asia/Yerevan reporting week (YYYY-MM-DD).")
@click.option("--source", default=DEFAULT_SOURCE_NAME, show_default=True)
def cli(week_start: str, source: str) -> None:
    """Build the weekly neighborhood asking-price index for observed active listings."""
    try:
        start = date.fromisoformat(week_start)
        week_window(start)
    except ValueError as error:
        raise click.BadParameter("Expected a Monday in YYYY-MM-DD format", param_hint="--week-start") from error

    from sqlalchemy import create_engine

    engine = create_engine(get_database_url(), pool_pre_ping=True)
    try:
        try:
            with Session(engine) as session:
                with session.begin():
                    aggregates = publish_week(session, start, source)
        except ValueError as error:
            raise click.ClickException(str(error)) from error
        click.echo(json.dumps({
            "period_start": start.isoformat(),
            "period_end": (start + timedelta(days=6)).isoformat(),
            "districts_published": len(aggregates),
            "sampled_properties": sum(row["sample_count"] for row in aggregates),
        }, sort_keys=True))
    finally:
        engine.dispose()


if __name__ == "__main__":
    cli()
