"""Tests for [B04] train_compare: leakage guards, training-only fitting, decision plumbing."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("catboost")

from ml import train_compare as tc


@pytest.fixture(scope="module")
def splits():
  return tc.synthetic_snapshot(n_groups=300)


def test_synthetic_split_is_group_isolated_and_chronological(splits):
  report = tc.leakage_checks(splits, ["latitude", "area_sqm"])
  assert report["passed"], report
  assert all(v == 0 for v in report["group_overlap_between_splits"].values())


def test_leakage_check_flags_group_overlap_and_target_columns(splits):
  leaky = {k: v.copy() for k, v in splits.items()}
  leaky["test"] = pd.concat([leaky["test"], leaky["train"].head(3)], ignore_index=True)
  report = tc.leakage_checks(leaky, ["latitude", "price_usd"])
  assert not report["passed"]
  assert report["group_overlap_between_splits"]["train&test"] > 0
  assert report["target_derived_columns_in_features"] == ["price_usd"]


def test_preprocessor_fitted_on_train_only(splits):
  train = splits["train"]
  pre = tc.Preprocessor().fit(train)
  poisoned = splits["test"].copy()
  poisoned["area_sqm"] = 10_000.0
  # Fitted statistics must not move when other splits change.
  assert tc.Preprocessor().fit(train).to_json() == pre.to_json()
  x = pre.transform(splits["test"].assign(area_sqm=np.nan))
  expected = splits["test"]["district"].map(pre.district_area).fillna(pre.global_area)
  assert np.allclose(x["area_sqm"], expected)
  assert not x[pre.feature_names].isna().any().any()
  assert "price_usd" not in pre.feature_names


def test_metrics_known_values():
  m = tc.metrics(np.array([100.0, 200.0, 300.0]), np.array([110.0, 190.0, 330.0]))
  assert m["mae"] == pytest.approx(16.67, abs=0.01)
  assert m["median_ae"] == 10.0


def test_near_duplicate_with_different_group_id_fails_validation(splits):
  leaky = {k: v.copy() for k, v in splits.items()}
  dup = leaky["train"].iloc[[0]].copy()
  dup["dedup_group_id"] = "different-group-id"
  leaky["test"] = pd.concat([leaky["test"], dup], ignore_index=True)
  report = tc.leakage_checks(leaky, ["latitude"])
  assert report["near_duplicate_rows_between_splits(coords+area+price)"]["train&test"] >= 1
  assert not report["passed"]


def test_validate_splits_raises_before_training(splits):
  leaky = {k: v.copy() for k, v in splits.items()}
  leaky["test"] = pd.concat([leaky["test"], leaky["train"].head(2)], ignore_index=True)
  with pytest.raises(tc.SplitValidationError):
    tc.validate_splits(leaky, ["latitude"])


def test_run_aborts_without_artifacts_when_splits_leak(tmp_path, monkeypatch):
  clean = tc.synthetic_snapshot(n_groups=200)
  clean["test"] = pd.concat([clean["test"], clean["train"].head(2)], ignore_index=True)
  monkeypatch.setattr(tc, "synthetic_snapshot", lambda: clean)
  args = tc.argparse.Namespace(synthetic=True, snapshot=None, version="leaky",
                               output_dir=str(tmp_path))
  with pytest.raises(tc.SplitValidationError):
    tc.run(args)
  assert not (tmp_path / "leaky").exists()


def test_per_district_uses_common_rows_for_both_models():
  test = pd.DataFrame({"district": ["A"] * 4, "price_usd": [100.0, 200.0, 300.0, 400.0]})
  base = np.array([110.0, np.nan, 290.0, np.nan])
  ml = np.array([100.0, 250.0, 300.0, 500.0])
  row = tc.per_district(test, base, ml, ~np.isnan(base))[0]
  assert row["common_rows"]["n"] == 2
  assert row["common_rows"]["catboost"]["n"] == row["common_rows"]["baseline"]["n"] == 2
  assert row["common_rows"]["catboost"]["mae"] == 0.0
  assert row["catboost_full_cohort"]["n"] == 4
  assert row["baseline_coverage"] == {"answered": 2, "abstained": 2}


# ---- non-temporal (grouped-random) snapshots from a one-observation-date scrape ----

def test_leakage_check_marks_chronology_not_applicable_for_non_temporal_splits(splits):
  report = tc.leakage_checks(splits, ["latitude", "area_sqm"], temporal=False)
  assert report["temporal_split"] is False
  assert report["chronological_order_ok"] == "not_applicable"
  assert report["passed"], report


def test_non_temporal_flag_does_not_relax_group_overlap_or_target_checks(splits):
  leaky = {k: v.copy() for k, v in splits.items()}
  leaky["test"] = pd.concat([leaky["test"], leaky["train"].head(3)], ignore_index=True)
  report = tc.leakage_checks(leaky, ["latitude", "price_usd"], temporal=False)
  assert not report["passed"]
  assert report["group_overlap_between_splits"]["train&test"] > 0
  assert report["target_derived_columns_in_features"] == ["price_usd"]


def test_temporal_check_still_fails_when_dates_are_out_of_order(splits):
  shuffled = {k: v.copy() for k, v in splits.items()}
  shuffled["train"], shuffled["test"] = shuffled["test"], shuffled["train"]
  assert not tc.leakage_checks(shuffled, ["latitude"])["passed"]
  assert tc.leakage_checks(shuffled, ["latitude"], temporal=False)["chronological_order_ok"] == "not_applicable"


def _one_day_snapshot(tmp_path, groups=240, seed=7, twin_every=0, merge=False):
  """A06 export (grouped-random) of a synthetic single-date scrape, written like the real CLI."""
  pytest.importorskip("geoalchemy2")
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
    price = round(base[d] * area * float(rng.normal(1.0, 0.08)), 2)
    rows.append({
        "source": "list.am", "_property_id": i, "price_usd": price, "original_price": price,
        "original_currency": "USD", "original_period": "month", "exchange_rate": 1.0,
        "rate_source": "identity", "rate_date": date(2026, 1, 1), "utilities_included": None,
        "area_sqm": area, "rooms": int(max(1, area // 30)), "floor": int(rng.integers(1, 9)),
        "total_floors": 9, "building_type": "stone", "first_seen_at": observed,
        "observation_at": observed, "ingestion_run_id": 1,
        "raw_data": {"rejected_fields": {}},
        "latitude": 40.17 + (i % 4) * 0.01 + float(rng.normal(0, 0.002)),
        "longitude": 44.50 + (i % 4) * 0.01 + float(rng.normal(0, 0.002)),
        "district_id": d, "distance_metro_m": 700.0, "distance_center_m": 1500.0 + 100 * (i % 4),
        "distance_university_m": 1200.0, "coordinate_source": "test",
        "coordinate_confidence": "approximate", "geography_version": "test-geo",
    })
  if twin_every:
    # Reposts: same coordinates, area and price, but a different property (so its own group).
    for original in [r for r in rows if r["_property_id"] % twin_every == 0]:
      rows.append({**original, "_property_id": original["_property_id"] + 10_000})
  as_of = date(2026, 10, 31)
  split_rows, quality = ex.prepare_snapshot(rows, as_of, split_mode="grouped-random",
                                            merge_near_duplicates=merge)
  version = f"v-test-grouped-{'merged' if merge else 'plain'}"
  artifacts = ex.create_artifacts(split_rows, quality, version, as_of)
  return ex.write_versioned_snapshot(tmp_path / "processed", version, artifacts)


def test_end_to_end_one_date_snapshot_runs_b04_and_labels_results_non_temporal(tmp_path):
  snapshot = _one_day_snapshot(tmp_path)
  args = tc.argparse.Namespace(synthetic=False, snapshot=str(snapshot), version="b04-grouped-test",
                               output_dir=str(tmp_path / "artifacts"))
  report = tc.run(args)

  meta = report["metadata"]
  assert meta["dataset"]["temporal_split"] is False
  assert "grouped-random" in meta["dataset"]["split_method"]
  assert "non-temporal" in meta["evidence_level"]
  assert report["leakage"]["chronological_order_ok"] == "not_applicable"
  assert report["leakage"]["passed"]
  assert len(report["limitations"]) == 3
  assert meta["serving_decision"] in {"ml", "baseline"}
  assert report["test_common_rows"]["n"] > 0
  for name in ("model.cbm", "preprocessing.json", "feature_schema.json", "metadata.json",
               "report.json", "SHA256SUMS.json"):
    assert (tmp_path / "artifacts" / "b04-grouped-test" / name).is_file()


def test_empty_validation_error_points_to_the_grouped_random_fallback(tmp_path):
  snapshot = _one_day_snapshot(tmp_path)
  for name in ("validation", "test"):
    path = snapshot / f"{name}.csv"
    path.write_text(path.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
  args = tc.argparse.Namespace(synthetic=False, snapshot=str(snapshot), version="x",
                               output_dir=str(tmp_path / "artifacts"))
  with pytest.raises(SystemExit) as error:
    tc.run(args)
  assert "grouped-random" in str(error.value)


def test_reposted_listings_are_refused_without_merge_and_accepted_with_it(tmp_path):
  args = lambda snap, name: tc.argparse.Namespace(
      synthetic=False, snapshot=str(snap), version=name, output_dir=str(tmp_path / "artifacts"))

  plain = _one_day_snapshot(tmp_path, twin_every=4, merge=False)
  with pytest.raises(tc.SplitValidationError) as error:
    tc.run(args(plain, "b04-plain"))
  assert "near_duplicate_rows_between_splits" in str(error.value)
  assert not (tmp_path / "artifacts" / "b04-plain").exists()  # nothing written on a leaky split

  merged = _one_day_snapshot(tmp_path, twin_every=4, merge=True)
  report = tc.run(args(merged, "b04-merged"))
  assert report["leakage"]["passed"]
  assert all(v == 0 for v in report["leakage"]["near_duplicate_rows_between_splits(coords+area+price)"].values())
