import json

from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session
from geoalchemy2.elements import WKTElement

from database.models import GeographicReferencePoint, Property
from .config import get_database_url
from .geography import (GEOGRAPHY_VERSION, normalize_district, proximity_features,
                        reference_points)


def enrich_all(session: Session) -> dict:
    for point in reference_points():
        session.merge(GeographicReferencePoint(
            id=point["id"], name=point["name"], kind=point["kind"],
            geom=WKTElement(f"POINT({point['longitude']} {point['latitude']})", srid=4326),
            coordinate_source=point["coordinate_source"],
            coordinate_confidence=point["coordinate_confidence"],
            source_url=point["source_url"], geography_version=point["geography_version"],
        ))
    session.query(GeographicReferencePoint).filter(
        GeographicReferencePoint.geography_version != GEOGRAPHY_VERSION
    ).delete(synchronize_session=False)
    updated = resolved = unresolved = 0
    rows = session.query(Property, func.ST_Y(Property.geom), func.ST_X(Property.geom)).yield_per(500)
    for prop, latitude, longitude in rows:
        prop.district_id = normalize_district(prop.district)
        features = proximity_features(latitude, longitude)
        for field, value in features.items():
            setattr(prop, field, value)
        if features["geo_status"] == "resolved":
            resolved += 1
        else:
            unresolved += 1
            prop.coordinate_source = None
            prop.coordinate_confidence = "unknown"
        updated += 1
    session.commit()
    return {"updated": updated, "resolved": resolved, "unresolved": unresolved,
            "geography_version": GEOGRAPHY_VERSION}


def main() -> None:
    engine = create_engine(get_database_url(), pool_pre_ping=True)
    try:
        with Session(engine) as session:
            print(json.dumps(enrich_all(session), sort_keys=True))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
