"""Ingestion run bookkeeping and the staleness policy (see docs/storage-and-ingestion.md)."""
from datetime import datetime, timezone
from typing import Iterable, Optional
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from database.models import IngestionRun, Listing
from .config import MIN_SEEN_RATIO, STALENESS_RUNS

_CHUNK = 500


def start_run(session: Session, source: str, params: Optional[dict] = None) -> IngestionRun:
    run = IngestionRun(source=source, status="running", params=params or {},
                       started_at=datetime.now(timezone.utc))
    session.add(run)
    session.commit()
    return run


def finish_run(session: Session, run: IngestionRun, *, seen_ids: Iterable[str] = (),
               crawl_complete: Optional[bool] = None, stats: Optional[dict] = None,
               error: Optional[str] = None, now: Optional[datetime] = None) -> IngestionRun:
    """
    Closes a run.

    crawl_complete:
      None  -> not a crawl (file import): nothing is deactivated, status 'success'
      False -> incomplete crawl: nothing is deactivated, status 'partial'
      True  -> the whole segment was observed: the staleness policy is applied
    A failed run (error) never deactivates anything.
    """
    now = now or datetime.now(timezone.utc)
    stats = stats or {}
    for key in ("pages_requested", "pages_fetched", "listings_seen", "listings_saved",
                "listings_quarantined"):
        if key in stats:
            setattr(run, key, stats[key])
    notes = []

    # Listings seen on an index page count as observed even when their detail page failed
    # or was quarantined, so a collection failure is never mistaken for inactive inventory.
    ids = list(seen_ids)
    for i in range(0, len(ids), _CHUNK):
        session.execute(
            update(Listing)
            .where(Listing.source == run.source, Listing.external_id.in_(ids[i:i + _CHUNK]))
            .values(last_seen_at=now, last_seen_run_id=run.id, consecutive_misses=0,
                    is_active=True, deactivated_at=None),
            execution_options={"synchronize_session": False},
        )

    deactivated = 0
    if error:
        run.status = "failed"
        notes.append(f"error: {error}")
    elif crawl_complete is None:
        run.status = "success"
    elif not crawl_complete:
        run.status = "partial"
        notes.append("crawl incomplete: staleness not evaluated")
    else:
        active_total = session.scalar(select(func.count()).select_from(Listing).where(
            Listing.source == run.source, Listing.is_active.is_(True)))
        seen_active = session.scalar(select(func.count()).select_from(Listing).where(
            Listing.source == run.source, Listing.is_active.is_(True),
            Listing.last_seen_run_id == run.id))
        if active_total and seen_active / active_total < MIN_SEEN_RATIO:
            run.status = "partial"
            notes.append(f"suspicious run: saw {seen_active}/{active_total} active listings "
                         f"(< {MIN_SEEN_RATIO:.0%}); staleness not applied")
        else:
            run.status = "success"
            run.is_complete = True
            deactivated = apply_staleness(session, run, now)

    run.listings_deactivated = deactivated
    run.finished_at = now
    run.notes = "; ".join(notes) or None
    session.commit()
    return run


def apply_staleness(session: Session, run: IngestionRun, now: datetime) -> int:
    """Active listings of this source not observed in `run` get one more miss; those reaching
    STALENESS_RUNS consecutive misses are deactivated. Only called for complete runs."""
    not_seen = (Listing.source == run.source, Listing.is_active.is_(True),
                (Listing.last_seen_run_id.is_(None)) | (Listing.last_seen_run_id != run.id))
    session.execute(update(Listing).where(*not_seen)
                    .values(consecutive_misses=Listing.consecutive_misses + 1),
                    execution_options={"synchronize_session": False})
    result = session.execute(
        update(Listing)
        .where(Listing.source == run.source, Listing.is_active.is_(True),
               Listing.consecutive_misses >= STALENESS_RUNS)
        .values(is_active=False, deactivated_at=now),
        execution_options={"synchronize_session": False},
    )
    return result.rowcount or 0
