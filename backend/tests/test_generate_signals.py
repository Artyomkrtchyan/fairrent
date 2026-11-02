"""C03 -> B06 mapping, missing inputs, source contradictions and train-fitted district support."""
from backend.generate_signals import evaluate, main
from backend.listing_models import ListingData
from ml import ontology_rules as rules


def test_independent_description_produces_versioned_signals(listing_document):
    record = ListingData.model_validate({**listing_document, "title": "2 rooms, Kentron, 65 m2",
        "description": "3 rooms, Arabkir, 120 m2", "area_sqm": 65, "rooms": 2, "district_id": "kentron"})
    signals = evaluate(record, created_at="2026-11-02T10:00:00Z")
    assert {s["rule_id"] for s in signals} == {"DESC-AREA-MATCH", "DESC-ROOMS-MATCH", "DESC-DISTRICT-MATCH"}
    assert all(s["listing_id"] == str(record.id) and s["rules_version"] == rules.RULES_VERSION for s in signals)
    assert all(s["category"] == "risk_evidence" for s in signals)
    assert all(any(e.startswith("source=description") for e in s["evidence"]) for s in signals)


def test_missing_values_and_high_price_do_not_invent_risk(listing_document):
    record = ListingData.model_validate({**listing_document, "title": None, "description": None,
        "area_sqm": None, "rooms": None, "district_id": None, "latitude": None, "longitude": None,
        "coordinate_confidence": "unknown", "price_monthly_normalized": 100000})
    assert evaluate(record) == []
    record.status = "inactive"
    record.area_sqm = 2000
    assert evaluate(record) == []


def test_district_check_uses_supplied_training_reference(listing_document):
    record = ListingData.model_validate({**listing_document, "title": None, "description": None,
        "district_id": "nor-nork", "latitude": 40.18, "longitude": 44.51})
    support = rules.DistrictSupport.fit(
        [{"latitude": 40.18, "longitude": 44.51, "district": "kentron"}] * 25,
        reference_version="train-fixture")
    signals = evaluate(record, district_support=support)
    district = next(s for s in signals if s["rule_id"] == "GEO-DISTRICT-SUPPORT")
    assert "reference_version=train-fixture" in district["evidence"]
    assert not any(s["rule_id"] == "GEO-DISTRICT-SUPPORT" for s in evaluate(record))


def test_bad_reference_fails_before_connecting(tmp_path, monkeypatch, capsys):
    import json
    import backend.generate_signals as producer
    def no_database(**kwargs):
        raise AssertionError("Invalid reference must fail before opening the database")
    monkeypatch.setattr(producer.psycopg, "connect", no_database)
    path = tmp_path / "reference.json"
    path.write_text(json.dumps({"rules_version": "old"}))
    assert main(["--district-support", str(path)]) == 1
    assert "previous signals and reviews preserved" in capsys.readouterr().err
