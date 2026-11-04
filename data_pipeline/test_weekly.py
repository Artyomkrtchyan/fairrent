"""Offline C09 failure, lifecycle admission and recovery tests."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import os
import signal
import sys
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest

from . import import_snapshot as importer
from . import weekly_collect as collector
from . import weekly_job as job


def snapshot(tmp_path, *, complete=True):
    path = tmp_path / 'listings.json'
    records = [dict(external_id='123', price=600, currency='USD', period='month',
                    lat=40.18, lon=44.51, district='Kentron')]
    collector.atomic_json(path, records)
    report = dict(schema_version=1, snapshot_id=uuid4().hex, source='list.am', segment='yerevan-monthly-rentals',
                  status='success' if complete else 'partial', complete=complete,
                  records=1, finished_at=collector.utcnow(), pages_fetched=2,
                  sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    collector.atomic_json(path.with_suffix('.report.json'), report)
    return path, report


@pytest.mark.parametrize('change', ['failed', 'hash', 'stale', 'future', 'count', 'inconsistent', 'segment'])
def test_untrusted_snapshot_rejected_before_database(tmp_path, monkeypatch, change):
    path, report = snapshot(tmp_path)
    if change == 'failed': report['status'] = 'failed'
    if change == 'hash': report['sha256'] = '0' * 64
    if change == 'count': report['records'] = 2
    if change == 'inconsistent': report['complete'] = False
    if change == 'segment': report['segment'] = 'other'
    if change in ('stale', 'future'):
        hours = -7 if change == 'stale' else 1
        report['finished_at'] = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
    collector.atomic_json(path.with_suffix('.report.json'), report)
    monkeypatch.setattr(importer, 'get_session_factory', lambda: pytest.fail('must not touch database'))
    with pytest.raises(ValueError):
        importer.import_snapshot(path)


@pytest.mark.parametrize('complete,quarantine,expected', [(True, False, True), (False, False, False), (True, True, False)])
def test_only_complete_clean_import_can_apply_staleness(tmp_path, monkeypatch, complete, quarantine, expected):
    path, _ = snapshot(tmp_path, complete=complete)
    query = SimpleNamespace(first=lambda: None)
    query.filter = lambda *args: query
    session = SimpleNamespace(close=lambda: None, rollback=lambda: None, query=lambda *args: query)
    monkeypatch.setattr(importer, 'get_session_factory', lambda: lambda: session)
    monkeypatch.setattr(importer, 'start_run', lambda *a: SimpleNamespace(id=1))
    calls = []

    def ingest(records, pipeline, *args, **kwargs):
        if quarantine:
            pipeline.quarantine_log.append({'error': 'rejected'})
        return 0 if quarantine else 1

    def finish(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status='success' if kwargs['crawl_complete'] else 'partial')

    monkeypatch.setattr(importer, 'ingest', ingest)
    monkeypatch.setattr(importer, 'finish_run', finish)
    assert importer.import_snapshot(path) == (0 if expected else 2)
    assert calls[0]['crawl_complete'] is expected
    assert calls[0]['seen_ids'] == ['123']


def test_stage_failure_stops_publication_and_recovery_updates_freshness(tmp_path):
    calls = []

    def fail(command, **kwargs):
        calls.append(command)
        return 1

    assert job.execute(tmp_path, runner=fail) == 1
    assert len(calls) == 1  # no import/publication after failed collection
    assert not (tmp_path / 'last-success.json').exists()
    assert job.check(tmp_path) == 1
    assert job.execute(tmp_path, runner=lambda *a, **kw: 0) == 0
    success = (tmp_path / 'last-success.json').read_bytes()
    assert job.check(tmp_path) == 0
    assert job.execute(tmp_path, runner=fail) == 1
    assert (tmp_path / 'last-success.json').read_bytes() == success
    assert job.check(tmp_path) == 1  # recent success cannot conceal latest failure


def test_partial_import_runs_downstream_but_does_not_claim_complete_success(tmp_path):
    calls = []

    def partial(command, **kwargs):
        calls.append(command)
        return 2 if 'data_pipeline.import_snapshot' in command else 0

    assert job.execute(tmp_path, runner=partial) == 2
    assert len(calls) == 5
    assert not (tmp_path / 'last-success.json').exists()


def test_timeout_records_failure(tmp_path):
    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 1)
    assert job.execute(tmp_path, runner=timeout) == 1
    report = json.loads((tmp_path / 'latest.json').read_text())
    assert report['status'] == 'failed'
    assert report['error_type'] == 'TimeoutExpired'


def card_html():
    return '''<div id="contentr"><div class="category-data-list-grid-card">
      <a href="/item/123"><span class="l">Apartment</span>
      <div class="category-data-list-card__amount"><span class="category-data-list-card__currency">$</span>600</div>
      <div class="category-data-list-card__price-frequency">ամսական</div>
      <div class="category-data-list-card__location">Կենտրոն</div></a></div></div>'''


def test_explicit_empty_catalogue_ends_collection_and_preserves_original_price():
    def fetch(url):
        if '/item/' in url: return '<h1>Apartment</h1>'
        if url.endswith('/2'): return '<div id="contentr"></div>'
        return card_html()
    records, complete, pages = collector.collect(fetch, max_pages=3, details_limit=3)
    assert complete and pages == 2
    assert records[0]['price'] == 600 and records[0]['currency'] == 'USD'


@pytest.mark.parametrize('terminal', ['<title>Just a moment</title>', '<div>changed markup</div>', card_html()])
def test_blocked_changed_or_repeated_page_never_completes(terminal):
    def fetch(url):
        return terminal if url.endswith('/2') else card_html()
    with pytest.raises(ValueError):
        collector.collect(fetch, max_pages=3, details_limit=3)


def test_page_cap_and_detail_cap_are_partial():
    def fetch(url):
        if '/item/' in url: return '<h1>Apartment</h1>'
        return card_html()
    assert collector.collect(fetch, max_pages=1, details_limit=3)[1] is False
    assert collector.collect(fetch, max_pages=1, details_limit=0)[1] is False


def test_failed_collection_preserves_old_snapshot_and_invalidates_old_report(tmp_path, monkeypatch):
    path, _ = snapshot(tmp_path)
    old = path.read_bytes()
    import sys
    monkeypatch.setitem(sys.modules, 'cloakbrowser', SimpleNamespace(
        launch_persistent_context=lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('secret-must-not-appear'))))
    assert collector.main(['--output', str(path), '--profile', str(tmp_path / 'profile')]) == 1
    assert path.read_bytes() == old
    report = path.with_suffix('.report.json').read_text()
    assert 'secret-must-not-appear' not in report
    assert json.loads(report)['status'] == 'failed'


def test_snapshot_replay_is_rejected_without_another_lifecycle_run(tmp_path, monkeypatch):
    path, _ = snapshot(tmp_path)
    query = SimpleNamespace(first=lambda: SimpleNamespace(id=1))
    query.filter = lambda *args: query
    session = SimpleNamespace(close=lambda: None, rollback=lambda: None, query=lambda *args: query)
    monkeypatch.setattr(importer, 'get_session_factory', lambda: lambda: session)
    monkeypatch.setattr(importer, 'start_run', lambda *a: pytest.fail('must not count a second observation'))
    with pytest.raises(ValueError, match='already imported'):
        importer.import_snapshot(path)


@pytest.mark.skipif(sys.platform != 'linux', reason='Linux process groups and flock')
def test_timed_out_process_is_stopped(tmp_path):
    pidfile = tmp_path / 'pid'
    command = [sys.executable, '-c',
               'import os,time,pathlib; pathlib.Path(__import__("sys").argv[1]).write_text(str(os.getpid())); time.sleep(60)',
               str(pidfile)]
    with pytest.raises(subprocess.TimeoutExpired):
        job.run_command(command, timeout=1)
    pid = int(pidfile.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


@pytest.mark.skipif(sys.platform != 'linux', reason='Linux process groups')
def test_timeout_also_kills_child_when_leader_exits_first(tmp_path):
    child_pid = tmp_path / 'child-pid'
    child = ('import os,signal,time,pathlib; signal.signal(signal.SIGTERM,signal.SIG_IGN); '
             'pathlib.Path(__import__("sys").argv[1]).write_text(str(os.getpid())); time.sleep(60)')
    parent = 'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",sys.argv[1],sys.argv[2]]); time.sleep(60)'
    with pytest.raises(subprocess.TimeoutExpired):
        job.run_command([sys.executable, '-c', parent, child, str(child_pid)], timeout=1)
    pid = int(child_pid.read_text())
    for _ in range(100):
        stat = Path(f'/proc/{pid}/stat')
        if not stat.exists() or stat.read_text().split()[2] == 'Z':
            break
        time.sleep(0.01)
    else:
        pytest.fail('child remained alive after timeout cleanup')


@pytest.mark.skipif(sys.platform != 'linux', reason='Linux process groups and flock')
def test_shell_rejects_overlapping_job(tmp_path):
    fake = tmp_path / 'python'
    fake.write_text('#!/bin/sh\ntouch "$FAIRRENT_WEEKLY_STATE/started"\nsleep 60\n')
    fake.chmod(0o700)
    state = tmp_path / 'state'
    environment = dict(os.environ, FAIRRENT_WEEKLY_PYTHON=str(fake), FAIRRENT_WEEKLY_STATE=str(state))
    script = Path(__file__).parents[1] / 'infra/scripts/run_weekly_ingestion.sh'
    first = subprocess.Popen(['bash', str(script)], env=environment, start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            if (state / 'started').exists(): break
            time.sleep(0.05)
        assert (state / 'started').exists()
        second = subprocess.run(['bash', str(script)], env=environment, capture_output=True, timeout=5)
        assert second.returncode == 75
    finally:
        os.killpg(first.pid, signal.SIGTERM)
        first.wait(timeout=5)
