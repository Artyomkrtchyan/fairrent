import pytest

from .geography import (
    CITY_CENTER, DISTRICTS, GEOGRAPHY_VERSION, METRO_STATIONS, UNIVERSITIES,
    haversine_m, normalize_district, proximity_features,
    reference_points,
)


def test_registry_covers_yerevan_districts_metro_and_university_campuses():
    assert len(DISTRICTS) == 12
    assert len(METRO_STATIONS) == 10
    assert len(UNIVERSITIES) >= 4
    assert GEOGRAPHY_VERSION == "yerevan-geo-v1"
    points = reference_points()
    assert len(points) == 15
    assert all(point["source_url"] and point["coordinate_confidence"] == "approximate"
               for point in points)


def test_armenian_and_english_district_names_normalize_without_guessing():
    assert normalize_district("Քանաքեռ-Զեյթուն") == "kanaker-zeytun"
    assert normalize_district("Malatia Sebastia") == "malatia-sebastia"
    assert normalize_district("not a Yerevan district") is None
    assert normalize_district(None) is None


def test_known_center_and_station_examples_produce_zero_metres():
    center = proximity_features(CITY_CENTER[0], CITY_CENTER[1])
    assert center["distance_center_m"] == 0
    assert center["distance_metro_m"] == 0
    station = METRO_STATIONS[2]
    result = proximity_features(station[2], station[3])
    assert result["distance_metro_m"] == 0
    assert result["nearest_metro_id"] == station[0]
    assert result["geo_status"] == "resolved"


def test_known_location_has_plausible_university_distance_in_metres():
    result = proximity_features(40.17767, 44.51562)
    assert result["distance_university_m"] == pytest.approx(1_019.7, abs=0.1)
    assert result["nearest_university_id"] == "ysu-main"
    assert haversine_m(40.17767, 44.51562, 40.17767, 44.51562) == 0


def test_missing_or_invalid_coordinates_are_flagged_and_distances_are_null():
    for result in (proximity_features(None, None), proximity_features(100, 44.5)):
        assert result["geo_status"] == "unresolved"
        assert result["distance_metro_m"] is None
        assert result["distance_university_m"] is None
        assert result["distance_center_m"] is None

