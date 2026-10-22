from datetime import date, datetime, timezone
from typing import Optional
from geoalchemy2 import Geography
from geoalchemy2.elements import WKTElement
from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session
from database.models import Listing, PriceObservation, Property
from .config import DEFAULT_SOURCE_NAME
from .grouping import GROUP_RADIUS_M, find_matching_property
from .geography import normalize_district, proximity_features

# Optional attributes: a known value is never overwritten by "unknown" (None).
_OPTIONAL_FIELDS = ("url", "title", "area_sqm", "rooms_count", "floor", "total_floors",
                    "building_type", "description")

COORD_EPSILON_M = 1.0


def _has_coords(data: dict) -> bool:
    return data.get("lat") is not None and data.get("lon") is not None

def _geom(data: dict) -> Optional[WKTElement]:
    if not _has_coords(data):
        return None
    return WKTElement(f"POINT({data['lon']} {data['lat']})", srid=4326)


def _geo_fields(data: dict) -> dict:
    features = proximity_features(data.get("lat"), data.get("lon"))
    return {
        **features,
        "district_id": normalize_district(data.get("district")),
        "district_source": data.get("district_source") or
                           ((data.get("source") or DEFAULT_SOURCE_NAME) if data.get("district") else None),
        "coordinate_source": data.get("coordinate_source") if _has_coords(data) else None,
        "coordinate_confidence": (data.get("coordinate_confidence") or "unknown")
                                  if _has_coords(data) else "unknown",
    }

def _new_property(session: Session, data: dict, now: datetime) -> Property:
    # geom stays NULL when the source gave no coordinates: the listing is still stored and
    # searchable, it is just excluded from map results (see queries.map_listings).
    prop = Property(geom=_geom(data), district=data.get("district"),
                    address_raw=data.get("address_raw"), created_at=now, **_geo_fields(data))
    session.add(prop)
    session.flush()
    return prop


def _reassess_property(session: Session, listing: Listing, prop: Property, data: dict,
                       source: str, now: datetime) -> Property:
    others = session.query(Listing).filter(
        Listing.property_id == prop.id, Listing.id != listing.id).count()
    new_point = func.ST_SetSRID(func.ST_MakePoint(data["lon"], data["lat"]), 4326)
    distance = session.scalar(
        select(func.ST_Distance(cast(Property.geom, Geography), cast(new_point, Geography)))
        .where(Property.id == prop.id))          # NULL when the property has no position yet

    if distance is not None and distance <= (GROUP_RADIUS_M if others else COORD_EPSILON_M):
        if prop.coordinate_confidence == "unknown" and data.get("coordinate_confidence"):
            prop.coordinate_confidence = data["coordinate_confidence"]
            prop.coordinate_source = data.get("coordinate_source")
        if prop.district is None and data.get("district"):
            prop.district = data["district"]
            prop.district_id = normalize_district(data["district"])
            prop.district_source = data.get("district_source") or source
        return prop                              # same place (or noise): nothing to do

    matched = find_matching_property(session, data, source)
    if matched is not None and matched.id != prop.id:
        return matched                           # the corrected position belongs to a known flat

    if others == 0:
        prop.geom = _geom(data)                  # exclusive property: move it in place
        for key, value in _geo_fields(data).items():
            setattr(prop, key, value)
        if data.get("district") is not None:
            prop.district = data["district"]
        if data.get("address_raw") is not None:
            prop.address_raw = data["address_raw"]
        session.flush()
        return prop
    return _new_property(session, data, now)     # shared property stays where it is; only this
                                                 # listing gets a property at the corrected spot


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
    if listing is None or listing.property_id is None:
        prop = find_matching_property(session, data, source) or _new_property(session, data, now)
    else:
        prop = session.get(Property, listing.property_id)
        if _has_coords(data):          # coordinates unknown now: keep what we already know
            prop = _reassess_property(session, listing, prop, data, source, now)
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
        "rate_source": normalized.get("rate_source"),
        "rate_date": date.fromisoformat(normalized["rate_date"]) if normalized.get("rate_date") else None,
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
