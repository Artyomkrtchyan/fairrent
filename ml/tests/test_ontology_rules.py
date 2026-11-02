"""B06 rule engine: facts, consistency checks, signals, explanation shape."""
import json
import uuid
from pathlib import Path

import pytest

from ml import intervals as iv
from ml import ontology_rules as r

LISTING_ID = "11111111-1111-4111-8111-111111111111"
NOW = "2026-01-01T00:00:00Z"
CONTRACT = json.loads((Path(__file__).resolve().parents[2] / "contracts" / "openapi.json").read_text("utf-8"))
SCHEMAS = CONTRACT["components"]["schemas"]
INTERVAL = {"lower_bound_usd": 400.0, "upper_bound_usd": 700.0, "confidence_level": 0.9,
            "calibration_version": "cal-test"}


def _status(items, rule_id):
    return next(i for i in items if i["rule_id"] == rule_id)["status"]


def _conforms(obj, schema_name):
    schema = SCHEMAS[schema_name]
    assert set(schema["required"]) <= set(obj)
    assert set(obj) <= set(schema["properties"])
    for key, spec in schema["properties"].items():
        if "enum" in spec and key in obj:
            assert obj[key] in spec["enum"]


def test_registry_is_versioned_and_complete():
    reg = r.registry()
    assert r.RULES_VERSION and len(reg) == len(r.RULES)
    for item in reg:
        assert item["rule_id"] and item["version"] and item["description"] and item["limitations"]


def test_proximity_fact_holds_with_evidence():
    facts = r.proximity_facts(40.1776, 44.5126)
    metro = next(f for f in facts if f["rule_id"] == "GEO-PROX-METRO")
    assert metro["status"] == "holds" and metro["value_m"] < 500
    assert any(e.startswith("nearest_metro=") for e in metro["evidence"])


def test_proximity_missing_coordinates_is_unknown_not_false():
    for f in r.proximity_facts():
        assert f["status"] == "unknown" and f["reason"] == "missing_coordinates"


def test_district_support_flags_only_with_enough_reference():
    rows = [{"latitude": 40.18, "longitude": 44.51, "district": "kentron"}] * 10
    support = r.DistrictSupport.fit(rows, reference_version="t", min_reference_listings=5)
    assert support.check(40.18, 44.51, "kentron")["status"] == "clear"
    assert support.check(40.18, 44.51, "arabkir")["status"] == "flagged"
    assert support.check(41.5, 45.5, "arabkir")["status"] == "unknown"          # sparse area
    assert support.check(None, None, "kentron")["status"] == "unknown"
    clone = r.DistrictSupport.from_json(json.loads(json.dumps(support.to_json())))
    assert clone.check(40.18, 44.51, "arabkir")["status"] == "flagged"


def test_district_support_leave_one_out():
    rows = [{"latitude": 40.18, "longitude": 44.51, "district": "kentron"}] * 5 + \
           [{"latitude": 40.18, "longitude": 44.51, "district": "arabkir"}]
    support = r.DistrictSupport.fit(rows, min_reference_listings=5)
    # the single arabkir reference listing supports itself unless it is excluded
    assert support.check(40.18, 44.51, "arabkir")["status"] == "clear"
    assert support.check(40.18, 44.51, "arabkir", exclude_self=True)["status"] == "flagged"


def test_description_mismatches_are_flagged():
    out = r.description_checks("2 սենյականոց բնակարան, Կենտրոն, 120 քմ", area_sqm=65, rooms=3, district="arabkir")
    assert _status(out, "DESC-AREA-MATCH") == "flagged"
    assert _status(out, "DESC-ROOMS-MATCH") == "flagged"


def test_description_without_text_facts_is_unknown():
    out = r.description_checks("Nice flat", area_sqm=65, rooms=3)
    assert {c["status"] for c in out} == {"unknown"}


def test_area_plausibility():
    assert r.area_plausibility(65, 2)["status"] == "clear"
    assert r.area_plausibility(1670, 3)["status"] == "flagged"
    assert r.area_plausibility(None, 2)["status"] == "unknown"


def test_price_anomaly_uses_interval_and_stays_separate_from_fraud():
    assert r.price_anomaly_check(550, INTERVAL)["status"] == "clear"
    high = r.price_anomaly_check(1800, INTERVAL)
    assert high["status"] == "flagged" and high["price_status"] == "above_range"
    assert "not" in high["explanation"] and "fraud" in high["explanation"]
    assert r.price_anomaly_check(1800, None)["status"] == "unknown"
    assert r.price_anomaly_check(None, INTERVAL)["status"] == "unknown"


def test_risk_signal_matches_contract_and_is_deterministic():
    check = r.price_anomaly_check(1800, INTERVAL)
    a = r.to_risk_signal(check, listing_id=LISTING_ID, created_at=NOW)
    b = r.to_risk_signal(check, listing_id=LISTING_ID, created_at=NOW)
    _conforms(a, "RiskSignal")
    assert a["id"] == b["id"] and a["category"] == "price_anomaly"
    uuid.UUID(a["id"])
    other = r.to_risk_signal(r.price_anomaly_check(2500, INTERVAL), listing_id=LISTING_ID, created_at=NOW)
    assert other["id"] != a["id"]


