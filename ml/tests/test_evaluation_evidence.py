"""B08: the evidence command, its guards, and the claims it must not make."""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

pytest.importorskip("catboost")
pytest.importorskip("geoalchemy2")
pytest.importorskip("matplotlib")

from ml import calibrate_intervals as ci  # noqa: E402
from ml import evaluation_evidence as ev  # noqa: E402
from ml import package_inference as pk  # noqa: E402
from ml import train_compare as tc  # noqa: E402
from ml import validate_proximity as vp  # noqa: E402
from test_calibrate_intervals import _args, _snapshot  # noqa: E402


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = tmp_path_factory.mktemp("b08")
    snapshot = _snapshot(root)
    tc.run(tc.argparse.Namespace(synthetic=False, snapshot=str(snapshot), version="b04-b08-test",
                                 output_dir=str(root / "b04")))
    b04 = root / "b04" / "b04-b08-test"
    ci.run(_args({"b04": b04, "snapshot": snapshot, "root": root}, "b05-b08-test"))
    meta = json.loads((b04 / "metadata.json").read_text())
    meta["serving_decision"] = "ml"            # tiny synthetic market is solved by the baseline; tests exercise the evidence code
    (b04 / "metadata.json").write_text(json.dumps(meta, indent=2, sort_keys=True))
    sums = json.loads((b04 / "SHA256SUMS.json").read_text())
    sums["metadata.json"] = ci._sha256(b04 / "metadata.json")
    (b04 / "SHA256SUMS.json").write_text(json.dumps(sums, indent=2))
    b05 = root / "b05" / "b05-b08-test"
    package = pk.build(b04, b05, snapshot, "b08-test", root / "b07")
    out = root / "evidence"
    summary = ev.run(ev.argparse.Namespace(b04=b04, b05=b05, package=package, snapshot=snapshot, output=out))
    return {"root": root, "b04": b04, "b05": b05, "package": package, "snapshot": snapshot, "out": out,
            "summary": summary}


def test_all_evidence_files_are_written(world):
    out = world["out"]
    manifest = json.loads((out / "manifest.json").read_text())
    for name in manifest["files"] + ["manifest.json"]:
        assert (out / name).is_file() and (out / name).stat().st_size > 0, name
    assert {"price_model_comparison.png", "price_error_by_district.png", "interval_calibration.png",
            "predicted_vs_actual.png", "rule_validation.png", "price_anomaly_sensitivity.png"} <= set(manifest["files"])
    assert manifest["command"].startswith("python -m ml.evaluation_evidence")
    assert manifest["inputs"]["snapshot_sha256"] and manifest["inputs"]["files_sha256"]


def test_price_numbers_come_straight_from_the_reports(world):
    r4 = json.loads((world["b04"] / "report.json").read_text())
    card = (world["out"] / "model_card.md").read_text(encoding="utf-8")
    common = r4["test_common_rows"]
    assert f"{common['catboost']['mae']:,.2f}" in card and f"{common['baseline_b03_comparable_median']['mae']:,.2f}" in card
    summary = json.loads((world["out"] / "evaluation_summary.json").read_text())
    assert summary["price_error"]["test_common_rows"] == common


def test_card_separates_price_and_risk_and_makes_no_fraud_accuracy_claim(world):
    card = (world["out"] / "model_card.md").read_text(encoding="utf-8")
    assert "## 4. Price error" in card and "## 6. Risk rules (evaluated separately from price error)" in card
    assert "Fraud accuracy was not measured" in card and "unmeasured" in card
    lowered = card.lower()
    for banned in ("fraud detection accuracy", "fraud recall of", "precision of fraud"):
        assert banned not in lowered
    assert "NOT a fraud rate" in (world["out"] / "evaluation_summary.json").read_text() or "not a fraud rate" in lowered
    assert json.loads((world["out"] / "risk_rule_validation.json").read_text())["no_fraud_labels"] is True


def test_risk_validation_behaves_as_designed(world):
    risk = json.loads((world["out"] / "risk_rule_validation.json").read_text())
    inj = risk["injected_defects"]
    assert inj["consistent_synthetic_text_false_flags"]["false_flags_by_rule"] == {
        "DESC-AREA-MATCH": 0, "DESC-DISTRICT-MATCH": 0, "DESC-FLOOR-MATCH": 0, "DESC-ROOMS-MATCH": 0}
    assert inj["coordinates_removed"]["geo_flags"] == 0 and inj["coordinates_removed"]["facts_unknown"]["rate"] == 1.0
    assert inj["area_multiplied_by_10"]["rate"] > 0.9
    assert inj["area_multiplied_by_2"]["rate"] < 0.2              # moderate errors are not caught: stated, not hidden
    for name in ("text_rooms_differs", "text_area_differs_by_50pct", "text_floor_differs", "text_district_differs"):
        assert inj[name]["rate"] == 1.0 and inj[name]["n"] > 0
    points = {p["price_multiplier"]: p["rate"] for p in risk["price_anomaly_sensitivity"]["points"]}
    assert points[3.0] > points[1.5] > points[1.0]
    assert 0 < world["summary"]["price_anomaly"]["outside_rate"] < 0.2


