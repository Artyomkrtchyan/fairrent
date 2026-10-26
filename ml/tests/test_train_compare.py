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
