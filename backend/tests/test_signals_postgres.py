"""B06 -> persistence -> public details -> reviewer queue, with real PostgreSQL transactions."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.generate_signals import evaluate, generate, main, migrate
from backend.listing_models import ListingData
from backend.listing_repository import publish_listing
from backend.review_models import ReviewUpdate
from backend.review_repository import ReviewRepository
from backend.signal_repository import reconcile_signals
from backend.tests.test_listing_postgres import database, validate_contract


@pytest.fixture
def contradictory(database, listing_document):
    record = ListingData.model_validate({**listing_document, "title": "2 rooms, Kentron, 65 m2",
        "description": "3 rooms, Arabkir, 120 m2", "area_sqm": 65, "rooms": 2, "district_id": "kentron"})
    with database() as connection:
        migrate(connection)
        migrate(connection)
        publish_listing(connection, record)
    return record


def run(database):
    with database() as connection:
        return generate(connection)


def resolve(review_id):
    return ReviewRepository().update(review_id, ReviewUpdate(
        status="resolved", decision="dismissed", reason="Controlled evidence review", version=1), uuid4())


def test_replays_and_resolved_reviews_are_idempotent(database, contradictory):
    assert run(database)["queued"] == 3
    with database() as connection:
        review_id, evidence = connection.execute("SELECT id, signals FROM api_review_queue").fetchone()
    assert run(database)["queued"] == 0
    with TestClient(app) as http:
        response = http.get(f"/api/v1/listings/{contradictory.id}")
        assert response.status_code == 200, response.text
        validate_contract(response.json(), "ListingDetail")
        assert {s["id"] for s in response.json()["signals"]} == {s["id"] for s in evidence}
        assert http.get("/api/v1/reviews").status_code == 401
    resolve(review_id)
    assert run(database)["queued"] == 0
    with database() as connection:
        assert connection.execute("SELECT count(*) FROM api_review_queue").fetchone()[0] == 1
        assert connection.execute("SELECT signals FROM api_review_queue").fetchone()[0] == evidence
        assert connection.execute("SELECT count(*) FROM api_review_events").fetchone()[0] == 1


def test_changed_evidence_waits_for_open_review_without_rewriting_it(database, contradictory):
    run(database)
    with database() as connection:
        first_id, evidence = connection.execute("SELECT id, signals FROM api_review_queue").fetchone()
        contradictory.description = "4 rooms, Arabkir, 150 m2"
        publish_listing(connection, contradictory)
    with database() as connection:
        assert connection.execute("SELECT count(*) FROM api_listing_signals WHERE active").fetchone()[0] == 0
    result = run(database)
    assert result["queued"] == 0 and result["deferred"] == 2
    with database() as connection:
        assert connection.execute("SELECT signals FROM api_review_queue WHERE id=%s", (first_id,)).fetchone()[0] == evidence
    resolve(first_id)
    assert run(database)["queued"] == 2
    with database() as connection:
        batches = connection.execute("SELECT signal_ids FROM api_review_queue").fetchall()
        assert len(batches) == 2
        assert set(batches[0][0]).isdisjoint(batches[1][0])
    assert run(database)["queued"] == 0


def test_corrected_or_inactive_listing_retires_public_signals_but_keeps_history(database, contradictory):
    run(database)
    with database() as connection:
        contradictory.description = "2 rooms, Kentron, 65 m2"
        publish_listing(connection, contradictory)
    with TestClient(app) as http:
        assert http.get(f"/api/v1/listings/{contradictory.id}").json()["signals"] == []
    assert run(database)["active"] == 0
    with database() as connection:
        assert connection.execute("SELECT jsonb_array_length(signals) FROM api_review_queue").fetchone()[0] == 3
        contradictory.description = "3 rooms, Arabkir, 120 m2"
        publish_listing(connection, contradictory)
    assert run(database)["active"] == 3
    with database() as connection:
        contradictory.status = "inactive"
        publish_listing(connection, contradictory)
    assert run(database)["active"] == 0


def test_observation_refresh_preserves_signals_and_first_observation_time(database, contradictory):
    signals = evaluate(contradictory, created_at="2026-11-02T10:00:00Z")
    with database() as connection:
        reconcile_signals(connection, contradictory.id, signals)
        contradictory.last_seen_at = contradictory.last_seen_at.replace(year=2027)
        publish_listing(connection, contradictory)
    with database() as connection:
        assert connection.execute("SELECT count(*) FROM api_listing_signals WHERE active").fetchone()[0] == 3
        later = evaluate(contradictory, created_at="2026-11-03T10:00:00Z")
        assert reconcile_signals(connection, contradictory.id, later)["queued"] == 0
        assert {r[0] for r in connection.execute("SELECT document->>'created_at' FROM api_listing_signals")} == {"2026-11-02T10:00:00Z"}


def test_concurrent_producers_create_one_review(database, contradictory):
    signals = evaluate(contradictory)
    def produce(_):
        with database() as connection:
            return reconcile_signals(connection, contradictory.id, signals)["queued"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(produce, range(2))) == [0, 3]
    with database() as connection:
        assert connection.execute("SELECT count(*) FROM api_review_queue").fetchone()[0] == 1


def test_producer_failure_rolls_back_signals_and_queue(database, contradictory, monkeypatch):
    import backend.generate_signals as producer
    original = producer.reconcile_signals
    def fail_after_write(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Controlled producer failure")
    monkeypatch.setattr(producer, "reconcile_signals", fail_after_write)
    with pytest.raises(RuntimeError), database() as connection:
        generate(connection)
    with database() as connection:
        assert connection.execute("SELECT count(*) FROM api_listing_signals").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM api_review_queue").fetchone()[0] == 0


def test_unpublished_listing_does_not_block_publication_or_destroy_review(database, contradictory):
    from backend.review_models import ReviewQuery
    run(database)
    with database() as connection:
        review_id, evidence = connection.execute("SELECT id, signals FROM api_review_queue").fetchone()
        connection.execute("DELETE FROM api_listing_projection WHERE id=%s", (contradictory.id,))
    with TestClient(app) as http:
        assert http.get(f"/api/v1/listings/{contradictory.id}").status_code == 404
    records, count = ReviewRepository().search(ReviewQuery())
    assert count == 1 and records[0].listing.status == "inactive"
    assert records[0].listing.id == contradictory.id
    resolve(review_id)
    with database() as connection:
        assert connection.execute("SELECT signals FROM api_review_queue").fetchone()[0] == evidence
        assert connection.execute("SELECT count(*) FROM api_review_events").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM api_listing_signals").fetchone()[0] == 0


def test_upgrade_backfills_existing_review_snapshots(database, contradictory):
    run(database)
    with database() as connection:
        # Reproduce the pre-004 queue shape with existing evidence.
        connection.execute("ALTER TABLE api_review_queue DROP COLUMN listing_snapshot")
        connection.execute("ALTER TABLE api_review_queue ADD CONSTRAINT api_review_queue_listing_id_fkey FOREIGN KEY(listing_id) REFERENCES api_listing_projection(id)")
        migrate(connection)
        snapshot = connection.execute("SELECT listing_snapshot FROM api_review_queue").fetchone()[0]
        assert snapshot == contradictory.model_dump(mode="json")
        connection.execute("DELETE FROM api_listing_projection WHERE id=%s", (contradictory.id,))


def test_cli_reports_committed_counts_and_replays(database, contradictory, capsys):
    import json
    assert main([]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["queued"] == 3 and summary["price_checks"] == "withheld_no_package"
    assert main([]) == 0
    assert json.loads(capsys.readouterr().out)["queued"] == 0


def test_reused_id_cannot_replace_evidence(database, contradictory):
    run(database)
    signals = evaluate(contradictory)
    signals[0]["explanation"] = "Different evidence under the same ID"
    with pytest.raises(ValueError, match="different evidence"), database() as connection:
        reconcile_signals(connection, contradictory.id, signals)
    with database() as connection:
        assert connection.execute("SELECT count(*) FROM api_listing_signals WHERE active").fetchone()[0] == 3
        assert connection.execute("SELECT count(*) FROM api_review_queue").fetchone()[0] == 1
