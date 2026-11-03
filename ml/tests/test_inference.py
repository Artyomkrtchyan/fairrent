"""B07: package build/load, the assess() entry point, failure behaviour and contract conformance."""
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

pytest.importorskip("catboost")
pytest.importorskip("geoalchemy2")

from ml import calibrate_intervals as ci  # noqa: E402
from ml import inference as inf  # noqa: E402
from ml import package_inference as pk  # noqa: E402
from ml import train_compare as tc  # noqa: E402
from ml.tests.test_calibrate_intervals import _args, _snapshot  # noqa: E402

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
BASE = {"latitude": 40.18, "longitude": 44.51, "as_of": "2026-10-31T09:47:00Z", "radius_m": 1000, "window_days": 30}
COMPS = [{"price_usd": p, "area_sqm": a} for p, a in [(500, 50), (600, 50), (700, 50), (650, 55)]]
OPENAPI = json.loads((Path(__file__).resolve().parents[2] / "contracts" / "openapi.json").read_text("utf-8"))


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = tmp_path_factory.mktemp("b07")
    snapshot = _snapshot(root)
    tc.run(tc.argparse.Namespace(synthetic=False, snapshot=str(snapshot), version="b04-b07-test",
                                 output_dir=str(root / "b04")))
    b04 = root / "b04" / "b04-b07-test"
    holder = type("W", (), {})()
    holder.__dict__.update(root=root, snapshot=snapshot, b04=b04)
    ci.run(_args(holder.__dict__, "b05-b07-test"))
    # The tiny synthetic market is solved by the baseline, so B04's decision is not "ml" here. These tests
    # exercise the package/serving code, not model quality: mark the decision as ml (and re-checksum).
    meta = json.loads((b04 / "metadata.json").read_text())
    meta["serving_decision"] = "ml"
    (b04 / "metadata.json").write_text(json.dumps(meta, indent=2, sort_keys=True))
    sums = json.loads((b04 / "SHA256SUMS.json").read_text())
    sums["metadata.json"] = ci._sha256(b04 / "metadata.json")
    (b04 / "SHA256SUMS.json").write_text(json.dumps(sums, indent=2))
    out = pk.build(b04, root / "b05" / "b05-b07-test", snapshot, "b07-test", root / "b07")
    return {"root": root, "snapshot": snapshot, "b04": b04, "b05": root / "b05" / "b05-b07-test", "pkg": out}


@pytest.fixture(scope="module")
def package(world):
    return inf.load_package(world["pkg"])


def _validator(name):
    pytest.importorskip("jsonschema")      # listed in ml/requirements-train.txt, so CI always runs these checks
    from jsonschema import Draft202012Validator, FormatChecker
    return Draft202012Validator({"$ref": f"#/components/schemas/{name}", "components": OPENAPI["components"]},
                                format_checker=FormatChecker())


def _full_response(result):
    """What the backend adds (contract-semantics.md) so the whole ValuationResponse can be validated."""
    data = {k: result[k] for k in ("coordinates", "versions", "valuation_assessment", "observed_market_statistics",
                                   "ml_prediction_interval", "feature_attributions", "area_reference", "explanation")}
    data.update(request_id="req_test", kind=inf.kind_for(result),
                cohort={"radius_m": 1000, "period_start": "2026-10-01", "period_end": "2026-10-31",
                        "minimum_sample_size": 3, "selection_version": "test",
                        "duplicate_policy": "latest_observation_per_duplicate_group",
                        "inventory_policy": "active_at_data_as_of"},
                freshness={"data_as_of": BASE["as_of"], "generated_at": "2026-11-02T12:00:00Z", "is_stale": False,
                           "max_age_days": 60, "policy_version": "test"},
                price_status="insufficient_data")
    return data


FULL = {**BASE, "area_sqm": 65, "rooms": 2, "district": "Kentron", "floor": 3, "total_floors": 9}


