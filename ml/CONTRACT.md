# [B02] ML Feature & Evaluation Contract

This document defines the formal API & Data contract between **Machine Learning (ML)**, **Data Engineering**, and **Backend** roles for the FairRent real estate valuation platform.

---

## 1. Feature Specifications & Input Schema

### Input Features Matrix

| Feature Name | Type | Unit / Format | Missing-Value Behavior | Description |
| :--- | :--- | :--- | :--- | :--- |
| `property_id` | String | UUID / Text | Reject (Required) | Unique identifier for the property |
| `area_sqm` | Float | $m^2$ | Reject if $\le 0$ or Null | Total living space area |
| `rooms` | Integer | Count ($1, 2, 3...$) | Impute with Median by District | Number of rooms |
| `building_type` | Categorical | Enum (`monolith`, `panel`, `stone`) | Impute with `"unknown"` | Construction material |
| `renovation` | Categorical | Enum (`cosmetic`, `designer`, `none`) | Impute with `"none"` | Renovation quality |
| `district` | Categorical | Yerevan District Enum | Reject (Required) | Administrative district (e.g., Kentron, Arabkir) |
| `latitude` | Float | Decimal Degrees | Reject if Null | Geographic WGS84 coordinate |
| `longitude` | Float | Decimal Degrees | Reject if Null | Geographic WGS84 coordinate |
| `distance_metro_m` | Float | Meters ($m$) | Impute with $99999.0$ (Far) | Geodesic distance to nearest metro station |
| `distance_center_m` | Float | Meters ($m$) | Impute with District Mean | Geodesic distance to Republic Square |
| `distance_university_m` | Float | Meters ($m$) | Impute with $99999.0$ (Far) | Geodesic distance to nearest university node |
| `listing_date` | Datetime | ISO 8601 (`YYYY-MM-DD`) | Reject (Required) | Date advertisement was posted |

---

## 2. Prediction Response Structure (API Contract)

The model inference endpoint receives a property feature payload and returns a structured JSON response containing point predictions, valuation ranges, standard deviations, and explainability signals:

```json
{
  "property_id": "prop_7841a",
  "estimated_price_usd": 750.00,
  "prediction_interval": {
    "lower_bound_usd": 680.00,
    "upper_bound_usd": 820.00,
    "std_dev_usd": 70.00,
    "confidence_level": 0.95
  },
  "valuation_assessment": {
    "tier": "Fair Market Price",
    "deviation_from_baseline_pct": 2.5,
    "risk_flag": "NORMAL"
  },
  "feature_attributions": [
    { "feature": "distance_metro_m", "impact_pct": +12.5, "direction": "positive" },
    { "feature": "renovation", "impact_pct": +8.0, "direction": "positive" }
  ]
}