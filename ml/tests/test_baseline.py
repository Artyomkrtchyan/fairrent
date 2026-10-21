"""Deterministic unit tests for [B03] Comparable Property Median Baseline."""

from pathlib import Path
import sys

# Ensure root directory is on Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np
import pandas as pd
import pytest
from ml.baseline import ComparableMedianBaseline


@pytest.fixture
def sample_dataset():
  """Provides controlled synthetic rental dataset for Yerevan districts."""
  data = {
      "listing_id": [101, 102, 103, 104, 105, 106],
      "district": [
          "Kentron",
          "Kentron",
          "Kentron",
          "Arabkir",
          "Arabkir",
          "Shengavit",
      ],
      "latitude": [40.1811, 40.1820, 40.1805, 40.2010, 40.2025, 40.1450],
      "longitude": [44.5136, 44.5140, 44.5120, 44.5080, 44.5095, 44.4850],
      "area_sqm": [50.0, 60.0, 100.0, 70.0, 80.0, 40.0],
      "price_usd": [500.0, 600.0, 1000.0, 560.0, 640.0, 240.0],
      "rooms": [2, 2, 3, 2, 3, 1],
  }
  df = pd.DataFrame(data)
  df["price_per_sqm"] = df["price_usd"] / df["area_sqm"]
  return df


def test_standard_valuation_success(sample_dataset):
  """Test standard request with area_sqm returning exact median valuation."""
  model = ComparableMedianBaseline(sample_dataset, min_comparables=3)
  query = {
      "latitude": 40.1811,
      "longitude": 44.5136,
      "district": "Kentron",
      "area_sqm": 70.0,
  }

  res = model.predict(query)

  assert (
      res["valuation_assessment"]["assessment_status"] == "VALUATION_SUCCESS"
  )
  assert res["valuation_assessment"]["price_per_sqm_usd"] == 10.0
  assert res["valuation_assessment"]["estimated_price_usd"] == 700.0
  assert res["observed_market_statistics"]["comparables_count"] == 3
  assert res["observed_market_statistics"]["insufficient_data"] is False


def test_coordinate_only_request(sample_dataset):
  """Test coordinate-only payload returning reference area baseline."""
  model = ComparableMedianBaseline(
      sample_dataset, min_comparables=3, default_reference_area_sqm=60.0
  )
  query = {
      "latitude": 40.1811,
      "longitude": 44.5136,
      "district": "Kentron",
      "area_sqm": None,
  }

  res = model.predict(query)

  assert (
      res["valuation_assessment"]["assessment_status"]
      == "COORDINATE_BASELINE_ONLY"
  )
  assert res["valuation_assessment"]["estimated_price_usd"] == 600.0
  assert res["observed_market_statistics"]["insufficient_data"] is False


def test_sparse_comparables_abstention(sample_dataset):
  """Test model abstention when comparables count is below threshold."""
  model = ComparableMedianBaseline(sample_dataset, min_comparables=3)
  query = {
      "latitude": 40.1450,
      "longitude": 44.4850,
      "district": "Shengavit",
      "area_sqm": 40.0,
  }

  res = model.predict(query)

  assert (
      res["valuation_assessment"]["assessment_status"]
      == "INSUFFICIENT_DATA_ABSTAIN"
  )
  assert res["valuation_assessment"]["estimated_price_usd"] is None
  assert res["observed_market_statistics"]["insufficient_data"] is True
  assert res["observed_market_statistics"]["comparables_count"] == 1
