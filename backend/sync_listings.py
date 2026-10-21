"""Publish A03/A04 inventory to the C03 read model after ingestion.

Run with the C02 PG* environment: python -m backend.sync_listings.
No source tables are written. A failure rolls back the entire publication.
"""
import json
import sys
from collections import Counter
from decimal import DecimalException
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from pydantic import ValidationError

try:
    from .listing_repository import publish_listing
    from .source_adapter import Unpublishable, adapt_source
except ImportError:
    from listing_repository import publish_listing
    from source_adapter import Unpublishable, adapt_source


SOURCE_SQL = """
    SELECT l.*, p.district, p.address_raw,
           ST_Y(p.geom) AS latitude, ST_X(p.geom) AS longitude
    FROM listings l LEFT JOIN properties p ON p.id = l.property_id
    WHERE l.source = 'list.am'
    ORDER BY l.id
"""
SYNC_LOCK = 730304001


class PublicationBusy(RuntimeError):
    pass


def sync_projection(connection):
    """Caller owns transaction and sync serialization. Return counts, never raw records."""
    connection.execute((Path(__file__).parent / "sql" / "001_listing_projection.sql").read_text(encoding="utf-8"))
    if connection.execute("SELECT EXISTS (SELECT 1 FROM ingestion_runs WHERE source = 'list.am' AND status = 'running')").fetchone()[0]:
        raise PublicationBusy("A list.am ingestion run is still running; finish it before publication")
    connection.execute("CREATE TEMP TABLE c03_published_ids (id uuid PRIMARY KEY) ON COMMIT DROP")
    reasons = Counter()
    published = 0
    with connection.cursor(name="c03_source_snapshot", row_factory=dict_row) as cursor:
        cursor.execute(SOURCE_SQL)
        for row in cursor:
            try:
                record = adapt_source(row)
            except Unpublishable as error:
                reasons[str(error)] += 1
                continue
            except (ValidationError, DecimalException):
                reasons["invalid_contract_record"] += 1
                continue
            publish_listing(connection, record)
            connection.execute("INSERT INTO c03_published_ids VALUES (%s)", (record.id,))
            published += 1
    removed = connection.execute("""
        DELETE FROM api_listing_projection p
        WHERE NOT EXISTS (SELECT 1 FROM c03_published_ids live WHERE live.id = p.id)
    """).rowcount
    return {"published": published, "excluded": sum(reasons.values()),
            "excluded_reasons": dict(reasons), "removed_from_projection": removed}


def main():
    # Lock before beginning the snapshot, so a waiting publication cannot overwrite
    # a newer snapshot. Disconnect also releases this session lock on any failure.
    try:
        with psycopg.connect(connect_timeout=3, autocommit=True) as connection:
            connection.execute("SELECT pg_advisory_lock(%s)", (SYNC_LOCK,))
            with connection.transaction():
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                connection.execute("SET LOCAL statement_timeout = '30s'")
                summary = sync_projection(connection)
        print(json.dumps(summary))
        return 0
    except PublicationBusy as error:
        print(str(error), file=sys.stderr)
        return 1
    except psycopg.Error:
        print("Publication failed; previous API snapshot preserved. Check database/migrations.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
