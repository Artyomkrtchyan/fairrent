from datetime import datetime, timezone
from typing import Optional
from geoalchemy2.elements import WKTElement
from sqlalchemy.orm import Session
from database.models import Listing, PriceObservation, Property
from .config import DEFAULT_SOURCE_NAME
from .grouping import find_matching_property

_OPTIONAL_FIELDS = ("url", "title", "area_sqm", "rooms_count", "floor", "total_floors",
                    "building_type", "description")


def process_scraped_item(session: Session, data: dict, normalized: dict,
                         run_id: Optional[int] = None, now: Optional[datetime] = None) -> str:
    source = data.get("source") or DEFAULT_SOURCE_NAME
    external_id = data["id"]
    now = now or datetime.now(timezone.utc)

    listing = (
        session.query(Listing)
        .filter(Listing.source == source, Listing.external_id == external_id)
        .first()
    )

    # 1. Property (spatial identity)
    if listing is not None and listing.property_id is not None:
        property_id = listing.property_id
    else:
        matched = find_matching_property(session, data, source)
        if matched is not None:
            property_id = matched.id
        else:
            prop = Property(
                geom=WKTElement(f"POINT({data['lon']} {data['lat']})", srid=4326),
                district=data.get("district"),
                address_raw=data.get("address_raw"),
                created_at=now,
            )
            session.add(prop)
            session.flush()
            property_id = prop.id

    # 2. Listing upsert
    provenance = {
        "price_usd": normalized["monthly_usd"],
        "price_amd": normalized["monthly_amd"],
        "original_price": normalized["original_price"],
        "original_currency": normalized["original_currency"],
        "original_period": normalized["original_period"],
        "exchange_rate": normalized["exchange_rate_used"],
        "exchange_rate_at": datetime.fromisoformat(normalized["conversion_timestamp"]),
        "utilities_included": normalized.get("utilities_included"),
    }

    if listing is None:
        action = "created"
        listing = Listing(
            property_id=property_id, source=source, external_id=external_id,
            first_seen_at=now, created_at=now, **provenance,
            **{f: data.get(f) for f in _OPTIONAL_FIELDS},
        )
        session.add(listing)
    else:
        action = "updated"
        listing.property_id = property_id
        for key, value in provenance.items():
            setattr(listing, key, value)
        for field in _OPTIONAL_FIELDS:
            if data.get(field) is not None:
                setattr(listing, field, data[field])

    listing.raw_data = data
    listing.last_seen_at = now
    listing.last_seen_run_id = run_id
    listing.consecutive_misses = 0
    if not listing.is_active:
        listing.is_active = True
        listing.deactivated_at = None

    session.flush()

    # 3. Price history: only when price or its provenance changed
    latest = (
        session.query(PriceObservation)
        .filter(PriceObservation.listing_id == listing.id)
        .order_by(PriceObservation.recorded_at.desc(), PriceObservation.id.desc())
        .first()
    )
    keys = ("price_usd", "price_amd", "original_price", "original_currency", "original_period")
    if latest is None or any(getattr(latest, k) != provenance[k] for k in keys):
        session.add(PriceObservation(listing_id=listing.id, run_id=run_id, recorded_at=now, **provenance))

    session.commit()
    return action
