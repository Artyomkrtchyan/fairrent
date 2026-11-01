"""Bounded queue reads and atomic versioned decisions with append-only history."""
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from uuid import uuid4

try:
    from .listing_models import ListingData, public_listing
    from .review_models import Review, RiskSignal
except ImportError:
    from listing_models import ListingData, public_listing
    from review_models import Review, RiskSignal


class ReviewConflict(Exception):
    pass


def document(connection, record):
    events = connection.execute("""
        SELECT status, decision, reason, actor_id, created_at
        FROM api_review_events WHERE review_id = %s ORDER BY id
    """, (record["id"],)).fetchall()
    listing = connection.execute("SELECT document FROM api_listing_projection WHERE id = %s", (record["listing_id"],)).fetchone()
    return Review.model_validate({**record, "history": events,
                                  "listing": public_listing(ListingData.model_validate(listing["document"]))})


def enqueue(connection, listing_id, signals):
    """Trusted producer boundary; stores explicit evidence, never infers fraud from price.

    One open review per listing. Repeated identical evidence is idempotent; changed
    evidence must be reconciled by the future signal producer, not silently replaced.
    """
    signals = [RiskSignal.model_validate(s) for s in signals]
    ids = [s.id for s in signals]
    if not signals or len(set(ids)) != len(ids) or any(s.listing_id != listing_id for s in signals):
        raise ValueError("Unique evidence for the same listing is required")
    if any(s.created_at.tzinfo is None for s in signals):
        raise ValueError("Signal timestamps must include a timezone")
    # Lock the subject to serialize competing producers before examining the open queue.
    if connection.execute("SELECT id FROM api_listing_projection WHERE id=%s FOR UPDATE", (listing_id,)).fetchone() is None:
        raise ValueError("Listing not published")
    existing = connection.execute("SELECT id, signals FROM api_review_queue WHERE listing_id=%s AND status <> 'resolved'", (listing_id,)).fetchone()
    documents = [s.model_dump(mode="json") for s in sorted(signals, key=lambda s: str(s.id))]
    if existing:
        if existing[1] != documents:
            raise ReviewConflict("Open review already contains different evidence")
        return existing[0]
    review_id = uuid4()
    connection.execute("INSERT INTO api_review_queue(id, listing_id, signal_ids, signals) VALUES (%s,%s,%s,%s)",
                       (review_id, listing_id, [s.id for s in sorted(signals, key=lambda s: str(s.id))], Jsonb(documents)))
    return review_id


class ReviewRepository:
    def search(self, query):
        clauses, values = [], []
        for field in ("status", "listing_id"):
            value = getattr(query, field)
            if value is not None:
                clauses.append(f"{field} = %s")
                values.append(value)
        evidence = {}
        for field in ("category", "rule_id"):
            value = getattr(query, field)
            if value is not None:
                evidence[field] = value
        if evidence:
            clauses.append("signals @> %s")
            values.append(Jsonb([evidence]))
        where = " AND ".join(clauses) or "TRUE"
        with psycopg.connect(connect_timeout=3, row_factory=dict_row) as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            connection.execute("SET LOCAL statement_timeout = '5s'")
            total = connection.execute(f"SELECT count(*) AS n FROM api_review_queue WHERE {where}", values).fetchone()["n"]
            records = connection.execute(
                f"SELECT * FROM api_review_queue WHERE {where} ORDER BY updated_at DESC, id "
                "LIMIT %s OFFSET %s", [*values, query.page_size, (query.page - 1) * query.page_size],
            ).fetchall()
            return [document(connection, record) for record in records], total

    def update(self, review_id, update, actor_id):
        with psycopg.connect(connect_timeout=3, row_factory=dict_row) as connection:
            connection.execute("SET LOCAL statement_timeout = '5s'")
            current = connection.execute("SELECT * FROM api_review_queue WHERE id = %s FOR UPDATE", (review_id,)).fetchone()
            if current is None:
                return None
            if current["version"] != update.version or current["status"] == "resolved":
                raise ReviewConflict("Review changed or is already resolved; refresh before retrying")
            if current["status"] == update.status:
                raise ReviewConflict("Review is already in this status")
            record = connection.execute("""
                UPDATE api_review_queue SET status = %s, decision = %s, reason = %s,
                    reviewed_at = CASE WHEN %s = 'resolved' THEN CURRENT_TIMESTAMP ELSE NULL END,
                    updated_at = CURRENT_TIMESTAMP, version = version + 1
                WHERE id = %s RETURNING *
            """, (update.status, update.decision, update.reason, update.status, review_id)).fetchone()
            connection.execute("""
                INSERT INTO api_review_events(review_id, status, decision, reason, actor_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (review_id, update.status, update.decision, update.reason, actor_id))
            result = document(connection, record)
        return result