def test_ontology_competency_questions_run(world):
    onto = json.loads((world["out"] / "ontology_evaluation.json").read_text())
    assert onto["available"] and onto["inferred_facts_disjoint_from_learned_effects"] is True
    assert set(onto["competency_questions"]) == {"CQ1", "CQ2", "CQ3", "CQ4"}
    assert len(onto["worked_examples"]) >= 3
    assert any(all(s == "unknown" for s in ex["facts"].values()) for ex in onto["worked_examples"])   # missing-data case


def test_evidence_is_deterministic(world, tmp_path):
    second = ev.run(ev.argparse.Namespace(b04=world["b04"], b05=world["b05"], package=world["package"],
                                          snapshot=world["snapshot"], output=tmp_path))
    for name in ("risk_rule_validation.json", "ontology_evaluation.json", "evaluation_summary.json"):
        assert (tmp_path / name).read_text() == (world["out"] / name).read_text().replace(str(world["out"]), str(tmp_path)), name
    assert second["risk_rules"] == world["summary"]["risk_rules"]


def test_refuses_artifacts_that_do_not_belong_together(world, tmp_path):
    other = tmp_path / "b05"
    shutil.copytree(world["b05"], other)
    report = json.loads((other / "b05_report.json").read_text())
    report["metadata"]["snapshot_sha256"] = "0" * 64
    (other / "b05_report.json").write_text(json.dumps(report))
    sums = json.loads((other / "SHA256SUMS.json").read_text())
    sums["b05_report.json"] = ci._sha256(other / "b05_report.json")
    (other / "SHA256SUMS.json").write_text(json.dumps(sums))
    assert ev.main(["--b04", str(world["b04"]), "--b05", str(other), "--package", str(world["package"]),
                    "--snapshot", str(world["snapshot"]), "--output", str(tmp_path / "o")]) == 2


def test_wilson_interval():
    low, high = ev.wilson(50, 100)
    assert 0.40 < low < 0.5 < high < 0.60 and ev.wilson(0, 0) == (None, None)
    assert ev.wilson(100, 100)[1] == 1.0


def test_proximity_effect_reports_confounding(world):
    import pandas as pd
    test = pd.read_csv(Path(world["snapshot"]) / "test.csv")
    res = vp.metro_proximity_effect(test)
    assert res["available"] and res["interpretation"].startswith("Ratio of median price per m2")
    assert set(res["buckets"]) == {"near", "between", "far"}


def test_withheld_predictions_are_excluded_from_every_served_row_rate(world):
    import numpy as np
    inputs = ev.load_inputs(world["b04"], world["b05"], world["package"], world["snapshot"])
    pred = ev.predictions(inputs)
    package = inputs["package"]
    assert ev.interval_for_row(float("nan"), float("nan"), package) is None      # NaN is "no interval", like None
    assert ev.interval_for_row(None, 5.0, package) is None
    pred.loc[:49, ["lower_usd", "upper_usd"]] = np.nan                            # withhold 50 more rows
    pred.loc[:49, "price_status"] = "insufficient_data"
    risk = ev.risk_validation(inputs, pred)
    served = int((pred["price_status"] != "insufficient_data").sum())
    assert served <= len(pred) - 50
    assert all(p["n"] == served for p in risk["price_anomaly_sensitivity"]["points"])
    assert risk["flag_rates_on_unmodified_rows"]["PRICE-OUTSIDE-INTERVAL"]["unknown"] >= 50


def test_sensitivity_at_multiplier_one_equals_the_price_anomaly_rate(world):
    summary = world["summary"]
    at_one = next(p for p in summary["risk_rules"]["price_anomaly_sensitivity"]["points"] if p["price_multiplier"] == 1.0)
    served = summary["price_anomaly"]["served_rows"]
    assert at_one["n"] == served
    assert round(at_one["detected"] / served, 4) == summary["price_anomaly"]["outside_rate"]


def test_refuses_a_b05_calibration_that_differs_from_the_packaged_one(world, tmp_path):
    ci.run(_args({"b04": world["b04"], "snapshot": world["snapshot"], "root": world["root"]},
                 "b05-b08-absolute", method="absolute"))
    absolute = world["root"] / "b05" / "b05-b08-absolute"
    assert (absolute / "interval_calibration.json").read_bytes() != (world["b05"] / "interval_calibration.json").read_bytes()
    with pytest.raises(ci.ArtifactError, match="calibration"):
        ev.load_inputs(world["b04"], absolute, world["package"], world["snapshot"])
    assert ev.main(["--b04", str(world["b04"]), "--b05", str(absolute), "--package", str(world["package"]),
                    "--snapshot", str(world["snapshot"]), "--output", str(tmp_path / "o")]) == 2
    ev.load_inputs(world["b04"], world["b05"], world["package"], world["snapshot"])   # the matching one still loads
