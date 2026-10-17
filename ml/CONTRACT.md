# [B02] Machine Learning Feature, Evaluation & Integration Contract

This document defines the binding data schema, evaluation methodology, and API contract for the **Machine Learning (ML)** component, aligned with the shared project contracts in **PR #38 (C01)**.

> **Status of numeric thresholds:** All sample-size, freshness, and performance thresholds in this document (e.g., `comparables_count < 3`, `data_freshness_days > 60`, MAE, MAPE, R², coverage, and interval-width targets) are **provisional targets**. They are to be validated against measured results in a later stage and may be revised. No trained-model results are claimed here.

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
| `area_sqm` | Float | Optional | Yes | District Median Imputation (training-fitted) | Living space area in $m^2$ |
| `rooms` | Integer | Optional | Yes | District Mode Imputation (training-fitted) | Number of rooms |
| `building_type` | String | Optional | Yes | Constant `"unknown"` | Construction material (`monolith`, `stone`, `panel`) |
| `renovation` | String | Optional | Yes | Constant `"none"` | Interior quality (`cosmetic`, `designer`, `none`) |
| `district` | String | Optional | Yes | PostGIS Spatial Join Lookup | Yerevan municipal district |
| `distance_metro_m` | Float | Optional | Yes | Nearest spatial lookup or $99999.0$ | Geodesic distance to nearest metro station ($m$) |
| `distance_center_m` | Float | Optional | Yes | Geodesic distance to Republic Sq ($m$) | Geodesic distance to city center ($m$) |
| `distance_university_m` | Float | Optional | Yes | Spatial lookup or $99999.0$ | Geodesic distance to nearest university ($m$) |

**Training-only fitting rule:** All statistics used for imputation (district median `area_sqm`, district mode `rooms`) and all baseline reference statistics (district median price per $m^2$, district reference area, ontology tier calibration) are **fitted exclusively on the training split**. The fitted values are frozen, versioned with the model artifact, and reused unchanged for validation, test, and inference. Validation and test data never contribute to these statistics.

---

## 2. API Response Structure & Payloads

### A. Full Feature Request Response Example

