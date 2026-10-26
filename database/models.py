from geoalchemy2 import Geometry
from sqlalchemy import (
    JSON, Boolean, CheckConstraint, Column, Date, DateTime, Float, ForeignKey, Index,
    Integer, Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class IngestionRun(Base):
    """One execution of the collection pipeline (or a file import)."""
    __tablename__ = "ingestion_runs"

    id = Column(Integer, primary_key=True)
    source = Column(String, nullable=False)
    # running | success | partial | failed
    status = Column(String, nullable=False, default="running", server_default="running")
    # True only for a crawl that reached the end of pagination with no index failures.
    is_complete = Column(Boolean, nullable=False, default=False, server_default="false")
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at = Column(DateTime(timezone=True))
    pages_requested = Column(Integer)
    pages_fetched = Column(Integer)
    listings_seen = Column(Integer, nullable=False, default=0, server_default="0")
    listings_saved = Column(Integer, nullable=False, default=0, server_default="0")
    listings_quarantined = Column(Integer, nullable=False, default=0, server_default="0")
    listings_deactivated = Column(Integer, nullable=False, default=0, server_default="0")
    params = Column(JSON)
    notes = Column(Text)

    __table_args__ = (
        CheckConstraint("status IN ('running', 'success', 'partial', 'failed')",
                        name="ck_ingestion_runs_status"),
        Index("ix_ingestion_runs_source_started", "source", "started_at"),
    )


class Property(Base):
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True, index=True)
    # PostGIS Point for geospatial queries (WGS 84 / SRID 4326)
    geom = Column(Geometry(geometry_type="POINT", srid=4326), nullable=True)
    district = Column(String, index=True)
    district_id = Column(String, index=True)
    district_source = Column(String)
    address_raw = Column(String)
    coordinate_source = Column(String)
    coordinate_confidence = Column(String, nullable=False, default="unknown", server_default="unknown")
    distance_metro_m = Column(Float)
    nearest_metro_id = Column(String)
    distance_university_m = Column(Float)
    nearest_university_id = Column(String)
    distance_center_m = Column(Float)
    geo_status = Column(String, nullable=False, default="unresolved", server_default="unresolved")
    geography_version = Column(String, nullable=False, default="yerevan-geo-v1",
                               server_default="yerevan-geo-v1")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("coordinate_confidence IN ('exact', 'approximate', 'unknown')",
                        name="ck_properties_coordinate_confidence"),
        CheckConstraint("geo_status IN ('resolved', 'unresolved')", name="ck_properties_geo_status"),
        CheckConstraint(
            "(distance_metro_m IS NULL OR distance_metro_m >= 0) AND "
            "(distance_university_m IS NULL OR distance_university_m >= 0) AND "
            "(distance_center_m IS NULL OR distance_center_m >= 0)",
            name="ck_properties_geographic_distances_nonnegative"),
    )


class GeographicReferencePoint(Base):
    """Versioned Metro, campus and center point with per-record provenance."""
    __tablename__ = "geographic_reference_points"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    kind = Column(String, nullable=False)
    geom = Column(Geometry(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False)
    coordinate_source = Column(String, nullable=False)
    coordinate_confidence = Column(String, nullable=False, default="approximate",
                                   server_default="approximate")
    source_url = Column(Text, nullable=False)
    geography_version = Column(String, nullable=False)

    __table_args__ = (
        CheckConstraint("kind IN ('metro', 'university', 'city_center')",
                        name="ck_geographic_reference_points_kind"),
        CheckConstraint("coordinate_confidence IN ('exact', 'approximate', 'unknown')",
                        name="ck_geographic_reference_points_confidence"),
        Index("ix_geographic_reference_points_geom", "geom", postgresql_using="gist"),
    )


class Listing(Base):
    __tablename__ = "listings"

    id = Column(Integer, primary_key=True, index=True)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=True, index=True)

    # Source identity: the same external_id may exist in different sources.
    source = Column(String, nullable=False, default="list.am", server_default="list.am")
    external_id = Column(String, nullable=False, index=True)
    url = Column(Text)

    title = Column(String)
    # Normalized MONTHLY amounts.
    price_usd = Column(Float)
    price_amd = Column(Float)
    # Provenance of the conversion; NULL means unknown, never 0.
    original_price = Column(Float)
    original_currency = Column(String(3))
    original_period = Column(String)
    exchange_rate = Column(Float)          # units of original currency per 1 USD
    exchange_rate_at = Column(DateTime(timezone=True))   # when the conversion was performed
    rate_source = Column(String)           # where the rate comes from (e.g. "static-config")
    rate_date = Column(Date)               # effective date of the rate (not the processing time)
    utilities_included = Column(Boolean)   # NULL = unknown

    # Optional attributes: NULL means "unknown", 0 is a real zero.
    area_sqm = Column(Float)
    rooms_count = Column(Integer)
    floor = Column(Integer)
    total_floors = Column(Integer)
    building_type = Column(String)
    description = Column(Text)
    raw_data = Column(JSON)

    # Lifecycle
    first_seen_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_run_id = Column(Integer, ForeignKey("ingestion_runs.id", ondelete="SET NULL",
                                                  name="fk_listings_last_seen_run_id"))
    consecutive_misses = Column(Integer, nullable=False, default=0, server_default="0")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    deactivated_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    property = relationship("Property", backref="listings")

    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_listings_source_external_id"),
        Index("ix_listings_source_active", "source", "is_active"),
        CheckConstraint("consecutive_misses >= 0", name="ck_listings_consecutive_misses_nonneg"),
        CheckConstraint("original_price IS NULL OR original_price > 0",
                        name="ck_listings_original_price_positive"),
        CheckConstraint("exchange_rate IS NULL OR exchange_rate > 0",
                        name="ck_listings_exchange_rate_positive"),
    )


