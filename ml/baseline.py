"""[B03] Comparable Property Median Baseline Engine.

Provides an explainable valuation baseline using comparable rental listings,
handling spatial distance filtering, freshness constraints, data cleaning,
and sparse data abstention aligned with ml/CONTRACT.md.
"""

from datetime import datetime
from typing import Any, Dict, Optional
import numpy as np
import pandas as pd


def haversine_distance_km(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
  """Calculates the great-circle distance between two points on the Earth in kilometers."""
  r = 6371.0  # Earth's radius in kilometers
  phi1, phi2 = np.radians(lat1), np.radians(lat2)
  delta_phi = np.radians(lat2 - lat1)
  delta_lambda = np.radians(lon2 - lon1)

  a = (
      np.sin(delta_phi / 2.0) ** 2
      + np.cos(phi1) * np.cos(phi2) * np.sin(delta_lambda / 2.0) ** 2
  )
  c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
  return float(r * c)


class ComparableMedianBaseline:
  """Calculates estimated monthly rent using median statistics of local comparables."""

  def __init__(
      self,
      dataset: pd.DataFrame,
      min_comparables: int = 3,
      max_freshness_days: int = 60,
      default_reference_area_sqm: float = 60.0,
      max_distance_km: float = 3.0,
  ):
    """Initialize the baseline estimator."""
    self.dataset = dataset.copy()
    self.min_comparables = min_comparables
    self.max_freshness_days = max_freshness_days
    self.default_reference_area_sqm = default_reference_area_sqm
    self.max_distance_km = max_distance_km

    # 3. Clean invalid records: exclude non-positive/non-finite areas and prices
    self._clean_dataset()

  def _clean_dataset(self) -> None:
    """Filter out zero-area, negative/non-finite prices, and invalid coordinates."""
    if self.dataset.empty:
      return

    # Ensure numeric types
    self.dataset["price_usd"] = pd.to_numeric(
        self.dataset["price_usd"], errors="coerce"
    )
    self.dataset["area_sqm"] = pd.to_numeric(
        self.dataset["area_sqm"], errors="coerce"
    )

    # Filter out non-finite or non-positive values
    valid_mask = (
        self.dataset["price_usd"].notna()
        & np.isfinite(self.dataset["price_usd"])
        & (self.dataset["price_usd"] > 0)
        & self.dataset["area_sqm"].notna()
        & np.isfinite(self.dataset["area_sqm"])
        & (self.dataset["area_sqm"] > 0)
    )
    self.dataset = self.dataset[valid_mask].copy()

    # Calculate price_per_sqm
    self.dataset["price_per_sqm"] = (
        self.dataset["price_usd"] / self.dataset["area_sqm"]
    )

    # Parse listing_date if present
    if "listing_date" in self.dataset.columns:
      self.dataset["listing_date"] = pd.to_datetime(
          self.dataset["listing_date"], errors="coerce"
      )

  def predict(
      self, input_payload: Dict[str, Any], query_date: Optional[str] = None
  ) -> Dict[str, Any]:
    """Computes baseline valuation for an input property query or coordinate payload."""
    lat = input_payload.get("latitude")
    lng = input_payload.get("longitude")
    district = input_payload.get("district")
    area_sqm = input_payload.get("area_sqm")
    rooms = input_payload.get("rooms")

    if lat is None or lng is None:
      raise ValueError(
          "Inference request requires valid 'latitude' and 'longitude'."
      )

    current_dt = (
        pd.to_datetime(query_date) if query_date else pd.Timestamp.now()
    )

    # 1 & 2. Select comparables filtered by distance and freshness
    comparables, freshness_days = self._select_comparables(
        lat, lng, district, rooms, current_dt
    )
    comparables_count = len(comparables)

    # Abstention Check
    if (
        comparables_count < self.min_comparables
        or (
            freshness_days is not None
            and freshness_days > self.max_freshness_days
        )
    ):
      reason = (
          f"Insufficient or outdated comparable listings in area"
          f" ({comparables_count} < {self.min_comparables} or freshness"
          f" {freshness_days}d > {self.max_freshness_days}d)."
      )
      return {
          "valuation_assessment": {
              "estimated_price_usd": None,
              "price_per_sqm_usd": None,
              "valuation_tier": "UNCERTAIN_OUTOF_SCOPE",
              "assessment_status": "INSUFFICIENT_DATA_ABSTAIN",
              "deviation_from_baseline_pct": None,
          },
          "observed_market_statistics": {
              "cluster_mean_price_usd": None,
              "observed_price_std_dev_usd": None,
              "comparables_count": comparables_count,
              "data_freshness_days": freshness_days,
              "insufficient_data": True,
          },
          "selection_explanation": f"{reason} Model abstained.",
      }

    # Compute Median Statistics
    median_price_per_sqm = float(comparables["price_per_sqm"].median())
    observed_mean_price = float(comparables["price_usd"].mean())
    observed_std_dev = (
        float(comparables["price_usd"].std()) if comparables_count > 1 else 0.0
    )

    is_coordinate_only = area_sqm is None or np.isnan(area_sqm)
    effective_area = (
        self.default_reference_area_sqm if is_coordinate_only else float(area_sqm)
    )

    estimated_price = round(median_price_per_sqm * effective_area, 2)
    price_per_sqm_rounded = round(median_price_per_sqm, 2)

    # 4. Explanation: Describe default area as configured reference area
    if is_coordinate_only:
      assessment_status = "COORDINATE_BASELINE_ONLY"
      valuation_tier = "Baseline Market Estimate"
      explanation = (
          f"Coordinate-only baseline valuation derived using configured"
          f" reference area ({self.default_reference_area_sqm} sqm) across"
          f" {comparables_count} local comparables within"
          f" {self.max_distance_km} km."
      )
    else:
      assessment_status = "VALUATION_SUCCESS"
      valuation_tier = "Fair Market Price"
      explanation = (
          f"Valuation estimated from median unit price"
          f" (${price_per_sqm_rounded}/sqm) of {comparables_count} comparable"
          f" listings in {district or 'local cluster'}."
      )

    return {
        "valuation_assessment": {
            "estimated_price_usd": estimated_price,
            "price_per_sqm_usd": price_per_sqm_rounded,
            "valuation_tier": valuation_tier,
            "assessment_status": assessment_status,
            "deviation_from_baseline_pct": 0.0,
        },
        "observed_market_statistics": {
            "cluster_mean_price_usd": round(observed_mean_price, 2),
            "observed_price_std_dev_usd": round(observed_std_dev, 2),
            "comparables_count": comparables_count,
            "data_freshness_days": freshness_days,
            "insufficient_data": False,
        },
        "selection_explanation": explanation,
    }

  def _select_comparables(
      self,
      lat: float,
      lng: float,
      district: Optional[str],
      rooms: Optional[int],
      current_dt: pd.Timestamp,
  ) -> tuple[pd.DataFrame, Optional[int]]:
    """Selects matching comparable listings applying distance and freshness filters."""
    filtered = self.dataset.copy()

    # 1. Distance filtering
    if "latitude" in filtered.columns and "longitude" in filtered.columns:
      distances = [
          haversine_distance_km(lat, lng, r_lat, r_lng)
          for r_lat, r_lng in zip(
              filtered["latitude"], filtered["longitude"], strict=False
          )
      ]
      filtered["distance_km"] = distances
      filtered = filtered[filtered["distance_km"] <= self.max_distance_km]

    # Optional District filter
    if district and "district" in filtered.columns and not filtered.empty:
      district_matches = filtered[
          filtered["district"].str.lower() == district.lower()
      ]
      if len(district_matches) >= self.min_comparables:
        filtered = district_matches

    # Calculate freshness from observation dates
    freshness_days = None
    if "listing_date" in filtered.columns and not filtered.empty:
      valid_dates = filtered["listing_date"].dropna()
      if not valid_dates.empty:
        latest_date = valid_dates.max()
        freshness_days = int((current_dt - latest_date).days)
        freshness_days = max(0, freshness_days)

        # 2. Freshness filtering
        fresh_mask = (
            current_dt - filtered["listing_date"]
        ).dt.days <= self.max_freshness_days
        filtered = filtered[fresh_mask]

    return filtered, freshness_days
