"""C05: evaluate B06 rules against published listings (no synthetic price intervals).

Run after sync_listings: python -m backend.generate_signals [--district-support PATH].
The entire run commits atomically. API requests never execute rules or create reviews.
"""
import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from data_pipeline import geography
from ml import ontology_rules as rules
from backend.listing_models import ListingData
from backend.signal_repository import reconcile_signals


def migrate(connection):
    for name in ("003_review_workflow.sql", "004_listing_signals.sql"):
        connection.execute((Path(__file__).parent / "sql" / name).read_text(encoding="utf-8"))


def evaluate(record, *, district_support=None, created_at=None):
    """Translate the public C03 record into B06 inputs; preserve nulls and normalized USD units."""
    if record.status != "active":
        return []
    values = record.model_dump()
    values["district"] = record.district_id
    values["asking_price_usd"] = record.price_monthly_normalized
    result = rules.evaluate_listing(values, district_support=district_support)
    # B07 will supply a model-bound calibrated interval. Until then the price check is unknown.
    timestamp = created_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return rules.listing_signals(result, listing_id=str(record.id), created_at=timestamp)


def generate(connection, *, district_support=None):
    """Read and lock rows in ID order. Publication and other producers use the same row locks."""
    counts = Counter(evaluated=0, active=0, queued=0, deferred=0)
    with connection.cursor(name="c05_signal_inputs") as cursor:
        cursor.execute("SELECT document FROM api_listing_projection ORDER BY id FOR UPDATE")
        for (document,) in cursor:
            record = ListingData.model_validate(document)
            signals = evaluate(record, district_support=district_support)
            result = reconcile_signals(connection, record.id, signals)
            counts["evaluated"] += 1
            for key in ("active", "queued", "deferred"):
                counts[key] += result[key]
    return {"rules_version": rules.RULES_VERSION, "geography_version": geography.GEOGRAPHY_VERSION,
            "district_reference_version": district_support.reference_version if district_support else None,
            "price_checks": "withheld_until_B07", **counts}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--district-support", type=Path,
                        help="B06 train-fitted reference artifact; never fit on the serving inventory")
    args = parser.parse_args(argv)
    try:
        support = None
        if args.district_support:
            payload = json.loads(args.district_support.read_text(encoding="utf-8"))
            if payload.get("rules_version") != rules.RULES_VERSION:
                raise ValueError("District support rules version does not match the loaded rules")
            support = rules.DistrictSupport.from_json(payload)
        with psycopg.connect(connect_timeout=3) as connection:
            connection.execute("SELECT pg_advisory_xact_lock(%s)", (730305001,))
            connection.execute("SET LOCAL statement_timeout = '30s'")
            migrate(connection)
            summary = generate(connection, district_support=support)
        print(json.dumps(summary))
        return 0
    except (OSError, ValueError, psycopg.Error):
        print("Signal generation failed; previous signals and reviews preserved. Check inputs and database.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
