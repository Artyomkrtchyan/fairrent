# [B02] Machine Learning Feature, Evaluation & Integration Contract

This document defines the binding data schema, evaluation methodology, and API contract for the **Machine Learning (ML)** component, aligned with the shared project contracts in **PR #38 (C01)**.

---

## 1. Input Specifications & Null-Handling Strategy

### A. Training Record Requirements vs. Inference API Inputs
* **Training Dataset (Database & Pipeline Requirements):**
  * Historical records must contain valid target values (`price_usd`), verified geotags (`latitude`, `longitude`), and creation timestamps (`listing_date`).
  * Listings missing critical structural metadata or geotags are dropped during data cleaning.
  * Every record must contain a `dedup_group_id` (hash of normalized location + structural features) to isolate duplicate re-listings.

* **Inference API Payload (Flexible Scopes):**
  * Supports full listing payloads (e.g., standard property evaluation).
  * Supports **coordinate-only requests** (e.g., when a user clicks a pin on the interactive map without specifying property details).

### B. Shared Schema & Model Imputation Matrix

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

## 2. API Response Structure & Payloads

### A. Full Feature Request Response Example

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
    "assessment_status": "VALUATION_SUCCESS",
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
```
 B. Coordinate-Only Request Response Example (Property Details Unavailable)
When a request contains only coordinates (latitude, longitude) without property attributes (area_sqm, rooms, etc.), the model estimates local baseline stats and reference metrics using area defaults:
```
{
  "request_id": "req_coord_4412b",
  "coordinates": {
    "latitude": 40.1811,
    "longitude": 44.5136
  },
  "area_reference": {
    "district": "Kentron",
    "reference_area_sqm": 60.0,
    "note": "Valuation computed using district median reference area unit"
  },
  "versions": {
    "model_version": "v1.2.0-catboost",
    "rule_engine_version": "v1.0.0-ontology"
  },
  "valuation_assessment": {
    "estimated_price_usd": 690.00,
    "price_per_sqm_usd": 11.50,
    "valuation_tier": "Baseline Market Estimate",
    "assessment_status": "COORDINATE_BASELINE_ONLY",
    "deviation_from_baseline_pct": 0.0
  },
  "observed_market_statistics": {
    "cluster_mean_price_usd": 690.00,
    "observed_price_std_dev_usd": 92.00,
    "comparables_count": 10,
    "data_freshness_days": 12,
    "insufficient_data": false
  },
  "ml_prediction_interval": {
    "lower_bound_usd": 598.00,
    "upper_bound_usd": 782.00,
    "confidence_level": 0.95,
    "interval_width_usd": 184.00
  },
  "feature_attributions": []
}
```

C. Insufficient-Data Behavior & Model AbstentionIf local comparable listings count comparables_count < 3 OR data freshness data_freshness_days > 60 OR location lies outside municipal estimation boundaries:

-Flag Behavior: insufficient_data is explicitly set to true.
-Assessment Status: assessment_status returns "INSUFFICIENT_DATA_ABSTAIN".
-Valuation Status Tier: valuation_tier returns "UNCERTAIN_OUTOF_SCOPE".
-Null Fields: Specific point estimate metrics become null while general market stats remain visible if available:valuation_assessment.estimated_price_usd -> null
valuation_assessment.price_per_sqm_usd -> null
valuation_assessment.deviation_from_baseline_pct -> null
ml_prediction_interval.lower_bound_usd -> null
ml_prediction_interval.upper_bound_usd -> null
ml_prediction_interval.interval_width_usd -> null
feature_attributions -> []

```
{
  "request_id": "req_abstain_001c",
  "coordinates": {
    "latitude": 40.0511,
    "longitude": 44.3120
  },
  "versions": {
    "model_version": "v1.2.0-catboost",
    "rule_engine_version": "v1.0.0-ontology"
  },
  "valuation_assessment": {
    "estimated_price_usd": null,
    "price_per_sqm_usd": null,
    "valuation_tier": "UNCERTAIN_OUTOF_SCOPE",
    "assessment_status": "INSUFFICIENT_DATA_ABSTAIN",
    "deviation_from_baseline_pct": null
  },
  "observed_market_statistics": {
    "cluster_mean_price_usd": null,
    "observed_price_std_dev_usd": null,
    "comparables_count": 1,
    "data_freshness_days": 85,
    "insufficient_data": true
  },
  "ml_prediction_interval": {
    "lower_bound_usd": null,
    "upper_bound_usd": null,
    "confidence_level": 0.95,
    "interval_width_usd": null
  },
  "feature_attributions": []
}

```
3. Data Leakage Prevention & Dataset Splitting
1) Strict Chronological Splits:
   Data is split chronologically by listing_date: Train (70%) -> Validation (15%) -> Test (15%).
   Models are strictly evaluated on future time windows relative to their training data.
2) Duplicate-Group Isolation:
   Properties re-listed or scraped from multiple sources share a unique dedup_group_id.
   All records sharing the same dedup_group_id are isolated within the same dataset split (Train, Val, or Test) to eliminate cross-fold leakage.

   
4. Model Evaluation Methodology
   
   A. Baselines
   1.Naive Market Baseline: District median price per m^2 * area_sqm
   2.Knowledge Engineering Baseline: Ontology distance-tier baseline engine.
   
   B. Error Metrics
   
   MAE (Mean Absolute Error): Primary metric for average dollar discrepancy (<=$45).
   MedAE (Median Absolute Error): Robust error metric immune to extreme market outliers.
   RMSE (Root Mean Squared Error): Penalty metric for severe valuation errors.
   MAPE (Mean Absolute Percentage Error): Target $\le 12\%$ relative error.
   R^2 Score: Target $\ge 0.82$ variance coverage.

   C. Interval Coverage & Width Metrics
   
   Empirical  Coverage Target: The nominal 95% prediction interval must cover >= 92\% of true test
   prices.
   Interval Width Ratio: (Interval Width/Predicted Price) <= 0.22
   
   D. Neighborhood-Level Evaluation
   
   Model performance (MAE, MedAE, MAPE) is evaluated independently across each Yerevan administrative
   district (e.g., Kentron, Arabkir, Shengavit, Malatia-Sebastia) to guarantee uniform valuation
   accuracy across both high-value and peripheral market zones.


