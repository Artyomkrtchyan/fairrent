from typing import Optional
from geoalchemy2 import Geography
from sqlalchemy import cast, func, or_
from sqlalchemy.orm import Session
from database.models import Listing, Property
 
GROUP_RADIUS_M = 15.0
AREA_TOLERANCE_SQM = 0.5
_PREFILTER_DEGREES = 0.0005  # ~55 m; lets PostGIS use the GiST index before the exact check
 
 
def find_matching_property(session: Session, data: dict, source: str) -> Optional[Property]:
    if data.get("lat") is None or data.get("lon") is None:
        return None  # no position -> cannot be grouped by location
    area, rooms, floor = data.get("area_sqm"), data.get("rooms_count"), data.get("floor")
    if area is None or rooms is None or floor is None:
        return None
 
    point = func.ST_SetSRID(func.ST_MakePoint(data["lon"], data["lat"]), 4326)
    query = (
        session.query(Property)
        .join(Listing, Listing.property_id == Property.id)
        .filter(
            Listing.source == source,
            Listing.external_id != data["id"],
            Listing.rooms_count == rooms,
            Listing.floor == floor,
            Listing.area_sqm.between(area - AREA_TOLERANCE_SQM, area + AREA_TOLERANCE_SQM),
            func.ST_DWithin(Property.geom, point, _PREFILTER_DEGREES),
            func.ST_DWithin(cast(Property.geom, Geography), cast(point, Geography), GROUP_RADIUS_M),
        )
    )
    total_floors = data.get("total_floors")
    if total_floors is not None:
        query = query.filter(or_(Listing.total_floors.is_(None), Listing.total_floors == total_floors))
    return query.order_by(Property.id).first()
 