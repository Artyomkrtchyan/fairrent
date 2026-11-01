"""End-to-end tests for [B05] ml/calibrate_intervals.py on a small exporter-built snapshot."""

from pathlib import Path
import json
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("catboost")
pytest.importorskip("geoalchemy2")

from ml import calibrate_intervals as ci
from ml import intervals as iv
from ml import train_compare as tc


def _snapshot(root: Path, groups: int = 420, seed: int = 11) -> Path:
  """A06 export (grouped-random) of a synthetic single-date scrape, written like the real CLI."""
  from datetime import date, datetime, timezone
  from data_pipeline import export_dataset as ex

  rng = np.random.default_rng(seed)
  districts = ["kentron", "arabkir", "ajapnyak", "avan"]
  base = {"kentron": 14.0, "arabkir": 11.0, "ajapnyak": 8.0, "avan": 7.0}
  observed = datetime(2026, 10, 31, 9, 47, tzinfo=timezone.utc)
  rows = []
  for i in range(1, groups + 1):
    d = districts[i % 4]
    area = float(rng.integers(30, 120))
    price = round(base[d] * area * float(rng.normal(1.0, 0.12)), 2)
    rows.append({
        "source": "list.am", "_property_id": i, "price_usd": price, "original_price": price,
        "original_currency": "USD", "original_period": "month", "exchange_rate": 1.0,
        "rate_source": "identity", "rate_date": date(2026, 1, 1), "utilities_included": None,
        "area_sqm": area, "rooms": int(max(1, area // 30)), "floor": int(rng.integers(1, 9)),
        "total_floors": 9, "building_type": "stone", "first_seen_at": observed,
        "observation_at": observed, "ingestion_run_id": 1, "raw_data": {"rejected_fields": {}},
        "latitude": 40.17 + (i % 4) * 0.01 + float(rng.normal(0, 0.002)),
        "longitude": 44.50 + (i % 4) * 0.01 + float(rng.normal(0, 0.002)),
        "district_id": d, "distance_metro_m": 700.0, "distance_center_m": 1500.0 + 100 * (i % 4),
        "distance_university_m": 1200.0, "coordinate_source": "test",
        "coordinate_confidence": "approximate", "geography_version": "test-geo",
    })
  as_of = date(2026, 10, 31)
  split_rows, quality = ex.prepare_snapshot(rows, as_of, split_mode="grouped-random", merge_near_duplicates=True)
  artifacts = ex.create_artifacts(split_rows, quality, "v-b05-test", as_of)
  return ex.write_versioned_snapshot(root / "processed", "v-b05-test", artifacts)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
  root = tmp_path_factory.mktemp("b05")
  snapshot = _snapshot(root)
  tc.run(tc.argparse.Namespace(synthetic=False, snapshot=str(snapshot), version="b04-b05-test",
                               output_dir=str(root / "b04")))
  return {"root": root, "snapshot": snapshot, "b04": root / "b04" / "b04-b05-test"}


def _args(world, version, **overrides):
  base = dict(b04=str(world["b04"]), snapshot=str(world["snapshot"]), version=version, method="relative",
              level=0.95, output_dir=str(world["root"] / "b05"))
  base.update(overrides)
  return ci.argparse.Namespace(**base)


def test_end_to_end_writes_bound_artifacts_and_reports_heldout_coverage(world):
  report = ci.run(_args(world, "e2e"))
  out = world["root"] / "b05" / "e2e"
  for name in ("interval_calibration.json", "b05_report.json", "SHA256SUMS.json"):
    assert (out / name).is_file()
  payload = json.loads((out / "interval_calibration.json").read_text(encoding="utf-8"))
  assert payload["meta"]["b04_model_sha256"] == report["metadata"]["b04_model_sha256"]
  assert payload["meta"]["snapshot_sha256"] == report["metadata"]["snapshot_sha256"]
  assert payload["meta"]["calibration_split"].startswith("validation")
  assert payload["serving_gate"]["fitted_on"] == "train split only"
  assert report["metadata"]["temporal_split"] is False
  assert any("NOT chronological" in note for note in report["limitations"])
  served = report["held_out_test"]["0.95"]["served_rows"]
  assert served["n"] > 40 and served["coverage"] >= 0.85          # small test split: loose bound
  checks = report["price_status_checks"]
  assert checks["bounds_enclose_prediction"] and checks["width_equals_upper_minus_lower"]
  assert checks["withheld_blocks_are_all_null"]
  assert checks["asking_price_x2_of_prediction"]["above_range"] == served["n"]
  assert checks["asking_price_x0.25_of_prediction"]["below_range"] == served["n"]
  assert checks["missing_asking_price"]["insufficient_data"] == report["metadata"]["split_rows"]["test"]
  assert {"sparse_local_data", "missing_features", "out_of_distribution"} <= set(report["scenarios"])
  assert report["scenarios"]["out_of_distribution"]["synthetic_location_shifted_0.3deg_north"]["share_withheld"] == 1.0
  assert report["scenarios"]["out_of_distribution"]["synthetic_area_twice_training_maximum"]["share_withheld"] == 1.0
  assert report["scenarios"]["missing_features"]["area_missing"]["interval_still_returned_share"] == 0.0
  assert set(report["variants_compared_on_test"]) >= {"absolute", "relative", "relative_by_district"}


def test_calibration_does_not_depend_on_test_labels(world):
  ci.run(_args(world, "labels-a"))
  tampered = world["root"] / "snapshot-tampered"
  shutil.copytree(world["snapshot"], tampered)
  test = pd.read_csv(tampered / "test.csv")
  test["price_usd"] = test["price_usd"] * 10 + 5000          # wildly different test labels
  test.to_csv(tampered / "test.csv", index=False)
  report_b = ci.run(_args(world, "labels-b", snapshot=str(tampered)))
  a = (world["root"] / "b05" / "labels-a" / "interval_calibration.json").read_bytes()
  b = (world["root"] / "b05" / "labels-b" / "interval_calibration.json").read_bytes()
  assert a.replace(b"labels-a", b"labels-b") == b              # only the version label differs
  assert report_b["held_out_test"]["0.95"]["served_rows"]["coverage"] < 0.5   # ...but the score reacts


def test_calibration_is_deterministic(world):
  ci.run(_args(world, "det-1"))
  ci.run(_args(world, "det-2"))
  a = (world["root"] / "b05" / "det-1" / "interval_calibration.json").read_text(encoding="utf-8")
  b = (world["root"] / "b05" / "det-2" / "interval_calibration.json").read_text(encoding="utf-8")
  assert a.replace("det-1", "det-2") == b


def test_refuses_altered_b04_artifacts_and_mismatched_snapshots(world):
  broken = world["root"] / "b04-broken"
  shutil.copytree(world["b04"], broken)
  with (broken / "model.cbm").open("ab") as handle:
    handle.write(b"x")
  with pytest.raises(ci.ArtifactError, match="model.cbm"):
    ci.run(_args(world, "bad-model", b04=str(broken)))

  other = _snapshot(world["root"] / "other", seed=99)
  with pytest.raises(ci.ArtifactError, match="snapshot SHA-256"):
    ci.run(_args(world, "bad-snapshot", snapshot=str(other)))
  with pytest.raises(ci.ArtifactError, match="SHA256SUMS"):
    ci.run(_args(world, "no-b04", b04=str(world["root"])))


def test_level_option_is_validated_and_other_levels_are_reported(world):
  with pytest.raises(SystemExit):
    ci.run(_args(world, "bad-level", level=0.99))
  report = ci.run(_args(world, "level-90", level=0.90))
  assert report["metadata"]["primary_level"] == 0.90
  assert set(report["held_out_test"]) == {"0.80", "0.90", "0.95"}


def test_relative_by_district_method_runs(world):
  report = ci.run(_args(world, "mondrian", method="relative_by_district"))
  assert report["metadata"]["method"] == "relative_by_district"
  assert report["held_out_test"]["0.95"]["served_rows"]["coverage"] >= 0.8
