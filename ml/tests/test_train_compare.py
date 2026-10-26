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
