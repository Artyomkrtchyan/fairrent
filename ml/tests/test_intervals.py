"""Tests for [B05] ml/intervals.py: conformal calibration, contract blocks, price_status, serving gate."""

from pathlib import Path
import json
import math
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np
import pandas as pd
import pytest

from ml import intervals as iv


@pytest.fixture(scope="module")
def hetero():
  rng = np.random.default_rng(0)
  n = 30000
  pred = rng.lognormal(6.2, 0.5, n)
  y = pred * np.exp(rng.normal(0, 0.18, n))   # error grows with price
  return pred, y


# --------------------------------------------------------------- conformal quantile

def test_conformal_quantile_uses_ceil_n_plus_1_rank_and_needs_enough_scores():
  scores = np.arange(1, 20, dtype=float)          # n = 19
  assert iv.conformal_quantile(scores, 0.95) == 19.0   # ceil(20 * 0.95) = 19 -> largest
  assert iv.conformal_quantile(np.arange(1, 101, dtype=float), 0.90) == 91.0   # ceil(101*0.9) = 91
  with pytest.raises(iv.CalibrationError, match="at least 19"):
    iv.conformal_quantile(np.arange(1, 19, dtype=float), 0.95)                 # n = 18
  assert iv.min_calibration_size(0.80) == 4 and iv.min_calibration_size(0.95) == 19


def test_nonconformity_absolute_vs_relative_and_prediction_floor():
  y, p = [110.0, 90.0], [100.0, 100.0]
  assert list(iv.nonconformity(y, p, "absolute")) == [10.0, 10.0]
  assert list(iv.nonconformity(y, p, "relative")) == pytest.approx([0.1, 0.1])
  assert np.isfinite(iv.nonconformity([5.0], [0.0], "relative")).all()   # prediction floored at $1
  with pytest.raises(ValueError):
    iv.nonconformity(y, p, "bogus")


def test_split_conformal_hits_nominal_coverage_on_heldout_rows(hetero):
  pred, y = hetero
  cal_mask = np.arange(len(y)) < 10000
  for method in ("absolute", "relative"):
    cal = iv.fit_calibration(y[cal_mask], pred[cal_mask], method=method)
    for level in (0.80, 0.90, 0.95):
      lo, hi = cal.bounds(pred[~cal_mask], level)
      coverage = iv.interval_metrics(y[~cal_mask], pred[~cal_mask], lo, hi)["coverage"]
      assert abs(coverage - level) < 0.012, (method, level, coverage)


def test_relative_intervals_are_narrower_than_absolute_when_error_scales_with_price(hetero):
  pred, y = hetero
  cal_mask = np.arange(len(y)) < 10000
  ratios = {}
  for method in ("absolute", "relative"):
    cal = iv.fit_calibration(y[cal_mask], pred[cal_mask], method=method)
    lo, hi = cal.bounds(pred[~cal_mask], 0.95)
    ratios[method] = iv.interval_metrics(y[~cal_mask], pred[~cal_mask], lo, hi)["median_width_ratio"]
  assert ratios["relative"] < ratios["absolute"]


def test_calibration_uses_only_the_labels_it_is_given():
  rng = np.random.default_rng(1)
  pred = rng.uniform(300, 900, 400)
  y = pred * rng.normal(1, 0.1, 400)
  a = iv.fit_calibration(y, pred)
  b = iv.fit_calibration(y.copy(), pred.copy())
  assert a.to_json() == b.to_json()
  assert iv.fit_calibration(y * 2, pred).levels != a.levels


def test_mondrian_uses_group_quantile_only_for_large_enough_groups_and_needs_groups():
  rng = np.random.default_rng(2)
  n = 600
  groups = np.array(["big"] * 400 + ["tiny"] * 20 + ["mid"] * 180)
  pred = np.full(n, 500.0)
  noise = np.where(groups == "big", 0.05, 0.3)
  y = pred * (1 + rng.normal(0, 1, n) * noise)
  cal = iv.fit_calibration(y, pred, method="relative_by_district", groups=groups, min_group_size=100)
  assert set(cal.group_levels) == {"big", "mid"}              # "tiny" (20 rows) falls back
  assert cal.quantile(0.95, "big") < cal.quantile(0.95, "mid")
  assert cal.quantile(0.95, "tiny") == cal.levels["0.95"] == cal.quantile(0.95)
  with pytest.raises(ValueError):
    iv.fit_calibration(y, pred, method="relative_by_district")


