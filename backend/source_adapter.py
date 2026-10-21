"""Map the accepted A02/A04 storage schema to C01 without changing source tables."""
import math
from datetime import timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from uuid import UUID, uuid5

try:
    from .listing_models import ListingData
except ImportError:
    from listing_models import ListingData

# Permanent public identity namespace. Never change it when migrating storage IDs.
PUBLIC_NAMESPACE = UUID("1cd63f77-92ca-45ba-b4d5-39a8ce7086a8")
# Only mappings already represented by C01 fixtures. A05 will supply the full registry.
DISTRICTS = {"kentron": "kentron", "arabkir": "arabkir"}
PERIODS = {"month": Decimal(1), "monthly": Decimal(1), "day": Decimal(30),
           "daily": Decimal(30), "week": Decimal("4.33"), "weekly": Decimal("4.33"),
           "year": Decimal(1), "yearly": Decimal(1), "annual": Decimal(1)}


class Unpublishable(ValueError):
    """A source record lacks required evidence; the message is a safe reason code."""


def listing_uuid(source, external_id):
    return uuid5(PUBLIC_NAMESPACE, f"listing:{source}:{external_id}")


def text(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if value and value.lower() != "unknown" else None


def positive(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() and result > 0 else None


def optional_number(value, *, integer=False, zero=False):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if isinstance(value, bool) or not math.isfinite(number) or number < 0 or (number == 0 and not zero):
        return None
    if integer:
        return int(number) if number.is_integer() else None
    return number


def utc(value):
    if value is None or value.tzinfo is None:
        raise Unpublishable("missing_observation_time")
    return value.astimezone(timezone.utc)


def adapt_source(row) -> ListingData:
    raw = row.get("raw_data") or {}
    if not isinstance(raw, dict):
        raw = {}
    if row["source"] != "list.am":
        raise Unpublishable("unsupported_source")
    # Old migration defaults are not proof of a source observation.
    if row.get("last_seen_run_id") is None:
        raise Unpublishable("unobserved_legacy_record")
    amount = positive(row.get("original_price"))
    currency = row.get("original_currency")
    period = text(row.get("original_period"))
    if amount is None or currency not in {"USD", "AMD", "EUR", "RUB"}:
        raise Unpublishable("missing_original_price")
    if period is None or period.lower() not in PERIODS:
        raise Unpublishable("unsupported_period")
    first_seen, last_seen = utc(row.get("first_seen_at")), utc(row.get("last_seen_at"))
    with localcontext() as context:
        context.prec = 40
        monthly = amount / 12 if period.lower() in {"year", "yearly", "annual"} else amount * PERIODS[period.lower()]
        conversion = None
        normalized = None
        if currency == "USD":
            conversion = {"rate_to_usd": 1, "rate_date": last_seen.date(), "rate_source": "identity"}
            normalized = monthly
        else:
            rate = positive(row.get("exchange_rate"))
            provider = text(row.get("rate_source"))
            effective = row.get("rate_date")
            if rate is not None and provider is not None and effective is not None and effective <= last_seen.date():
                conversion = {"rate_to_usd": float(Decimal(1) / rate),
                              "rate_date": effective, "rate_source": provider}
                normalized = monthly / rate
        if normalized is not None:
            normalized = float(normalized.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            if normalized <= 0:
                raise Unpublishable("normalized_price_below_precision")

    latitude, longitude = row.get("latitude"), row.get("longitude")
    if latitude is None or longitude is None:
        latitude = longitude = None
    district = text(raw.get("district")) or text(row.get("district"))
    building = text(row.get("building_type"))
    floor = optional_number(row.get("floor"), integer=True, zero=True)
    total_floors = optional_number(row.get("total_floors"), integer=True)
    if floor is not None and total_floors is not None and floor > total_floors:
        floor = total_floors = None
    return ListingData(
        id=listing_uuid(row["source"], row["external_id"]), source=row["source"],
        external_id=row["external_id"], source_url=row.get("url"),
        property_id=uuid5(PUBLIC_NAMESPACE, f"property:{row['property_id']}") if row.get("property_id") else None,
        title=text(row.get("title")), description=text(row.get("description")),
        address=text(raw.get("address_raw")) or text(row.get("address_raw")),
        district_id=DISTRICTS.get(district.lower()) if district else None,
        latitude=latitude, longitude=longitude,
        coordinate_confidence="approximate" if latitude is not None else "unknown",
        price_original=float(monthly), currency_original=currency,
        price_monthly_normalized=normalized, currency_normalized="USD", conversion=conversion,
        utilities_included=row.get("utilities_included"),
        rooms=optional_number(row.get("rooms_count"), integer=True), floor=floor,
        total_floors=total_floors, area_sqm=optional_number(row.get("area_sqm")),
        published_at=None, first_seen_at=first_seen, last_seen_at=last_seen,
        status="active" if row["is_active"] else "inactive", dedup_group_id=None,
        renovation=None, building_type=building if building in {"monolith", "stone", "panel"} else None,
        building_type_raw=building, thumbnail_url=None,
    )
