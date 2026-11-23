"""C05: evaluate B06 rules against published listings (no synthetic price intervals).

Run after sync_listings: python -m backend.generate_signals [--district-support PATH].
The default run commits atomically. --resume commits batches with a database checkpoint.
API requests never execute rules or create reviews.
"""
import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from functools import partial

import psycopg
from psycopg.types.json import Jsonb

from data_pipeline import geography
from ml import ontology_rules as rules
from ml import inference
if __package__:
    from .valuation_service import ValuationService
    from .valuation_gateway import PackagedGateway, ModelUnavailable
    from .valuation_models import ValuationRequest
    from .valuation_coverage import OutsideCoverage, CoverageUnavailable
    from .valuation_repository import CandidateLimit
    from .listing_models import ListingData
    from .signal_repository import reconcile_signals
else:
    from valuation_service import ValuationService
    from valuation_gateway import PackagedGateway, ModelUnavailable
    from valuation_models import ValuationRequest
    from valuation_coverage import OutsideCoverage, CoverageUnavailable
    from valuation_repository import CandidateLimit
    from listing_models import ListingData
    from signal_repository import reconcile_signals


def migrate(connection, *, with_valuations=False, with_checkpoints=False):
    names = (["002_valuation_estimates.sql"] if with_valuations else []) + ["003_review_workflow.sql", "004_listing_signals.sql"]
    if with_checkpoints:
        names.append("005_signal_checkpoint.sql")
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


def generate(connection, *, district_support=None, package=None, clock=None,
             after_id=None, batch_size=None):
    """Read and lock rows in ID order. Publication and other producers use the same row locks."""
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    valuator = ValuationService(provider=partial(PackagedGateway, package=package), clock=lambda: now) if package else None
    district_support = district_support or (package.district_support if package else None)
    counts = Counter(evaluated=0, active=0, queued=0, deferred=0, calibrated=0, price_withheld=0)
    last_id = after_id
    with connection.cursor(name="c05_signal_inputs") as cursor:
        if batch_size is None:
            cursor.execute("SELECT document FROM api_listing_projection ORDER BY id FOR UPDATE")
        else:
            cursor.execute("""
                SELECT document FROM api_listing_projection
                WHERE (%s::uuid IS NULL OR id > %s::uuid)
                ORDER BY id LIMIT %s FOR UPDATE
            """, (after_id, after_id, batch_size))
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
            last_id = record.id
    summary = {"rules_version": rules.RULES_VERSION, "geography_version": geography.GEOGRAPHY_VERSION,
               "district_reference_version": district_support.reference_version if district_support else None,
               "price_checks": "calibrated_B07" if package else "withheld_no_package", **counts}
    if batch_size is not None:
        summary["last_listing_id"] = str(last_id) if last_id else None
    return summary


def inventory_key(connection):
    # xmin changes on every publication update, including changes to comparables.
    return connection.execute("""
        SELECT md5(COALESCE(string_agg(id::text || ':' || xmin::text, ',' ORDER BY id), ''))
        FROM api_listing_projection
    """).fetchone()[0]


def context_key(package, support):
    digest = hashlib.sha256()
    files = [Path(__file__), *Path(__file__).parent.glob("valuation_*.py")]
    files += [Path(geography.__file__), Path(rules.__file__), Path(inference.__file__)]
    files += list(Path(inference.__file__).parent.glob("*.py"))
    if package:
        files += [package.directory / "SHA256SUMS.json"]
    for name in ("VALUATION_COVERAGE_FILE", "VALUATION_DISTRICTS_FILE"):
        if os.environ.get(name):
            files.append(Path(os.environ[name]))
    for path in sorted(files, key=lambda path: path.name):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    digest.update(json.dumps(support.to_json() if support else None, sort_keys=True).encode())
    return digest.hexdigest()


