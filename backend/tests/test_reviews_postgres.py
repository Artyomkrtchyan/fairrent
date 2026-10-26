"""Real transactions: session lifecycle, queue filters, concurrent updates, audit rollback."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.review_models import ReviewUpdate
from backend.review_repository import ReviewConflict, ReviewRepository, enqueue
from backend.reviewer_auth import issue_session, token_digest
from backend.tests.test_listing_postgres import database, populated, validate_contract
from backend.tests.test_reviews import record


@pytest.fixture
def setup(database, populated, record):
    migration = (Path(__file__).resolve().parents[1] / "sql/003_review_workflow.sql").read_text()
    actor = uuid4()
    with database() as connection:
        connection.execute(migration)
        connection.execute(migration)
        session_id, token = issue_session(connection, actor)
        signals = [{**s, "listing_id": populated[0].id} for s in record["signals"]]
        review_id = enqueue(connection, populated[0].id, signals)
        assert enqueue(connection, populated[0].id, signals) == review_id
    return actor, review_id, session_id, token


def test_sessions_queue_and_decision_audit(database, setup):
    actor, review_id, session_id, token = setup
    with TestClient(app) as http:
        assert http.get("/api/v1/reviews").status_code == 401
        headers = {"Authorization": f"Bearer {token}"}
        result = http.get("/api/v1/reviews?status=pending", headers=headers)
        assert result.status_code == 200
        validate_contract(result.json(), "ReviewPage")
        assert result.json()["total"] == 1
        assert http.get("/api/v1/reviews?page=2", headers=headers).json()["items"] == []
        assert http.get(f"/api/v1/reviews?listing_id={uuid4()}", headers=headers).json()["total"] == 0
        url = f"/api/v1/reviews/{review_id}"
        body = dict(status="in_review", decision=None, reason="Checking source", version=1)
        result = http.patch(url, headers=headers, json=body)
        assert result.status_code == 200, result.text
        validate_contract(result.json(), "Review")
        assert result.json()["history"][0]["actor_id"] == str(actor)
        assert result.json()["version"] == 2
        assert http.patch(url, headers=headers, json=body).status_code == 409
        body.update(status="resolved", decision="dismissed", version=2)
        result = http.patch(url, headers=headers, json=body)
        assert result.status_code == 200
        validate_contract(result.json(), "Review")
        assert len(result.json()["history"]) == 2
        assert result.json()["reviewed_at"].endswith("Z")
        assert http.patch(url, headers=headers, json={**body, "version": 3}).status_code == 409
        assert http.patch(f"/api/v1/reviews/{uuid4()}", headers=headers, json=body).status_code == 404
        with database() as connection:
            stored = connection.execute("SELECT token_hash FROM api_reviewer_sessions WHERE id=%s", (session_id,)).fetchone()[0]
            assert stored == token_digest(token) and stored != token
            connection.execute("UPDATE api_reviewer_sessions SET role='viewer' WHERE id=%s", (session_id,))
        assert http.get("/api/v1/reviews", headers=headers).status_code == 403
        with database() as connection:
            connection.execute("UPDATE api_reviewer_sessions SET role='reviewer', created_at=CURRENT_TIMESTAMP - interval '1 day', expires_at=CURRENT_TIMESTAMP - interval '1 hour' WHERE id=%s", (session_id,))
        assert http.get("/api/v1/reviews", headers=headers).status_code == 401


def test_concurrent_decisions_only_commit_once(database, setup):
    actor, review_id, _, _ = setup
    update = ReviewUpdate(status="resolved", decision="needs_follow_up", reason="Controlled concurrency check", version=1)
    def decide():
        try:
            ReviewRepository().update(review_id, update, actor)
            return "saved"
        except ReviewConflict:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: decide(), range(2)))
    assert sorted(outcomes) == ["conflict", "saved"]
    with database() as connection:
        assert connection.execute("SELECT count(*) FROM api_review_events WHERE review_id=%s", (review_id,)).fetchone()[0] == 1


def test_audit_failure_rolls_back_decision(database, setup):
    actor, review_id, _, _ = setup
    with database() as connection:
        connection.execute("ALTER TABLE api_review_events ADD CONSTRAINT force_audit_failure CHECK (false)")
    update = ReviewUpdate(status="resolved", decision="dismissed", reason="Synthetic rollback check", version=1)
    import psycopg
    with pytest.raises(psycopg.errors.CheckViolation):
        ReviewRepository().update(review_id, update, actor)
    with database() as connection:
        assert connection.execute("SELECT status, version FROM api_review_queue WHERE id=%s", (review_id,)).fetchone() == ("pending", 1)


def test_revoked_session_is_rejected(database, setup):
    _, _, session_id, token = setup
    with database() as connection:
        connection.execute("UPDATE api_reviewer_sessions SET revoked_at=CURRENT_TIMESTAMP WHERE id=%s", (session_id,))
    with TestClient(app) as http:
        assert http.get("/api/v1/reviews", headers={"Authorization": f"Bearer {token}"}).status_code == 401