The values below are illustrative. The interval is labeled `confidence_level: 0.95` only because it is assumed to come from an interval method calibrated on held-out validation data (see Section 4.C).

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
    "deviation_from_baseline_pct": 2.4
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
    { "feature": "distance_metro_m", "impact_pct": 11.2, "direction": "positive" },
    { "feature": "renovation", "impact_pct": 6.5, "direction": "positive" }
  ]
}
```

Signed values are represented without a leading `+` (valid JSON); sign information for attributions is carried by the `direction` field.

### B. Coordinate-Only Request Response Example (Property Details Unavailable)

When a request contains only coordinates (`latitude`, `longitude`) without property attributes (`area_sqm`, `rooms`, etc.), the model estimates local baseline stats and reference metrics using the training-fitted district median reference area.

**Prediction interval policy:** A coordinate-only response must **not** present an interval as a 95% prediction interval unless that interval has been separately calibrated for coordinate-only requests. Until such calibration exists, `lower_bound_usd`, `upper_bound_usd`, `interval_width_usd`, and `confidence_level` are returned as `null`. (The observed price standard deviation must not be reused as an interval half-width.) If a synthetic interval is later introduced, it must be independently defined, explicitly labeled as synthetic, and must not carry a `confidence_level` claim.

```json
{
  "request_id": "req_coord_4412b",
  "coordinates": {
    "latitude": 40.1811,
    "longitude": 44.5136
  },
  "area_reference": {
    "district": "Kentron",
    "reference_area_sqm": 60.0,
    "note": "Valuation computed using district median reference area unit (fitted on training data)"
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
    "lower_bound_usd": null,
    "upper_bound_usd": null,
    "confidence_level": null,
    "interval_width_usd": null
  },
  "feature_attributions": []
}
```

### C. Insufficient-Data Behavior & Model Abstention

If local comparable listings count `comparables_count < 3` **OR** data freshness `data_freshness_days > 60` **OR** location lies outside municipal estimation boundaries (the count and freshness thresholds are **provisional**, to be validated later):

- **Flag Behavior:** `insufficient_data` is explicitly set to `true`.
- **Assessment Status:** `assessment_status` returns `"INSUFFICIENT_DATA_ABSTAIN"`.
- **Valuation Status Tier:** `valuation_tier` returns `"UNCERTAIN_OUTOF_SCOPE"`.
- **Null Fields:** Specific point estimate metrics become `null`, while general market stats remain visible if available:
  - `valuation_assessment.estimated_price_usd` -> `null`
  - `valuation_assessment.price_per_sqm_usd` -> `null`
  - `valuation_assessment.deviation_from_baseline_pct` -> `null`
  - `ml_prediction_interval.lower_bound_usd` -> `null`
  - `ml_prediction_interval.upper_bound_usd` -> `null`
  - `ml_prediction_interval.interval_width_usd` -> `null`
  - `ml_prediction_interval.confidence_level` -> `null`
  - `feature_attributions` -> `[]`

```json
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
    "confidence_level": null,
    "interval_width_usd": null
  },
  "feature_attributions": []
}
```

---

## 3. Data Leakage Prevention & Dataset Splitting

1. **Strict Chronological Splits:**
   Data is split chronologically by `listing_date`: Train (70%) -> Validation (15%) -> Test (15%). Cutoff dates are chosen from the chronological ordering of records. Models are strictly evaluated on future time windows relative to their training data.

2. **Duplicate-Group Isolation:**
   Properties re-listed or scraped from multiple sources share a unique `dedup_group_id`. All retained records sharing the same `dedup_group_id` are placed within the same dataset split (Train, Val, or Test) to eliminate cross-fold leakage.

3. **Handling Duplicate Groups That Cross Chronological Boundaries:**
   - Each group is anchored to its **earliest** `listing_date` and assigned to the split whose time window contains that anchor date.
   - Member records whose `listing_date` falls **after the end of the assigned split's window** are **excluded** from all splits (Train, Val, and Test). They are never moved into an earlier split, so no future observation enters training, and never placed in a later split, so no group is split across folds.
   - Excluded records are logged (count per split boundary) for auditability.
   - Because of these exclusions, realized split proportions may deviate slightly from 70/15/15. The realized proportions and the number of excluded records are reported with the dataset version.

4. **Training-Only Fitting of Statistics:**
   Imputation values (district median `area_sqm`, district mode `rooms`, district reference area for coordinate-only requests) and baseline reference statistics (district median price per $m^2$ for the Naive Market Baseline, and ontology tier calibration for the Knowledge Engineering Baseline) are fitted using **training data only**. Validation and test records are never used to compute them; the frozen values are applied unchanged to validation, test, and inference.

---

## 4. Model Evaluation Methodology

> All targets in this section are **provisional** and will be validated against measured results later.

### A. Baselines
1. **Naive Market Baseline:** District median price per $m^2$ (training-fitted) $\times$ `area_sqm`.
2. **Knowledge Engineering Baseline:** Ontology distance-tier baseline engine (training-calibrated).

### B. Error Metrics
- **MAE (Mean Absolute Error):** Primary metric for average dollar discrepancy (provisional target $\le \$45$).
- **MedAE (Median Absolute Error):** Robust error metric immune to extreme market outliers.
- **RMSE (Root Mean Squared Error):** Penalty metric for severe valuation errors.
- **MAPE (Mean Absolute Percentage Error):** Provisional target $\le 12\%$ relative error.
- **R² Score:** Provisional target $\ge 0.82$ variance coverage.

### C. Interval Coverage & Width Metrics
- **Calibration requirement:** An interval may be labeled with a nominal `confidence_level` (e.g., 0.95) only if it is produced by a method calibrated on held-out validation data (e.g., conformal calibration). Uncalibrated spreads, such as the observed price standard deviation, must not be reported as prediction intervals.
- **Empirical Coverage Target (provisional):** The nominal 95% prediction interval must cover $\ge 92\%$ of true test prices.
- **Interval Width Ratio (provisional):** (Interval Width / Predicted Price) $\le 0.22$.

### D. Neighborhood-Level Evaluation
Model performance (MAE, MedAE, MAPE) is evaluated independently across each Yerevan administrative district (e.g., Kentron, Arabkir, Shengavit, Malatia-Sebastia) to guarantee uniform valuation accuracy across both high-value and peripheral market zones.