def generate_resumable(connection, *, district_support=None, package=None, batch_size=25, clock=None):
    """Commit results and cursor together. A new inventory starts a new pass."""
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    support = district_support or (package.district_support if package else None)
    key = context_key(package, support)
    with connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        snapshot = inventory_key(connection)
        previous = connection.execute("""
            SELECT inventory_key, as_of, last_listing_id, counts, completed
            FROM api_signal_checkpoints WHERE context_key=%s FOR UPDATE
        """, (key,)).fetchone()
        if (previous and previous[0] == snapshot and
                0 <= (now - previous[1]).total_seconds() < 86400):
            as_of, last_id, totals, completed = previous[1:]
        else:
            as_of, last_id, totals, completed = now, None, {}, False
        connection.execute("""
            INSERT INTO api_signal_checkpoints(context_key, inventory_key, as_of)
            VALUES (%s, %s, %s) ON CONFLICT (context_key) DO NOTHING
        """, (key, snapshot, as_of))
    print(json.dumps({"status": "resuming" if last_id else "starting",
                      "committed": totals.get("evaluated", 0), "completed": completed}), flush=True)
    summary = {}
    while not completed:
        with connection.transaction():
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            if inventory_key(connection) != snapshot:
                raise ValueError("Inventory changed; rerun to start a new snapshot")
            summary = generate(connection, district_support=support, package=package,
                               clock=lambda: as_of, after_id=last_id, batch_size=batch_size)
            last_id = summary.pop("last_listing_id")
            totals = {name: totals.get(name, 0) + summary[name] for name in
                      ("evaluated", "active", "queued", "deferred", "calibrated", "price_withheld")}
            completed = summary["evaluated"] < batch_size
            connection.execute("""
                UPDATE api_signal_checkpoints
                SET inventory_key=%s, as_of=%s, last_listing_id=%s, counts=%s,
                    completed=%s, updated_at=CURRENT_TIMESTAMP
                WHERE context_key=%s
            """, (snapshot, as_of, last_id, Jsonb(totals), completed, key))
        print(json.dumps({"status": "completed" if completed else "batch_committed",
                          **totals}), flush=True)
    return {"rules_version": rules.RULES_VERSION, "geography_version": geography.GEOGRAPHY_VERSION,
            "district_reference_version": support.reference_version if support else None,
            "price_checks": "calibrated_B07" if package else "withheld_no_package", **totals}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true",
                        help="Commit batches and resume from the last database checkpoint")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--skip-migrations", action="store_true",
                        help="Use schemas already applied by the database owner")
    parser.add_argument("--district-support", type=Path,
                        help="B06 train-fitted reference artifact; never fit on the serving inventory")
    parser.add_argument("--package", type=Path, default=os.environ.get("FAIRRENT_MODEL_PACKAGE") or None,
                        help="Verified B07 directory; default: FAIRRENT_MODEL_PACKAGE")
    args = parser.parse_args(argv)
    if not 1 <= args.batch_size <= 1000:
        parser.error("batch-size must be between 1 and 1000")
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
            if args.resume:
                if not connection.execute("SELECT pg_try_advisory_lock(%s)", (730305001,)).fetchone()[0]:
                    raise ValueError("Another signal worker is already running")
            else:
                connection.execute("SELECT pg_advisory_lock(%s)", (730305001,))
            if not args.skip_migrations:
                with connection.transaction():
                    migrate(connection, with_valuations=package is not None, with_checkpoints=args.resume)
            if args.resume:
                summary = generate_resumable(connection, district_support=support, package=package,
                                             batch_size=args.batch_size)
            else:
                with connection.transaction():
                    connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                    summary = generate(connection, district_support=support, package=package)
        print(json.dumps(summary))
        return 0
    except (OSError, ValueError, psycopg.Error, inference.PackageError, CoverageUnavailable, ModelUnavailable) as error:
        if args.resume:
            print(f"Signal generation stopped ({type(error).__name__}, "
                  f"sqlstate={getattr(error, 'sqlstate', None)}). "
                  "The current transaction was rolled back; committed batches remain available. "
                  "Rerun with --resume to continue.", file=sys.stderr)
        else:
            print("Signal generation failed; previous signals and reviews preserved. "
                  "Check inputs and database.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
