# [B02] Machine Learning Feature, Evaluation & Integration Contract

This document defines the binding data schema, evaluation methodology, and API contract for the **Machine Learning (ML)** component, fully aligned with the shared project contracts in **PR #38 (C01)**.

---

## 1. Input Specifications & Null-Handling Strategy

### A. Training Record Requirements vs. Inference API Inputs
* **Training Dataset (Database & Pipeline Requirements):**
  * Historical records must contain valid target values (`price_usd`), verified geotags (`latitude`, `longitude`), and creation timestamps (`listing_date`).
  * Listings missing critical structural metadata or geotags are dropped during data cleaning.
  * Every record must contain a `dedup_group_id` (hash of normalized location + structural features) to isolate duplicate re-listings.

* **Inference API Payload (Flexible Scopes):**
  * Supports full listing payloads (e.g., standard property evaluation).
  * Supports **coordinate-only requests** (e.g., when a user clicks a pin on the interactive map).

### B. Shared Schema & Model Imputation Matrix (Aligned with C01 / PR #38)

| Field Name | Data Type | Inference Required? | API Null Allowed? | Model-Side Imputation Strategy | Unit / Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `latitude` | Float | **Yes** | No | **Reject Request** | WGS84 latitude coordinate |
| `longitude` | Float | **Yes** | No | **Reject Request** | WGS84 longitude coordinate |
| `area_sqm` | Float | Optional | Yes | District Median Imputation | Living space area in $m^2$ |
| `rooms` | Integer | Optional | Yes | District Mode Imputation | Number of rooms |
| `building_type` | String | Optional | Yes | Constant `"unknown"` | Construction material (`monolith`, `stone`, `panel`) |
| `renovation` | String | Optional | Yes | Constant `"none"` | Interior quality (`cosmetic`, `designer`, `none`) |
| `district` | String | Optional | Yes | PostGIS Spatial Join Lookup | Yerevan municipal district |
| `distance_metro_m` | Float | Optional | Yes | Nearest spatial lookup or $99999.0$ | Geodesic distance to nearest metro station ($m$) |
| `distance_center_m` | Float | Optional | Yes | Geodesic distance to Republic Sq ($m$) | Geodesic distance to city center ($m$) |
| `distance_university_m` | Float | Optional | Yes | Spatial lookup or $99999.0$ | Geodesic distance to nearest university ($m$) |

---

## 2. API Response Contract & Variance Separation

The inference output strictly distinguishes **observed spatial market variance** (from local database clusters) from **ML model prediction confidence intervals**.

```json
{
  "request_id": "req_c01_9921a",
  "coordinates": {
    "latitude": 40.1811,
    "longitude": 44.5136
  },
  "versions": {
    "model_version": "v1.2.0-catboost",
    "rule_engine_version": "v1.0.0-ontology"
  },
  "valuation_assessment": {
    "estimated_price_usd": 750.00,
    "price_per_sqm_usd": 11.54,
    "valuation_tier": "Fair Market Price",
    "deviation_from_baseline_pct": +2.4
  },
  "observed_market_statistics": {
    "cluster_mean_price_usd": 732.00,
    "observed_price_std_dev_usd": 85.50,
    "comparables_count": 14,
    "data_freshness_days": 6,
    "insufficient_data": false
  },
  "ml_prediction_interval": {
    "lower_bound_usd": 670.00,
    "upper_bound_usd": 830.00,
    "confidence_level": 0.95,
    "interval_width_usd": 160.00
  },
  "feature_attributions": [
    { "feature": "distance_metro_m", "impact_pct": +11.2, "direction": "positive" },
    { "feature": "renovation", "impact_pct": +6.5, "direction": "positive" }
  ]
}