def test_package_is_checksummed_versioned_and_loads(world, package):
    m = package.manifest
    assert m["package_version"] == "b07-test" and m["calibration_version"] and m["rules_version"]
    assert m["snapshot_sha256"] and m["data_as_of"].endswith("Z") and m["thresholds"]["min_comparables"] == 3
    assert package.versions["model_version"].endswith("-catboost")
    with pytest.raises(ci.ArtifactError):          # immutable versions
        pk.build(world["b04"], world["b05"], world["snapshot"], "b07-test", world["root"] / "b07")


def test_successful_valuation_conforms_to_contract(package):
    result = inf.assess(FULL, comparables=COMPS, package=package, now=NOW)
    va = result["valuation_assessment"]
    assert va["assessment_status"] == "VALUATION_SUCCESS" and va["estimated_price_usd"] > 0
    interval = result["ml_prediction_interval"]
    assert interval["lower_bound_usd"] <= va["estimated_price_usd"] <= interval["upper_bound_usd"]
    assert interval["calibration_version"] == package.manifest["calibration_version"]
    assert result["feature_attributions"] and result["ontology"]["rules_version"]
    assert result["observed_market_statistics"]["comparables_count"] == 4
    assert inf.kind_for(result) == "property_valuation"
    errors = list(_validator("ValuationResponse").iter_errors(_full_response(result)))
    assert not errors, errors[:2]


def test_assess_is_deterministic(package):
    a = inf.assess(FULL, comparables=COMPS, package=package, now=NOW)
    b = inf.assess(FULL, comparables=COMPS, package=package, now=NOW)
    assert a == b


def test_asking_price_is_rejected_as_input(package):
    with pytest.raises(inf.InputValidationError):
        inf.assess({**FULL, "asking_price_usd_month": 600}, comparables=COMPS, package=package, now=NOW)


@pytest.mark.parametrize("patch", [{"latitude": 95}, {"area_sqm": 0}, {"rooms": 0}, {"renovation": "x"},
                                   {"floor": 12}, {"as_of": "2026-10-31"}, {"radius_m": 50}, {"rooms": 2.5}])
def test_invalid_input_is_rejected(package, patch):
    with pytest.raises(inf.InputValidationError):
        inf.assess({**FULL, **patch}, comparables=COMPS, package=package, now=NOW)


def test_outside_coverage_is_an_error_not_an_abstention(package):
    with pytest.raises(inf.OutsideCoverageError):
        inf.assess({**FULL, "latitude": 41.7}, comparables=COMPS, package=package, now=NOW)


def test_coordinate_only_returns_baseline_without_interval(package):
    result = inf.assess(BASE, comparables=COMPS, package=package, now=NOW)
    va = result["valuation_assessment"]
    assert va["assessment_status"] == "COORDINATE_BASELINE_ONLY" and va["deviation_from_baseline_pct"] == 0
    assert va["estimated_price_usd"] == result["observed_market_statistics"]["cluster_mean_price_usd"]
    assert result["ml_prediction_interval"]["lower_bound_usd"] is None and result["feature_attributions"] == []
    assert result["area_reference"]["reference_area_sqm"] > 0
    assert inf.kind_for(result) == "area_reference"
    assert not list(_validator("ValuationResponse").iter_errors(_full_response(result)))


@pytest.mark.parametrize("comps,as_of,reason", [(COMPS[:2], BASE["as_of"], "insufficient_observed_data"),
                                                (COMPS, "2026-07-01T00:00:00Z", "insufficient_observed_data"),
                                                (None, BASE["as_of"], "insufficient_observed_data")])
def test_sparse_or_stale_evidence_abstains_but_keeps_observed_statistics(package, comps, as_of, reason):
    result = inf.assess({**FULL, "as_of": as_of}, comparables=comps, package=package, now=NOW)
    assert result["valuation_assessment"]["assessment_status"] == "INSUFFICIENT_DATA_ABSTAIN"
    assert result["valuation_assessment"]["estimated_price_usd"] is None
    assert result["ml_prediction_interval"]["lower_bound_usd"] is None
    assert result["observed_market_statistics"]["insufficient_data"] is True
    assert result["provenance"]["abstention_reason"] == reason
    assert not list(_validator("ValuationResponse").iter_errors(_full_response(result)))


