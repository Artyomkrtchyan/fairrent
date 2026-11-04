"""Run the weekly collection, import, publication, analytics and signal stages."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from uuid import uuid4
from zoneinfo import ZoneInfo

from .weekly_collect import atomic_json, utcnow


def run_command(command, *, timeout):
    process = subprocess.Popen(command, start_new_session=True, stdin=subprocess.DEVNULL)
    try:
        return process.wait(timeout=timeout)
    except BaseException:
        # A timeout or termination must stop the browser and its children before
        # the outer flock is released. Linux is the supported production host.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        # The leader may exit before a stubborn browser child. Clean up the
        # original process group even when wait() has already reaped its leader.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        raise


def execute(state_dir, *, max_pages=50, details_limit=2000, delay=3, timeout=14400, runner=run_command):
    state_dir = Path(state_dir)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8]
    directory = state_dir / 'runs' / run_id
    directory.mkdir(parents=True)
    snapshot = directory / 'listings.json'
    now = datetime.now(ZoneInfo('Asia/Yerevan')).date()
    monday = now - timedelta(days=now.weekday())
    python = sys.executable
    stages = [
        ('collect', [python, '-m', 'data_pipeline.weekly_collect', '--output', str(snapshot),
                     '--profile', str(state_dir / 'profile'), '--max-pages', str(max_pages),
                     '--details-limit', str(details_limit), '--delay', str(delay)]),
        ('import', [python, '-m', 'data_pipeline.import_snapshot', str(snapshot)]),
        ('publish', [python, '-m', 'backend.sync_listings']),
        ('analytics', [python, '-m', 'data_pipeline.aggregate_neighborhoods', '--week-start', monday.isoformat()]),
        ('signals', [python, '-m', 'backend.generate_signals']),
    ]
    report = dict(run_id=run_id, started_at=utcnow(), status='running', stages=[])
    deadline = time.monotonic() + timeout
    partial = False

    def persist():
        atomic_json(directory / 'job.json', report)
        atomic_json(state_dir / 'latest.json', report)

    persist()
    try:
        for name, command in stages:
            report['stage'] = name
            persist()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            code = runner(command, timeout=remaining)
            report['stages'].append({'stage': name, 'exit_code': code})
            # A partial import can still publish observed records and refresh
            # analytics/signals. It never advances the last-complete timestamp.
            if name == 'import' and code == 2:
                partial = True
            elif code:
                raise RuntimeError('stage failed')
        report['status'] = 'partial' if partial else 'success'
    except BaseException as error:
        report.update(status='failed', error_type=type(error).__name__)
    finally:
        report['finished_at'] = utcnow()
        persist()
        if report['status'] == 'success':
            atomic_json(state_dir / 'last-success.json', report)
    print(json.dumps(report))
    return {'success': 0, 'partial': 2, 'failed': 1}[report['status']]


def check(state_dir, *, max_age_hours=192):
    try:
        latest = json.loads((Path(state_dir) / 'latest.json').read_text(encoding='utf-8'))
        success = json.loads((Path(state_dir) / 'last-success.json').read_text(encoding='utf-8'))
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(success['finished_at'])).total_seconds()
        healthy = latest['status'] == 'success' and 0 <= age <= max_age_hours * 3600
    except (OSError, ValueError, KeyError, TypeError):
        healthy = False
    print(json.dumps({'healthy': healthy}))
    return 0 if healthy else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--max-age-hours', type=float, default=192)
    parser.add_argument('--max-pages', type=int, default=50)
    parser.add_argument('--details-limit', type=int, default=2000)
    parser.add_argument('--delay', type=float, default=3)
    parser.add_argument('--timeout', type=int, default=14400)
    args = parser.parse_args(argv)
    if min(args.max_age_hours, args.max_pages, args.timeout) <= 0 or args.details_limit < 0 or args.delay < 1:
        parser.error('invalid bounds')
    if args.check:
        return check(args.state_dir, max_age_hours=args.max_age_hours)
    if sys.platform != 'linux':
        parser.error('scheduled execution requires Linux')

    def terminate(signum, frame):
        raise InterruptedError('job terminated')

    signal.signal(signal.SIGTERM, terminate)
    return execute(args.state_dir.resolve(), max_pages=args.max_pages,
                   details_limit=args.details_limit, delay=args.delay, timeout=args.timeout)


if __name__ == '__main__':
    raise SystemExit(main())
