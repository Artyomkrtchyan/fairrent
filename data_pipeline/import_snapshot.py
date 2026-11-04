"""Import only fresh, hash-bound collection output; partial runs never deactivate."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import signal
from uuid import UUID

from database.models import IngestionRun

from .cli import get_session_factory, ingest
from .ingestion import finish_run, start_run
from .scraper import ListingPipeline


def load_snapshot(path, *, now=None):
    path = Path(path)
    report = json.loads(path.with_suffix('.report.json').read_text(encoding='utf-8'))
    UUID(report['snapshot_id'])
    now = now or datetime.now(timezone.utc)
    if (report.get('schema_version') != 1 or report.get('source') != 'list.am'
            or report.get('segment') != 'yerevan-monthly-rentals'
            or report.get('status') not in ('success', 'partial')
            or type(report.get('complete')) is not bool
            or (report['status'] == 'success') != report['complete']):
        raise ValueError('Collection report is not acceptable')
    finished = datetime.fromisoformat(report['finished_at'])
    age = (now - finished).total_seconds()
    if not 0 <= age <= 6 * 3600:
        raise ValueError('Collection report is stale or from the future')
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != report.get('sha256'):
        raise ValueError('Collection output checksum mismatch')
    records = json.loads(payload)
    if not isinstance(records, list) or not records or len(records) != report.get('records'):
        raise ValueError('Collection output count mismatch or empty output')
    ids = []
    for record in records:
        if not isinstance(record, dict) or not str(record.get('external_id', '')).isdigit() or record.get('period') != 'month':
            raise ValueError('Invalid source identity or rental period')
        record['id'] = str(record['external_id'])
        ids.append(record['id'])
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate source identities')
    return records, report


def import_snapshot(path):
    records, report = load_snapshot(path)
    session = get_session_factory()()
    pipeline = ListingPipeline(delay=0)
    run = None
    try:
        prior = session.query(IngestionRun).filter(
            IngestionRun.source == 'list.am',
            IngestionRun.params['snapshot_id'].as_string() == report['snapshot_id'],
            IngestionRun.status.in_(['success', 'partial']),
        ).first()
        if prior is not None:
            raise ValueError('Snapshot already imported; collect a new observation instead')
        run = start_run(session, 'list.am', {'snapshot_id': report['snapshot_id'],
                        'snapshot_sha256': report['sha256'], 'collector': 'cloakbrowser'})
        saved = ingest(records, pipeline, session, 'list.am', run_id=run.id)
        clean = saved == len(records) and not pipeline.quarantine_log
        run = finish_run(session, run, seen_ids=[r['id'] for r in records],
                         crawl_complete=report['complete'] and clean,
                         stats={'listings_seen': len(records), 'listings_saved': saved,
                                'listings_quarantined': len(pipeline.quarantine_log),
                                'pages_fetched': report.get('pages_fetched', 0)})
        if not clean or run.status != 'success':
            return 2
        return 0
    except Exception:
        session.rollback()
        if run is not None:
            finish_run(session, run, error='snapshot import failed; inspect protected local logs')
        raise
    finally:
        session.close()
        pipeline.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    args = parser.parse_args(argv)

    def terminate(signum, frame):
        raise InterruptedError('snapshot import terminated')

    signal.signal(signal.SIGTERM, terminate)
    try:
        return import_snapshot(args.snapshot)
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