def test_calibration_json_round_trip_and_schema_guard():
  rng = np.random.default_rng(3)
  pred = rng.uniform(300, 900, 300)
  cal = iv.fit_calibration(pred * rng.normal(1, 0.1, 300), pred, calibration_version="v",
                           meta={"b04_model_sha256": "abc"})
  payload = json.loads(iv.dumps(cal.to_json()))
  assert iv.IntervalCalibration.from_json(payload) == cal
  payload["calibration_schema_version"] = "other"
  with pytest.raises(iv.CalibrationError):
    iv.IntervalCalibration.from_json(payload)
  with pytest.raises(ValueError):
    iv.fit_calibration([1.0] * 50, [1.0] * 50, primary_level=0.5)


# ---------------------------------------------------------- contract interval blocks

@pytest.fixture(scope="module")
def cal():
  rng = np.random.default_rng(4)
  pred = rng.uniform(300, 900, 2000)
  return iv.fit_calibration(pred * rng.normal(1, 0.15, 2000), pred, calibration_version="b05-test")


def test_interval_block_matches_contract_encloses_prediction_and_rounds_outward(cal):
  block = iv.prediction_interval(1234.5678, cal)
  assert set(block) == {"lower_bound_usd", "upper_bound_usd", "confidence_level", "interval_width_usd",
                        "calibration_version"}
  assert block["lower_bound_usd"] <= 1234.5678 <= block["upper_bound_usd"]
  assert block["interval_width_usd"] == round(block["upper_bound_usd"] - block["lower_bound_usd"], 2)
  assert block["confidence_level"] == 0.95 and block["calibration_version"] == "b05-test"
  raw_lo, raw_hi = cal.bounds(1234.5678)
  assert block["lower_bound_usd"] <= raw_lo[0] and block["upper_bound_usd"] >= raw_hi[0]  # outward only
  assert all(round(v * 100, 6) == round(v * 100) for v in (block["lower_bound_usd"], block["upper_bound_usd"]))


def test_interval_block_is_all_null_without_calibration_prediction_or_when_gate_withholds(cal):
  null = {"lower_bound_usd": None, "upper_bound_usd": None, "confidence_level": None, "interval_width_usd": None}
  assert iv.prediction_interval(700.0, None) == null
  assert iv.prediction_interval(None, cal) == null
  assert iv.prediction_interval(float("nan"), cal) == null
  assert iv.prediction_interval(700.0, cal, reasons=[iv.REASON_NO_AREA]) == null
  assert "calibration_version" not in iv.null_interval()


def test_interval_lower_bound_is_never_negative():
  wide = iv.IntervalCalibration(method="relative", levels={"0.95": 1.8}, n_calibration=100,
                                calibration_version="w")
  block = iv.prediction_interval(100.0, wide)
  assert block["lower_bound_usd"] == 0.0 and block["upper_bound_usd"] == 280.0


# ------------------------------------------------------------------- price_status

def test_price_status_edges_are_inclusive_and_outside_values_are_flagged():
  kw = {"lower": 670.0, "upper": 830.0}
  assert iv.price_status(669.99, **kw) == "below_range"
  assert iv.price_status(670.0, **kw) == "within_range"
  assert iv.price_status(750.0, **kw) == "within_range"
  assert iv.price_status(830.0, **kw) == "within_range"
  assert iv.price_status(830.01, **kw) == "above_range"


@pytest.mark.parametrize("asking", [None, float("nan"), float("inf"), 0, -5, True, "700"])
def test_price_status_is_insufficient_for_unusable_asking_prices(asking):
  assert iv.price_status(asking, lower=670.0, upper=830.0) == "insufficient_data"


def test_price_status_is_insufficient_without_an_interval_and_validates_bounds(cal):
  assert iv.price_status(700.0, iv.null_interval()) == "insufficient_data"
  assert iv.price_status(700.0, None) == "insufficient_data"
  assert iv.price_status(700.0, lower=None, upper=800.0) == "insufficient_data"
  with pytest.raises(ValueError):
    iv.price_status(700.0, lower=800.0, upper=670.0)
  block = iv.prediction_interval(700.0, cal)
  assert iv.price_status(700.0, block) == "within_range"
  assert iv.price_status(block["upper_bound_usd"] + 0.01, block) == "above_range"
  assert set(iv.PRICE_STATUSES) == {"within_range", "above_range", "below_range", "insufficient_data"}