class PriceObservation(Base):
    __tablename__ = "price_observations"

    id = Column(Integer, primary_key=True, index=True)
    listing_id = Column(Integer, ForeignKey("listings.id"), nullable=False)
    run_id = Column(Integer, ForeignKey("ingestion_runs.id", ondelete="SET NULL",
                                        name="fk_price_observations_run_id"))
    price_usd = Column(Float, nullable=False)
    price_amd = Column(Float, nullable=False)
    original_price = Column(Float)
    original_currency = Column(String(3))
    original_period = Column(String)
    exchange_rate = Column(Float)
    exchange_rate_at = Column(DateTime(timezone=True))
    rate_source = Column(String)
    rate_date = Column(Date)
    utilities_included = Column(Boolean)
    recorded_at = Column(DateTime(timezone=True), nullable=False, index=True,
                         server_default=func.now())

    __table_args__ = (
        Index("ix_price_observations_listing_recorded", "listing_id", "recorded_at"),
        CheckConstraint("original_price IS NULL OR original_price > 0",
                        name="ck_price_observations_original_price_positive"),
    )


class WeeklyNeighborhoodPriceIndex(Base):
    """Published weekly medians of active rental asking prices by district."""
    __tablename__ = "weekly_neighborhood_price_indexes"

    source = Column(String, primary_key=True)
    district_id = Column(String, primary_key=True)
    period_start = Column(Date, primary_key=True)
    period_end = Column(Date, nullable=False)
    median_price_usd_month = Column(Numeric(12, 2))
    median_price_usd_per_sqm = Column(Numeric(12, 2))
    sample_count = Column(Integer, nullable=False)
    per_sqm_sample_count = Column(Integer, nullable=False)
    minimum_sample_count = Column(Integer, nullable=False, default=5, server_default="5")
    price_status = Column(String, nullable=False)
    per_sqm_status = Column(String, nullable=False)
    data_as_of = Column(DateTime(timezone=True), nullable=False)
    generated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    price_basis = Column(String, nullable=False, default="asking", server_default="asking")

    __table_args__ = (
        CheckConstraint("length(source) > 0", name="ck_weekly_neighborhood_source_nonempty"),
        CheckConstraint("EXTRACT(ISODOW FROM period_start) = 1",
                        name="ck_weekly_neighborhood_monday_start"),
        CheckConstraint("period_end = period_start + 6", name="ck_weekly_neighborhood_period"),
        CheckConstraint("sample_count >= 0 AND per_sqm_sample_count >= 0 AND "
                        "per_sqm_sample_count <= sample_count AND minimum_sample_count > 0",
                        name="ck_weekly_neighborhood_sample_counts"),
        CheckConstraint("median_price_usd_month IS NULL OR median_price_usd_month > 0",
                        name="ck_weekly_neighborhood_median_price_positive"),
        CheckConstraint("median_price_usd_per_sqm IS NULL OR median_price_usd_per_sqm > 0",
                        name="ck_weekly_neighborhood_median_unit_price_positive"),
        CheckConstraint("price_status IN ('available', 'insufficient_data')",
                        name="ck_weekly_neighborhood_price_status"),
        CheckConstraint("per_sqm_status IN ('available', 'insufficient_data')",
                        name="ck_weekly_neighborhood_per_sqm_status"),
        CheckConstraint(
            "(price_status = 'available' AND sample_count >= minimum_sample_count "
            "AND median_price_usd_month IS NOT NULL) OR "
            "(price_status = 'insufficient_data' AND sample_count < minimum_sample_count "
            "AND median_price_usd_month IS NULL)",
            name="ck_weekly_neighborhood_price_sparse_policy"),
        CheckConstraint(
            "(per_sqm_status = 'available' AND per_sqm_sample_count >= minimum_sample_count "
            "AND median_price_usd_per_sqm IS NOT NULL) OR "
            "(per_sqm_status = 'insufficient_data' AND per_sqm_sample_count < minimum_sample_count "
            "AND median_price_usd_per_sqm IS NULL)",
            name="ck_weekly_neighborhood_per_sqm_sparse_policy"),
        CheckConstraint("price_basis = 'asking'", name="ck_weekly_neighborhood_price_basis"),
        Index("ix_weekly_neighborhood_period", "source", "district_id", "period_start"),
    )