def test_only_flagged_checks_become_signals():
    with pytest.raises(ValueError):
        r.to_risk_signal(r.price_anomaly_check(550, INTERVAL), listing_id=LISTING_ID, created_at=NOW)
    with pytest.raises(ValueError):
        r.to_risk_signal(r.price_anomaly_check(1800, INTERVAL), listing_id="x", created_at=NOW)
    with pytest.raises(ValueError):
        r.to_risk_signal(r.price_anomaly_check(1800, INTERVAL), listing_id=LISTING_ID, created_at="2026-01-01")


def test_evaluate_listing_with_missing_data_does_not_invent_findings():
    res = r.evaluate_listing({"asking_price_usd": 600})
    assert res["findings"] == []
    assert all(f["status"] == "unknown" for f in res["facts"])


def test_explanation_separates_rule_facts_from_learned_effects():
    learned = [{"feature": "area_sqm", "impact_pct": 41.0, "direction": "positive"},
               {"feature": "distance_metro_m", "impact_pct": 9.5, "direction": "negative"}]
    inp = {"latitude": 40.1776, "longitude": 44.5126, "distance_metro_m": 257.0, "area_sqm": 1670, "rooms": 3}
    exp = r.explain_valuation(inp, learned_attributions=learned)
    assert exp["learned_price_effects"] == learned
    for f in exp["factors"]:
        _conforms(f, "Factor")
    origins = {f["origin"] for f in exp["factors"]}
    assert origins == {"ontology", "model"}
    assert all(f["origin"] == "ontology" for f in exp["factors"] if f["code"].startswith("geo_prox"))
    assert all(a["feature"] in {f["code"] for f in exp["factors"] if f["origin"] == "model"} for a in learned)
    assert "not price effects" in exp["text"]


def test_bad_attribution_is_rejected():
    with pytest.raises(ValueError):
        r.explain_valuation({}, learned_attributions=[{"feature": "x", "impact_pct": -1, "direction": "positive"}])
    with pytest.raises(ValueError):
        r.explain_valuation({}, learned_attributions=[{"feature": "x", "impact_pct": 1, "direction": "up"}])


def test_attributions_group_missing_indicators_and_normalise():
    from ml.attributions import attributions_from_shap
    out = attributions_from_shap(["area_sqm", "area_sqm_missing", "rooms", "district"], [30.0, 10.0, -20.0, 0.0])
    assert [a["feature"] for a in out] == ["area_sqm", "rooms", "district"]
    assert out[0] == {"feature": "area_sqm", "impact_pct": 66.67, "direction": "positive"}
    assert out[1]["direction"] == "negative" and out[2]["direction"] == "neutral"
    assert abs(sum(a["impact_pct"] for a in out) - 100) < 0.05
    for a in out:
        _conforms(a, "Attribution")
    with pytest.raises(ValueError):
        attributions_from_shap(["a"], [float("nan")])
    assert attributions_from_shap(["a"], [0.0]) == []


def test_description_is_checked_independently_from_title():
    listing = {"title": "2 սենյականոց բնակարան, Կենտրոն, 65 քմ",
               "description": "3 սենյականոց բնակարան, Արաբկիր, 120 քմ",
               "area_sqm": 65, "rooms": 2, "district": "kentron"}
    res = r.evaluate_listing(listing)
    for rule in ("DESC-AREA-MATCH", "DESC-ROOMS-MATCH", "DESC-DISTRICT-MATCH"):
        assert _status(res["checks"], rule) == "flagged", rule
    flagged = next(c for c in res["checks"] if c["rule_id"] == "DESC-AREA-MATCH")
    assert any(e.startswith("source=description") for e in flagged["evidence"])


def test_matching_title_and_description_stay_clear_and_missing_text_unknown():
    both = {"title": "2 սենյականոց, Կենտրոն, 65 քմ", "description": "2 սենյականոց, Կենտրոն, 65 քմ",
            "area_sqm": 65, "rooms": 2, "district": "kentron"}
    assert _status(r.evaluate_listing(both)["checks"], "DESC-AREA-MATCH") == "clear"
    none = r.evaluate_listing({"area_sqm": 65})
    assert _status(none["checks"], "DESC-AREA-MATCH") == "unknown"


def test_canonical_district_ids_are_accepted():
    from data_pipeline import geography as geo
    for key in geo.DISTRICTS:
        assert r._district_id(key) == key
    assert r._district_id("Nor Nork") == "nor-nork"
    rows = [{"latitude": 40.2, "longitude": 44.55, "district": "nor-nork"}] * 25
    support = r.DistrictSupport.fit(rows)
    assert support.n_reference == 25
    assert support.check(40.2, 44.55, "nor-nork")["status"] == "clear"
    assert support.check(40.2, 44.55, "kentron")["status"] == "flagged"
