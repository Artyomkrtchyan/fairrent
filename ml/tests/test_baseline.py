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
      "listing_date": [
          "2026-10-01",
          "2026-10-05",
          "2026-10-10",
          "2026-10-02",
          "2026-10-08",
          "2026-10-12",
      ],
  }
  return pd.DataFrame(data)


def test_standard_valuation_success(sample_dataset):
  """Test standard request with area_sqm returning exact median valuation."""
  model = ComparableMedianBaseline(sample_dataset, min_comparables=3)
  query = {
      "latitude": 40.1811,
      "longitude": 44.5136,
      "district": "Kentron",
      "area_sqm": 70.0,
  }

  res = model.predict(query, query_date="2026-10-15")

  assert (
      res["valuation_assessment"]["assessment_status"] == "VALUATION_SUCCESS"
  )
  assert res["valuation_assessment"]["price_per_sqm_usd"] == 10.0
  assert res["valuation_assessment"]["estimated_price_usd"] == 700.0
  assert res["observed_market_statistics"]["comparables_count"] == 3
  assert res["observed_market_statistics"]["insufficient_data"] is False


def test_distance_filtering_out_of_bounds(sample_dataset):
  """1. Test that coordinate-only request at (0, 0) returns abstention."""
  model = ComparableMedianBaseline(sample_dataset, min_distance_km=3.0)
  query = {"latitude": 0.0, "longitude": 0.0, "area_sqm": None}

  res = model.predict(query)

  assert (
      res["valuation_assessment"]["assessment_status"]
      == "INSUFFICIENT_DATA_ABSTAIN"
  )
  assert res["valuation_assessment"]["estimated_price_usd"] is None
  assert res["observed_market_statistics"]["comparables_count"] == 0


def test_freshness_outdated_records_abstain():
  """2. Test that records older than max_freshness_days trigger abstention."""
  old_data = pd.DataFrame({
      "listing_id": [1, 2, 3],
      "district": ["Kentron"] * 3,
      "latitude": [40.1811] * 3,
      "longitude": [44.5136] * 3,
      "area_sqm": [50.0, 60.0, 70.0],
      "price_usd": [500.0, 600.0, 700.0],
      "listing_date": ["2020-01-01", "2020-01-02", "2020-01-03"],
  })
  model = ComparableMedianBaseline(old_data, max_freshness_days=60)
  query = {"latitude": 40.1811, "longitude": 44.5136, "area_sqm": 50.0}

  res = model.predict(query, query_date="2026-10-15")

  assert (
      res["valuation_assessment"]["assessment_status"]
      == "INSUFFICIENT_DATA_ABSTAIN"
  )
  assert res["observed_market_statistics"]["insufficient_data"] is True


def test_exclude_zero_area_and_invalid_prices():
  """3. Test exclusion of zero area and invalid prices."""
  invalid_data = pd.DataFrame({
      "listing_id": [1, 2, 3, 4, 5],
      "district": ["Kentron"] * 5,
      "latitude": [40.1811] * 5,
      "longitude": [44.5136] * 5,
      "area_sqm": [0.0, -10.0, 50.0, 60.0, 70.0],  # 2 invalid areas
      "price_usd": [500.0, 600.0, 0.0, 600.0, 700.0],  # 1 invalid price
      "listing_date": ["2026-10-01"] * 5,
  })
  model = ComparableMedianBaseline(invalid_data, min_comparables=2)
  query = {"latitude": 40.1811, "longitude": 44.5136, "area_sqm": 50.0}

  res = model.predict(query, query_date="2026-10-15")

  assert res["observed_market_statistics"]["comparables_count"] == 2
  assert res["valuation_assessment"]["estimated_price_usd"] == 500.0


def test_explanation_configured_reference_area(sample_dataset):
  """4. Test explanation describes default 60 sqm as configured reference area."""
  model = ComparableMedianBaseline(
      sample_dataset, default_reference_area_sqm=60.0
  )
  query = {"latitude": 40.1811, "longitude": 44.5136, "area_sqm": None}

  res = model.predict(query, query_date="2026-10-15")

  assert (
      "configured reference area (60.0 sqm)" in res["selection_explanation"]
  )
