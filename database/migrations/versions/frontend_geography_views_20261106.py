from typing import Sequence, Union
from alembic import op


revision: str = "frontend_geography_views_20261106"
down_revision: Union[str, Sequence[str], None] = "a07_neighborhood_price_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute("""
        CREATE VIEW metro_stations AS
        SELECT id AS station_id,
               name,
               ST_Y(geom) AS latitude,
               ST_X(geom) AS longitude,
               coordinate_source,
               coordinate_confidence,
               source_url,
               geography_version
        FROM geographic_reference_points
        WHERE kind = 'metro'
    """)
    op.execute("""
        CREATE VIEW universities AS
        SELECT id AS university_id,
               name,
               ST_Y(geom) AS latitude,
               ST_X(geom) AS longitude,
               coordinate_source,
               coordinate_confidence,
               source_url,
               geography_version
        FROM geographic_reference_points
        WHERE kind = 'university'
    """)

def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS universities")
    op.execute("DROP VIEW IF EXISTS metro_stations")