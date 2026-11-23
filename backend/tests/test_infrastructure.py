import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from backend.main import app
from data_pipeline.geography import METRO_STATIONS, UNIVERSITIES


BBOX = "44.35,40.05,44.66,40.30"


def test_map_registry_includes_all_metro_and_expanded_university_points():
    spec = json.loads((Path(__file__).resolve().parents[2] / "contracts/openapi.json").read_text())
    validator = Draft202012Validator({
        "$ref": "#/components/schemas/InfrastructurePage", "components": spec["components"],
    })
    with TestClient(app) as client:
        response = client.get("/api/v1/infrastructure", params={"bbox": BBOX, "page_size": 100})
        assert response.status_code == 200, response.text
        result = response.json()
        validator.validate(result)
        assert result["total"] == len(METRO_STATIONS) + len(UNIVERSITIES)
        assert {point["id"] for point in result["items"]} == {
            point[0] for point in (*METRO_STATIONS, *UNIVERSITIES)
        }
        assert not result["has_more"]
        for kind, expected in (("metro", METRO_STATIONS), ("university", UNIVERSITIES)):
            points = client.get("/api/v1/infrastructure", params={
                "bbox": BBOX, "type": kind, "page_size": 100,
            }).json()
            assert points["total"] == len(expected)
            assert all(point["type"] == kind for point in points["items"])


def test_map_bounds_and_pagination():
    with TestClient(app) as client:
        first = client.get("/api/v1/infrastructure", params={"bbox": BBOX, "page_size": 1}).json()
        second = client.get("/api/v1/infrastructure", params={
            "bbox": BBOX, "page_size": 1, "page": 2,
        }).json()
        assert first["has_more"] and second["has_more"]
        assert first["items"][0]["id"] != second["items"][0]["id"]
        empty = client.get("/api/v1/infrastructure?bbox=44.0,40.0,44.1,40.1").json()
        assert empty["items"] == [] and empty["total"] == 0
        point = first["items"][0]
        lon, lat = point["longitude"], point["latitude"]
        boundary = client.get("/api/v1/infrastructure", params={
            "bbox": f"{lon},{lat},{lon + .001},{lat + .001}",
        }).json()
        assert point["id"] in {item["id"] for item in boundary["items"]}


@pytest.mark.parametrize("query", [
    "", "bbox=bad", "bbox=44,40,45,41", "bbox=44.5,40.1,44.6,40.2&page=0",
    f"bbox={BBOX}&type=unknown", f"bbox={BBOX}&page_size=101",
    f"bbox={BBOX}&page=1&page=2", f"bbox={BBOX}&unexpected=1",
])
def test_invalid_map_requests_are_rejected(query):
    with TestClient(app) as client:
        response = client.get("/api/v1/infrastructure?" + query)
        assert response.status_code == 422
        assert response.json()["code"] == "validation_error"
