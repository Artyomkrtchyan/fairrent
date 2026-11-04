"""Exercise C09 admission against real A04 lifecycle storage in disposable PostGIS."""
import os

import pytest

from . import import_snapshot as importer
from .test_loader_postgres import listing, rec, run, session
from .test_weekly import snapshot


pytestmark = pytest.mark.skipif(not os.environ.get('TEST_DATABASE_URL'), reason='TEST_DATABASE_URL not set')


def test_partial_failure_recovery_and_replay_preserve_inventory(session, tmp_path, monkeypatch):
    run(session, [rec('123'), rec('456')])
    monkeypatch.setattr(importer, 'get_session_factory', lambda: lambda: session)
    path, _ = snapshot(tmp_path, complete=False)
    assert importer.import_snapshot(path) == 2
    assert listing(session, '456').is_active
    assert listing(session, '456').consecutive_misses == 0

    # Corrupted evidence is rejected before a lifecycle run can begin.
    path.write_text('[]')
    with pytest.raises(ValueError):
        importer.import_snapshot(path)
    assert listing(session, '456').consecutive_misses == 0

    path, _ = snapshot(tmp_path)
    assert importer.import_snapshot(path) == 0
    assert listing(session, '456').consecutive_misses == 1
    with pytest.raises(ValueError, match='already imported'):
        importer.import_snapshot(path)
    assert listing(session, '456').consecutive_misses == 1
    assert listing(session, '456').is_active

    # A second genuinely fresh complete observation applies the existing A04 policy.
    path, _ = snapshot(tmp_path)
    assert importer.import_snapshot(path) == 0
    assert not listing(session, '456').is_active
    assert listing(session, '123').is_active
