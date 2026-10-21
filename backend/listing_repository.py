"""PostgreSQL read projection. Only validated, explicitly published records are served.

The sync_listings command adapts accepted A02/A04 inventory in one transaction.
"""
import psycopg
from psycopg.types.json import Jsonb

try:
    from .listing_models import ListingData, ListingQuery
except ImportError:  # Docker runs uvicorn main:app from /app.
    from listing_models import ListingData, ListingQuery


ORDER_BY = {
    "newest": "newest_at DESC NULLS LAST, id ASC",
    "price_asc": "price ASC NULLS LAST, id ASC",
    "price_desc": "price DESC NULLS LAST, id ASC",
    "area_asc": "area ASC NULLS LAST, id ASC",
    "area_desc": "area DESC NULLS LAST, id ASC",
}


def publish_listing(connection, record: ListingData):
    """Publish a complete normalized record; caller owns commit/rollback.

    No defaults are inferred from legacy converted prices, created_at or mock data.
    Public UUIDs must remain stable across updates and ingestion schema changes.
    """
    record = ListingData.model_validate(
        record.model_dump() if isinstance(record, ListingData) else record
    )
    result = connection.execute("""
        INSERT INTO api_listing_projection
            (id, source, external_id, status, district_id, price, area, rooms,
             latitude, longitude, newest_at, document)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            status=EXCLUDED.status, district_id=EXCLUDED.district_id,
            price=EXCLUDED.price, area=EXCLUDED.area, rooms=EXCLUDED.rooms,
            latitude=EXCLUDED.latitude, longitude=EXCLUDED.longitude,
            newest_at=EXCLUDED.newest_at, document=EXCLUDED.document
        WHERE api_listing_projection.source=EXCLUDED.source
          AND api_listing_projection.external_id=EXCLUDED.external_id
        RETURNING id
    """, (record.id, record.source, record.external_id, record.status,
          record.district_id, record.price_monthly_normalized, record.area_sqm,
          record.rooms, record.latitude, record.longitude,
          record.published_at or record.first_seen_at,
          Jsonb(record.model_dump(mode="json")))).fetchone()
    if result is None:
        raise ValueError("Public UUID already belongs to another source listing")


def search_sql(query: ListingQuery):
    clauses, params = ["status = %s"], [query.status]
    for name, column, operator in (
        ("district_id", "district_id", "="), ("price_min", "price", ">="),
        ("price_max", "price", "<="), ("rooms", "rooms", "="),
        ("area_min", "area", ">="), ("area_max", "area", "<="),
    ):
        value = getattr(query, name)
        if value is not None:
            clauses.append(f"{column} {operator} %s")
            params.append(value)
    if query.bbox is not None:
        west, south, east, north = query.bounds()
        clauses.extend(["longitude BETWEEN %s AND %s", "latitude BETWEEN %s AND %s"])
        params.extend([west, east, south, north])
    return " AND ".join(clauses), params


class ListingRepository:
    def search(self, query: ListingQuery):
        where, params = search_sql(query)
        # Count and page must see the same snapshot, including out-of-range pages.
        with psycopg.connect(connect_timeout=3) as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            connection.execute("SET LOCAL statement_timeout = '5s'")
            total = connection.execute(
                f"SELECT count(*) FROM api_listing_projection WHERE {where}", params
            ).fetchone()[0]
            rows = connection.execute(
                f"SELECT document FROM api_listing_projection WHERE {where} "
                f"ORDER BY {ORDER_BY[query.sort]} LIMIT %s OFFSET %s",
                [*params, query.page_size, (query.page - 1) * query.page_size],
            ).fetchall()
        return [ListingData.model_validate(row[0]) for row in rows], total

    def get(self, listing_id):
        with psycopg.connect(connect_timeout=3) as connection:
            connection.execute("SET TRANSACTION READ ONLY")
            connection.execute("SET LOCAL statement_timeout = '5s'")
            row = connection.execute(
                "SELECT document FROM api_listing_projection WHERE id = %s", (listing_id,)
            ).fetchone()
        return ListingData.model_validate(row[0]) if row else None
