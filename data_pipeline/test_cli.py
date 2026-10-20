import json
from types import SimpleNamespace
from click.testing import CliRunner
from . import cli as cli_module
from .scraper import ListingPipeline

class FakeSession:
    def close(self): pass
    def rollback(self): pass


def _patch(monkeypatch, saved, finished=None):
    monkeypatch.setattr(cli_module, "get_session_factory", lambda: FakeSession)
    monkeypatch.setattr(cli_module, "process_scraped_item",
                        lambda session, data, normalized, run_id=None: saved.append((data, normalized, run_id)))
    monkeypatch.setattr(cli_module, "start_run",
                        lambda session, source, params=None: SimpleNamespace(
                            id=7, source=source, params=params, status="running", is_complete=False,
                            listings_seen=0, listings_deactivated=0, notes=None))
    monkeypatch.setattr(cli_module, "finish_run",
                        lambda session, run, **kw: (finished.append(kw) if finished is not None else None) or run)


def test_run_uses_collection_and_passes_pages(monkeypatch):
    saved, calls = [], []

    def fake_collect(self, source_url, pages, max_listings=None):
        calls.append((source_url, pages, max_listings))
        yield {"id": "777", "title": "t", "price": "600", "currency": "usd",
               "period": "month", "lat": 40.1, "lon": 44.5}

    _patch(monkeypatch, saved)
    monkeypatch.setattr(ListingPipeline, "collect", fake_collect)

    result = CliRunner().invoke(cli_module.cli, ["run", "--pages", "3"])
    assert result.exit_code == 0, result.output
    assert calls[0][1] == 3
    assert [d["id"] for d, _, _ in saved] == ["777"]       # no hardcoded demo rows
    assert saved[0][2] == 7                                  # records are linked to the run


def test_crawl_state_is_handed_to_finish_run(monkeypatch):
    saved, finished = [], []

    def fake_collect(self, source_url, pages, max_listings=None):
        self.seen_ids.update({"1", "2"})
        self.reached_end = True
        self.finished = True
        yield {"id": "1", "price": 1, "currency": "USD", "period": "month", "lat": 1, "lon": 1}

    _patch(monkeypatch, saved, finished)
    monkeypatch.setattr(ListingPipeline, "collect", fake_collect)
    result = CliRunner().invoke(cli_module.cli, ["run"])
    assert result.exit_code == 0, result.output
    assert finished[0]["seen_ids"] == {"1", "2"}
    assert finished[0]["crawl_complete"] is True


def test_demo_records_only_with_flag_and_use_demo_source(monkeypatch):
    saved = []
    _patch(monkeypatch, saved)
    monkeypatch.setattr(ListingPipeline, "collect", lambda *a, **k: iter(()))

    CliRunner().invoke(cli_module.cli, ["run"])
    assert saved == []

    result = CliRunner().invoke(cli_module.cli, ["run", "--demo"])
    assert result.exit_code == 0
    assert [d["id"] for d, _, _ in saved] == ["101", "103"]
    assert {d["source"] for d, _, _ in saved} == {"demo"}


def test_import_file_goes_through_validation_and_never_deactivates(monkeypatch, tmp_path):
    saved, finished = [], []
    _patch(monkeypatch, saved, finished)
    path = tmp_path / "recs.json"
    path.write_text(json.dumps([
        {"external_id": "A1", "price": "500", "currency": "USD", "period": "month", "lat": 40.1, "lon": 44.5},
        {"external_id": "A2", "price": -1, "currency": "USD", "period": "month", "lat": 40.1, "lon": 44.5},
    ]))
    result = CliRunner().invoke(cli_module.cli, ["import-file", str(path), "--source-name", "fixture"])
    assert result.exit_code == 0, result.output
    assert [d["id"] for d, _, _ in saved] == ["A1"]
    assert finished[0]["crawl_complete"] is None             # file import: no staleness evaluation
    assert "Quarantined / Rejected: 1" in result.output


def test_missing_database_url_fails_cleanly(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    result = CliRunner().invoke(cli_module.cli, ["run"])
    assert result.exit_code != 0
    assert "DATABASE_URL" in result.output