def test_serving_gate_withholds_extrapolated_estimates(package):
    result = inf.assess({**FULL, "area_sqm": 900}, comparables=COMPS, package=package, now=NOW)
    assert result["valuation_assessment"]["assessment_status"] == "INSUFFICIENT_DATA_ABSTAIN"
    assert "area_outside_training_range" in result["provenance"]["interval_withheld_reasons"]


def test_observed_statistics_follow_contract_semantics():
    obs = inf.observed_statistics([{"price_usd": p, "area_sqm": 50} for p in (500, 600, 700)],
                                  as_of=datetime(2026, 11, 2, tzinfo=timezone.utc), now=NOW)
    assert (obs["cluster_mean_price_usd"], obs["observed_price_std_dev_usd"]) == (600.0, 100.0)
    assert (obs["cluster_mean_price_per_sqm_usd"], obs["observed_price_std_dev_per_sqm_usd"]) == (12.0, 2.0)
    one = inf.observed_statistics([{"price_usd": 500, "area_sqm": None}], as_of=None, now=NOW)
    assert one["observed_price_std_dev_usd"] is None and one["area_comparables_count"] == 0
    assert one["cluster_mean_price_per_sqm_usd"] is None and one["insufficient_data"] and one["data_freshness_days"] is None
    assert not list(_validator("ObservedMarketStatistics").iter_errors(one))


def test_tampered_or_missing_package_is_detected(world, tmp_path):
    bad = tmp_path / "pkg"
    shutil.copytree(world["pkg"], bad)
    (bad / "interval_calibration.json").write_text("{}")
    with pytest.raises(inf.PackageError):
        inf.load_package(bad)
    with pytest.raises(inf.PackageError):
        inf.load_package(tmp_path / "does-not-exist")
    with pytest.raises(inf.PackageError):
        inf.load_package(None)


def test_unloadable_package_falls_back_to_abstention_not_a_crash(monkeypatch, tmp_path):
    monkeypatch.setenv(inf.PACKAGE_ENV_VAR, str(tmp_path / "missing"))
    result = inf.assess(FULL, comparables=COMPS, now=NOW)
    assert result["valuation_assessment"]["assessment_status"] == "INSUFFICIENT_DATA_ABSTAIN"
    assert result["versions"]["model_version"] == "unavailable" and result["provenance"]["fallback"]
    assert result["observed_market_statistics"]["comparables_count"] == 4
    assert not list(_validator("ValuationResponse").iter_errors(_full_response(result)))


def test_model_failure_at_runtime_becomes_abstention(package, monkeypatch):
    monkeypatch.setattr(inf.tc, "predict_usd", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    result = inf.assess(FULL, comparables=COMPS, package=package, now=NOW)
    assert result["provenance"]["fallback"] == "inference_error: RuntimeError"
    assert result["valuation_assessment"]["estimated_price_usd"] is None


def test_packaging_refuses_mismatched_artifacts(world, tmp_path):
    other = tmp_path / "b04"
    shutil.copytree(world["b04"], other)
    meta = json.loads((other / "metadata.json").read_text())
    meta["serving_decision"] = "baseline"
    (other / "metadata.json").write_text(json.dumps(meta, indent=2, sort_keys=True))
    sums = json.loads((other / "SHA256SUMS.json").read_text())
    sums["metadata.json"] = ci._sha256(other / "metadata.json")
    (other / "SHA256SUMS.json").write_text(json.dumps(sums))
    with pytest.raises(ci.ArtifactError, match="not 'ml'"):
        pk.build(other, world["b05"], world["snapshot"], "x", tmp_path / "o")


def test_python_310_syntax():
    import ast
    for name in ("inference.py", "package_inference.py", "attributions.py", "ontology_rules.py"):
        ast.parse((Path(__file__).resolve().parents[1] / name).read_text(encoding="utf-8"), feature_version=(3, 10))
