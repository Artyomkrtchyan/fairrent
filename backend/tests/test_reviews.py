"""Authorization, contract and error behavior without a live database."""
import json
from pathlib import Path
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from backend.main import app
from backend import review_routes, reviewer_auth
from backend.review_repository import ReviewConflict

ACTOR = UUID(int=99)
TOKEN = "x" * 43


def validate(payload, name):
    spec = json.loads((Path(__file__).resolve().parents[2] / "contracts/openapi.json").read_text())
    Draft202012Validator({"$ref": f"#/components/schemas/{name}", "components": spec["components"]},
                        format_checker=FormatChecker()).validate(payload)


@pytest.fixture
def record():
    fixtures = json.loads((Path(__file__).resolve().parents[2] / "contracts/fixtures.json").read_text())
    item = fixtures["reviews"]["value"]["items"][0]
    item["listing"]["price_status"] = "insufficient_data"
    return item


@pytest.fixture
def client(record):
    class Sessions:
        principal = (ACTOR, "reviewer")
        def authenticate(self, token):
            assert token == TOKEN
            return self.principal
    class Queue:
        failure = None
        def search(self, query):
            if self.failure:
                raise self.failure
            return [record], 1
        def update(self, id, update, actor):
            assert actor == ACTOR
            if self.failure:
                raise self.failure
            return record
    sessions, queue = Sessions(), Queue()
    app.dependency_overrides[reviewer_auth.sessions] = lambda: sessions
    app.dependency_overrides[review_routes.repository] = lambda: queue
    try:
        with TestClient(app) as http:
            http.headers["Authorization"] = f"Bearer {TOKEN}"
            yield http, sessions, queue
    finally:
        app.dependency_overrides.clear()


def test_queue_contract_and_authentication(client):
    http, sessions, _ = client
    result = http.get("/api/v1/reviews")
    assert result.status_code == 200
    validate(result.json(), "ReviewPage")
    assert result.json()["total"] == 1
    assert "token" not in result.text
    sessions.principal = None
    result = http.get("/api/v1/reviews")
    assert result.status_code == 401
    assert result.headers["www-authenticate"] == "Bearer"
    validate(result.json(), "Error")
    sessions.principal = (ACTOR, "viewer")
    assert http.get("/api/v1/reviews").status_code == 403


@pytest.mark.parametrize("header", [None, "", "Basic abc", "Bearer tiny", "Bearer " + "ü" * 43])
def test_malformed_authentication(client, header):
    http, _, _ = client
    http.headers.pop("Authorization")
    headers = {} if header is None else {"Authorization": header.encode("utf-8")}
    result = http.get("/api/v1/reviews", headers=headers)
    assert result.status_code == 401


def test_duplicate_authorization_is_rejected(client):
    http, _, _ = client
    result = http.get("/api/v1/reviews", headers=[("Authorization", f"Bearer {TOKEN}"), ("Authorization", f"Bearer {TOKEN}")])
    assert result.status_code == 401


@pytest.mark.parametrize("query", ["page=0", "page_size=101", "status=bogus", "listing_id=bad", "unknown=x", "page=1&page=2"])
def test_invalid_queue_queries(client, query):
    assert client[0].get("/api/v1/reviews?" + query).status_code == 422


def test_update_errors_and_body_validation(client, record):
    http, _, queue = client
    url = f"/api/v1/reviews/{record['id']}"
    body = dict(status="resolved", decision="dismissed", reason="Checked source evidence", version=1)
    for changes in ({"reason": "   "}, {"decision": None}, {"status": "in_review"},
                    {"version": True}, {"version": 0}, {"reason": "x" * 2001}, {"actor_id": str(ACTOR)}):
        assert http.patch(url, json={**body, **changes}).status_code == 422
    assert http.patch(url + "?ignored=true", json=body).status_code == 422
    queue.failure = ReviewConflict("Refresh review")
    result = http.patch(url, json=body)
    assert result.status_code == 409
    validate(result.json(), "Error")
    queue.failure = psycopg.OperationalError("private connection details")
    result = http.patch(url, json=body)
    assert result.status_code == 503
    assert "private" not in result.text


def test_reviewer_cors_preflight(client):
    result = client[0].options("/api/v1/reviews/00000000-0000-0000-0000-000000000001", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "PATCH",
        "Access-Control-Request-Headers": "authorization,content-type",
    })
    assert result.status_code == 200
    assert "PATCH" in result.headers["access-control-allow-methods"]
