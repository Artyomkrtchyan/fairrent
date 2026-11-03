"""C05: evaluate B06 rules against published listings (no synthetic price intervals).

Run after sync_listings: python -m backend.generate_signals [--district-support PATH].
The entire run commits atomically. API requests never execute rules or create reviews.
"""
import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from functools import partial

import psycopg

from data_pipeline import geography
from ml import ontology_rules as rules
from ml import inference
from backend.valuation_service import ValuationService
from backend.valuation_gateway import PackagedGateway, ModelUnavailable
from backend.valuation_models import ValuationRequest
from backend.valuation_coverage import OutsideCoverage, CoverageUnavailable
from backend.valuation_repository import CandidateLimit
from backend.listing_models import ListingData
from backend.signal_repository import reconcile_signals


def migrate(connection, *, with_valuations=False):
    names = (["002_valuation_estimates.sql"] if with_valuations else []) + ["003_review_workflow.sql", "004_listing_signals.sql"]
    for name in names:
        connection.execute((Path(__file__).parent / "sql" / name).read_text(encoding="utf-8"))


def evaluate(record, *, district_support=None, created_at=None, valuation=None, package=None):
    """Translate the public C03 record into B06 inputs; preserve nulls and normalized USD units."""
    if record.status != "active":
        return []
    values = record.model_dump()
    values["district"] = record.district_id
    values["asking_price_usd"] = record.price_monthly_normalized
    interval = None
    if valuation is not None and valuation['valuation_assessment']['assessment_status'] == inference.STATUS_SUCCESS:
        candidate = valuation['ml_prediction_interval']
        if candidate.get('calibration_version') and candidate.get('confidence_level') is not None:
            interval = candidate
    result = rules.evaluate_listing(values, district_support=district_support, interval=interval)
    if interval is not None and package is not None:
        # Stable model provenance is part of evidence identity; per-run request IDs
        # and timestamps must never create duplicate alerts.
        for check in result['checks']:
            if check['rule_id'] == 'PRICE-OUTSIDE-INTERVAL':
                check['evidence'] += [f"model_version={package.versions['model_version']}",
                                      f"package_version={package.manifest['package_version']}"]
    timestamp = created_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return rules.listing_signals(result, listing_id=str(record.id), created_at=timestamp)


def generate(connection, *, district_support=None, package=None, clock=None):
    """Read and lock rows in ID order. Publication and other producers use the same row locks."""
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    valuator = ValuationService(provider=partial(PackagedGateway, package=package), clock=lambda: now) if package else None
    district_support = district_support or (package.district_support if package else None)
    counts = Counter(evaluated=0, active=0, queued=0, deferred=0, calibrated=0, price_withheld=0)
    with connection.cursor(name="c05_signal_inputs") as cursor:
        cursor.execute("SELECT document FROM api_listing_projection ORDER BY id FOR UPDATE")
        for (document,) in cursor:
            record = ListingData.model_validate(document)
            valuation = None
            fresh_subject = 0 <= (now - record.last_seen_at).total_seconds() <= inference.MAX_SOURCE_AGE_DAYS * 86400
            if (valuator and record.status == 'active' and fresh_subject
                    and record.price_monthly_normalized is not None
                    and record.latitude is not None and record.longitude is not None):
                query = ValuationRequest(**{key:getattr(record, key) for key in
                    ('latitude','longitude','area_sqm','rooms','floor','total_floors','renovation','building_type')})
                try:
                    valuation = valuator.assess(query, str(uuid4()), subject=record, connection=connection)
                except (OutsideCoverage, CandidateLimit):
                    # Valid but unsupported listings still receive description/location checks.
                    pass
            supported = valuation is not None and valuation['ml_prediction_interval']['calibration_version'] is not None
            counts['calibrated' if supported else 'price_withheld'] += 1
            signals = evaluate(record, district_support=district_support,
                created_at=now.isoformat().replace('+00:00','Z'), valuation=valuation, package=package)
            result = reconcile_signals(connection, record.id, signals)
            counts["evaluated"] += 1
            for key in ("active", "queued", "deferred"):
                counts[key] += result[key]
    return {"rules_version": rules.RULES_VERSION, "geography_version": geography.GEOGRAPHY_VERSION,
            "district_reference_version": district_support.reference_version if district_support else None,
            "price_checks": "calibrated_B07" if package else "withheld_no_package", **counts}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--district-support", type=Path,
                        help="B06 train-fitted reference artifact; never fit on the serving inventory")
    parser.add_argument("--package", type=Path, default=os.environ.get("FAIRRENT_MODEL_PACKAGE") or None,
                        help="Verified B07 directory; default: FAIRRENT_MODEL_PACKAGE")
    args = parser.parse_args(argv)
    try:
        package = inference.load_package(args.package) if args.package else None
        support = None
        if args.district_support:
            payload = json.loads(args.district_support.read_text(encoding="utf-8"))
            if payload.get("rules_version") != rules.RULES_VERSION:
                raise ValueError("District support rules version does not match the loaded rules")
            support = rules.DistrictSupport.from_json(payload)
        with psycopg.connect(connect_timeout=3, autocommit=True) as connection:
            # Hold producer admission across both transactions, but release DDL
            # locks before running potentially expensive inference. Closing the
            # connection releases this session lock on every failure path.
            connection.execute("SET statement_timeout = '30s'")
            connection.execute("SELECT pg_advisory_lock(%s)", (730305001,))
            with connection.transaction():
                migrate(connection, with_valuations=package is not None)
            with connection.transaction():
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                summary = generate(connection, district_support=support, package=package)
        print(json.dumps(summary))
        return 0
    except (OSError, ValueError, psycopg.Error, inference.PackageError, CoverageUnavailable, ModelUnavailable):
        print("Signal generation failed; previous signals and reviews preserved. Check inputs and database.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
