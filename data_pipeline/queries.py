from sqlalchemy.orm import Query, Session
from database.models import Listing, Property


def map_listings(session: Session) -> Query:
    return (session.query(Listing)
            .join(Property, Listing.property_id == Property.id)
            .filter(Property.geom.is_not(None)))