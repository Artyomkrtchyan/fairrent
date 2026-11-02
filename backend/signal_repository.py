"""Publish current findings and queue previously unseen evidence in one caller-owned transaction."""
from uuid import UUID

from psycopg.types.json import Jsonb

try:
    from .review_models import RiskSignal
    from .review_repository import enqueue
except ImportError:
    from review_models import RiskSignal
    from review_repository import enqueue


def reconcile_signals(connection, listing_id, signals):
    """Serialize with other producers on the listing row. Never mutate an existing review.

    Signal creation time is the first observation, not the time of the latest replay.
    New evidence waits while a review is open; a later run queues only IDs never reviewed.
    Resolved evidence (including dismissed evidence) is never automatically reopened.
    """
    listing_id = UUID(str(listing_id))
    validated = [RiskSignal.model_validate(s) for s in signals]
    if (len({s.id for s in validated}) != len(validated)
            or any(s.listing_id != listing_id or s.created_at.tzinfo is None for s in validated)):
        raise ValueError("Signals must have unique IDs, UTC timestamps and the same listing")
    if connection.execute("SELECT id FROM api_listing_projection WHERE id=%s FOR UPDATE", (listing_id,)).fetchone() is None:
        raise ValueError("Listing not published")
    connection.execute("UPDATE api_listing_signals SET active=false WHERE listing_id=%s AND active", (listing_id,))
    documents = []
    for signal in sorted(validated, key=lambda s: str(s.id)):
        incoming = signal.model_dump(mode="json")
        stored = connection.execute("SELECT document FROM api_listing_signals WHERE id=%s", (signal.id,)).fetchone()
        if stored:
            original = stored[0]
            if ({k: v for k, v in original.items() if k != "created_at"}
                    != {k: v for k, v in incoming.items() if k != "created_at"}):
                raise ValueError("Signal ID already belongs to different evidence")
            incoming = original
            connection.execute("UPDATE api_listing_signals SET active=true, last_evaluated_at=CURRENT_TIMESTAMP WHERE id=%s", (signal.id,))
        else:
            connection.execute("INSERT INTO api_listing_signals(id, listing_id, document) VALUES (%s,%s,%s)",
                               (signal.id, listing_id, Jsonb(incoming)))
        documents.append(incoming)
    unseen = [d for d in documents if not connection.execute(
        "SELECT 1 FROM api_review_queue WHERE listing_id=%s AND signal_ids @> %s::uuid[] LIMIT 1",
        (listing_id, [UUID(d["id"])]),
    ).fetchone()]
    review_id = None
    deferred = 0
    if unseen:
        opened = connection.execute("SELECT id FROM api_review_queue WHERE listing_id=%s AND status <> 'resolved'", (listing_id,)).fetchone()
        if opened:
            deferred = len(unseen)
        else:
            review_id = enqueue(connection, listing_id, unseen)
    return {"active": len(documents), "queued": len(unseen) if review_id else 0,
            "deferred": deferred, "review_id": str(review_id) if review_id else None}
