"""Record coordinate and district provenance for A05.

Revision ID: a05_geo_20261022
Revises: 5b7d2e91c4a6
Create Date: 2026-10-22
"""
from typing import Sequence, Union

from alembic import op
from geoalchemy2 import Geometry
import sqlalchemy as sa

revision: str = "a05_geo_20261022"
down_revision: Union[str, Sequence[str], None] = "5b7d2e91c4a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("properties", sa.Column("district_id", sa.String(), nullable=True))
    op.add_column("properties", sa.Column("district_source", sa.String(), nullable=True))
    op.add_column("properties", sa.Column("coordinate_source", sa.String(), nullable=True))
    op.add_column("properties", sa.Column(
        "coordinate_confidence", sa.String(), nullable=False, server_default="unknown"))
    op.add_column("properties", sa.Column("distance_metro_m", sa.Float(), nullable=True))
    op.add_column("properties", sa.Column("nearest_metro_id", sa.String(), nullable=True))
    op.add_column("properties", sa.Column("distance_university_m", sa.Float(), nullable=True))
    op.add_column("properties", sa.Column("nearest_university_id", sa.String(), nullable=True))
    op.add_column("properties", sa.Column("distance_center_m", sa.Float(), nullable=True))
    op.add_column("properties", sa.Column(
        "geo_status", sa.String(), nullable=False, server_default="unresolved"))
    op.add_column("properties", sa.Column(
        "geography_version", sa.String(), nullable=False, server_default="yerevan-geo-v1"))
    op.create_index("ix_properties_district_id", "properties", ["district_id"])
    # Existing list.am pins are described by the ingestion policy as coarse/approximate;
    # retain that provenance limitation rather than calling them exact address coordinates.
    op.execute("""
        UPDATE properties
        SET coordinate_source = 'list.am:legacy-coordinate-provenance-unrecorded',
            coordinate_confidence = 'approximate'
        WHERE geom IS NOT NULL
    """)
    op.execute("UPDATE properties SET district_source = 'list.am' WHERE district IS NOT NULL")
    op.create_check_constraint(
        "ck_properties_coordinate_confidence", "properties",
        "coordinate_confidence IN ('exact', 'approximate', 'unknown')")
    op.create_check_constraint(
        "ck_properties_geo_status", "properties", "geo_status IN ('resolved', 'unresolved')")
    op.create_check_constraint(
        "ck_properties_geographic_distances_nonnegative", "properties",
        "(distance_metro_m IS NULL OR distance_metro_m >= 0) AND "
        "(distance_university_m IS NULL OR distance_university_m >= 0) AND "
        "(distance_center_m IS NULL OR distance_center_m >= 0)")
    op.create_table(
        "geographic_reference_points",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("geom", Geometry(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column("coordinate_source", sa.String(), nullable=False),
        sa.Column("coordinate_confidence", sa.String(), nullable=False, server_default="approximate"),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("geography_version", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("kind IN ('metro', 'university', 'city_center')",
                           name="ck_geographic_reference_points_kind"),
        sa.CheckConstraint("coordinate_confidence IN ('exact', 'approximate', 'unknown')",
                           name="ck_geographic_reference_points_confidence"),
    )
    op.create_index("ix_geographic_reference_points_geom", "geographic_reference_points", ["geom"],
                    postgresql_using="gist")
    op.execute("""
        CREATE VIEW property_geographic_features AS
        SELECT id AS property_id, district, district_id,
               CASE WHEN district_id IS NULL THEN 'unresolved' ELSE 'resolved' END AS district_status,
               district_source,
               ST_Y(geom) AS latitude, ST_X(geom) AS longitude,
               coordinate_source, coordinate_confidence,
               distance_metro_m, nearest_metro_id,
               distance_university_m, nearest_university_id,
               distance_center_m, geo_status, geography_version
        FROM properties
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS property_geographic_features")
    op.drop_index("ix_geographic_reference_points_geom", table_name="geographic_reference_points")
    op.drop_table("geographic_reference_points")
    op.drop_constraint("ck_properties_geographic_distances_nonnegative", "properties", type_="check")
    op.drop_constraint("ck_properties_geo_status", "properties", type_="check")
    op.drop_constraint("ck_properties_coordinate_confidence", "properties", type_="check")
    op.drop_index("ix_properties_district_id", table_name="properties")
    op.drop_column("properties", "geography_version")
    op.drop_column("properties", "geo_status")
    op.drop_column("properties", "distance_center_m")
    op.drop_column("properties", "nearest_university_id")
    op.drop_column("properties", "distance_university_m")
    op.drop_column("properties", "nearest_metro_id")
    op.drop_column("properties", "distance_metro_m")
    op.drop_column("properties", "coordinate_confidence")
    op.drop_column("properties", "coordinate_source")
    op.drop_column("properties", "district_source")
    op.drop_column("properties", "district_id")
