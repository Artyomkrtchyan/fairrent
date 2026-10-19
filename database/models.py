from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry  

Base = declarative_base()

class Property(Base):
    __tablename__ = "properties"
    
    id = Column(Integer, primary_key=True, index=True)
    # PostGIS Point for geospatial queries (WGS 84 / SRID 4326)
    geom = Column(Geometry(geometry_type='POINT', srid=4326), nullable=True)
    district = Column(String, index=True)
    address_raw = Column(String)
    created_at = Column(DateTime)

class Listing(Base):
    __tablename__ = "listings"
    
    id = Column(Integer, primary_key=True, index=True)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=True)
    external_id = Column(String, unique=True, index=True, nullable=False)
    source = Column(String, default="list.am")
    title = Column(String)
    price_usd = Column(Float)
    price_amd = Column(Float)
    area_sqm = Column(Float)
    rooms_count = Column(Integer)
    floor = Column(Integer)
    total_floors = Column(Integer)
    building_type = Column(String)
    description = Column(Text)
    raw_data = Column(JSON)
    created_at = Column(DateTime)
    
    property = relationship("Property", backref="listings")

class PriceObservation(Base):
    __tablename__ = "price_observations"
    
    id = Column(Integer, primary_key=True, index=True)
    listing_id = Column(Integer, ForeignKey("listings.id"), nullable=False)
    price_usd = Column(Float, nullable=False)
    price_amd = Column(Float, nullable=False)
    recorded_at = Column(DateTime, index=True)