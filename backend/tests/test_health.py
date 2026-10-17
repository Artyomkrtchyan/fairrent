import psycopg

from fastapi.testclient import TestClient
from backend.main import app
from backend import main
from unittest.mock import MagicMock

def test_health_returns_ok():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_ready_returns_503_when_database_is_unavailable(monkeypatch):
    def failed_connect(*args, **kwargs):
        raise psycopg.OperationalError("Database connection failed")

    monkeypatch.setattr(main.psycopg, "connect", failed_connect)

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "database": "unavailable",
    }

def test_ready_returns_ok_when_database_is_available(monkeypatch):
    connection = MagicMock()
    cursor = (
        connection.__enter__.return_value
        .cursor.return_value.__enter__.return_value
    )
    cursor.fetchone.return_value = (1,)

    connect = MagicMock(return_value=connection)
    monkeypatch.setattr(main.psycopg, "connect", connect)

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    connect.assert_called_once_with(connect_timeout=3)
    cursor.execute.assert_called_once_with("SELECT 1")
    cursor.fetchone.assert_called_once()