# ------------------------------------------------------------------ serving gate

def _train_frame(n=300, seed=5):
  rng = np.random.default_rng(seed)
  return pd.DataFrame({"latitude": 40.18 + rng.normal(0, 0.01, n), "longitude": 44.51 + rng.normal(0, 0.01, n),
                       "area_sqm": rng.uniform(30, 110, n)})


def test_gate_allows_supported_requests_and_explains_every_withheld_one():
  gate = iv.ServingGate.fit(_train_frame())
  rows = pd.DataFrame([
      {"latitude": 40.18, "longitude": 44.51, "area_sqm": 60.0},     # fine
      {"latitude": 40.18, "longitude": 44.51, "area_sqm": None},     # coordinate-only
      {"latitude": 40.18, "longitude": 44.51, "area_sqm": 5000.0},   # extrapolation
      {"latitude": 41.50, "longitude": 44.51, "area_sqm": 60.0},     # nothing nearby
      {"latitude": None, "longitude": 44.51, "area_sqm": 60.0},      # invalid coordinates
      {"latitude": 95.0, "longitude": 44.51, "area_sqm": 60.0},      # impossible latitude
  ])
  got = gate.reasons(rows)
  assert got[0] == []
  assert got[1] == [iv.REASON_NO_AREA]
  assert got[2] == [iv.REASON_AREA_RANGE]
  assert got[3] == [iv.REASON_SPARSE]
  assert got[4] == [iv.REASON_MISSING_COORDINATES]   # no support lookup without a usable point
  assert got[5] == [iv.REASON_MISSING_COORDINATES]


def test_gate_is_fitted_on_train_only_and_serialises_counts_not_raw_points():
  train = _train_frame()
  gate = iv.ServingGate.fit(train)
  payload = json.loads(json.dumps(gate.to_json()))
  assert payload["fitted_on"] == "train split only"
  assert sum(payload["cell_counts"].values()) == len(train)
  assert all(len(key.split(",")) == 2 for key in payload["cell_counts"])       # grid cells only
  text = json.dumps(payload)
  assert all(f"{value:.5f}" not in text for value in train.latitude.head(20))   # no raw coordinates stored
  restored = iv.ServingGate.from_json(payload)
  probe = _train_frame(50, seed=9)
  assert restored.reasons(probe) == gate.reasons(probe)


def test_gate_needs_some_usable_area_in_training():
  with pytest.raises(iv.CalibrationError):
    iv.ServingGate.fit(pd.DataFrame({"latitude": [40.1], "longitude": [44.5], "area_sqm": [None]}))


# ---- regression: an interval must never exclude its own prediction (PR #85 review) ----

@pytest.mark.parametrize("pred", [0.0, 0.5, 0.999, -5.0, float("nan")])
def test_predictions_below_the_minimum_get_no_interval_instead_of_one_that_excludes_them(pred):
  wide = iv.IntervalCalibration(method="relative", levels={"0.95": 0.5}, n_calibration=100,
                                calibration_version="w")
  assert iv.prediction_interval(pred, wide) == iv.null_interval()


def test_every_returned_interval_encloses_its_prediction_including_near_the_minimum():
  wide = iv.IntervalCalibration(method="relative", levels={"0.95": 0.5}, n_calibration=100,
                                calibration_version="w")
  for pred in (1.0, 1.0001, 1.5, 7.77, 100.0, 1e6):
    block = iv.prediction_interval(pred, wide)
    assert block["lower_bound_usd"] <= pred <= block["upper_bound_usd"], pred
    assert block["interval_width_usd"] == round(block["upper_bound_usd"] - block["lower_bound_usd"], 2)
  absolute = iv.IntervalCalibration(method="absolute", levels={"0.95": 300.0}, n_calibration=100,
                                    calibration_version="a")
  for pred in (1.0, 50.0, 12345.678):
    block = iv.prediction_interval(pred, absolute)
    assert block["lower_bound_usd"] <= pred <= block["upper_bound_usd"], pred
