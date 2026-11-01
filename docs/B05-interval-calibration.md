# B05: calibrated prediction intervals and abstention

Code: `ml/intervals.py` (library, no CatBoost needed), `ml/calibrate_intervals.py` (CLI).
Tests: `ml/tests/test_intervals.py`, `ml/tests/test_calibrate_intervals.py`.

```
python -m ml.calibrate_intervals --b04 artifacts/b04/b04-v1.0.0-grouped-merged \
    --snapshot data/processed/v1.0.0-grouped-merged --version b05-v1.0.0
```

Use the **same snapshot** B04 trained on: the tool refuses a different SHA-256, altered B04 files
(`SHA256SUMS.json`), or different split sizes. Outputs go to `artifacts/b05/<version>/` (git-ignored):
`interval_calibration.json` (quantiles, serving gate, binding to the B04 model SHA-256), `b05_report.json`,
`SHA256SUMS.json`. The calibration file is deterministic; the report carries a timestamp.

## Method
Split conformal prediction with relative scores `|y - pred| / pred`. The interval is
`pred * (1 ± q)` (lower bound clipped at 0), where `q` is the `ceil((n+1)·level)`-th smallest calibration
score. Levels 0.80, 0.90 and 0.95 are stored; 0.95 is the primary (contract) level.

* **No test labels.** `q` comes only from the **validation** split, using only rows that pass the serving
  gate (the population intervals are served for). The test split is scored, never fitted, selected or tuned on.
* **Method fixed in advance.** `relative` is the primary method because rent errors grow with price. `absolute`
  and `relative_by_district` (per-district quantiles, global fallback under 100 calibration rows) are reported on
  the test split for comparison and are **not** used to choose the primary.
* **Binding.** The calibration records the B04 model SHA-256. A calibration is valid only for that model.

## What the coverage number means (and does not)
Coverage `>= level` is a *marginal* average over served rows, and only if calibration and serving rows are
exchangeable. It is not a guarantee for one listing, one district or one price level; see
`conditional_coverage` in the report (by district, predicted-price quartile and area bin) and
`worst_district_coverage_n_ge_30`.

## Response block and price_status
`prediction_interval(...)` returns the contract's `ml_prediction_interval`: `lower_bound_usd`, `upper_bound_usd`,
`confidence_level`, `interval_width_usd`, plus `calibration_version`. Bounds are rounded **outward** to cents so
rounding cannot break coverage or `lower <= expected <= upper`, and the width is computed from the rounded
bounds. With no calibration, no prediction, or any gate reason, all four fields are `null` and
`calibration_version` is absent.

`price_status(asking_price_usd, interval)`: `within_range` when `lower <= asking <= upper` (edges inclusive),
`above_range` above the upper bound, `below_range` below the lower bound, `insufficient_data` when the asking
price is missing/non-finite/non-positive or either bound is null. Assessment status
(`COORDINATE_BASELINE_ONLY`, `INSUFFICIENT_DATA_ABSTAIN`, ...) stays separate, as in `docs/contract-semantics.md`.

## Serving gate (abstention)
Fitted on the **train** split only; rules fixed in advance, not tuned on test results. No interval is returned for:

| reason code | rule |
| --- | --- |
| `missing_or_invalid_coordinates` | latitude/longitude missing or out of range |
| `coordinate_only_no_calibrated_interval` | `area_sqm` unknown (contract: coordinate-only intervals are not calibrated) |
| `area_outside_training_range` | area outside the 0.5%-99.5% training quantiles |
| `sparse_local_training_data` | fewer than 3 training listings in the 3x3 grid block (0.01° cells) around the point |

Training coordinates are stored as grid-cell counts, not raw points. The count/threshold values are provisional,
like the contract's `< 3 comparables` rule.

## Evaluation in `b05_report.json`
Held-out coverage and width per level (served rows, and all rows for transparency); abstention counts and the
coverage those rows *would* have had; variants; conditional coverage; and scenarios:
* **sparse**: test rows with thin local training data;
* **missing features**: rooms, floors, landmark distances, all optional inputs, and area blanked, with the coverage
  change and MAE change (area-missing intervals are withheld; the number shows why);
* **out-of-distribution**: natural out-of-range areas plus synthetic probes (location shifted 0.3° north, area at
  twice the training maximum) that must be withheld;
* **price_status checks**: statuses at the true price, at 2x and 0.25x the prediction, with no asking price, and
  structural checks (bounds enclose the prediction, width equals upper minus lower, withheld blocks all null).

## Provisional targets (`ml/CONTRACT.md` 4.C)
Coverage of the nominal 95% interval `>= 92%`; median width / predicted price `<= 0.22`. Both are reported in
`targets_vs_results` and **not** used to tune anything. With realistic rent noise (B04 MAPE about 17%), a 95% interval
is necessarily much wider than 22% of the price, so the width target is expected to fail; the owners should
revisit it or accept a lower nominal level (0.80 / 0.90 are reported).

## Confidence limitations
* The interval is for the **asking** price of listings, not the agreed rent.
* Non-temporal snapshots (one-date scrape) measure coverage on a random sample of the same period; future
  listings are drawn from a shifted market, so real coverage can be lower. Re-calibrate on a chronological split.
* Calibration reuses the validation split that B04 used for early stopping, so residuals can be slightly
  optimistic (compare `test_to_validation_median_ae_ratio`).
* Units from the same building can sit in both calibration and test even after near-duplicate merging.
* Coverage is thinner in the tails (most expensive predictions, largest areas); read `conditional_coverage`.
* Dropping optional inputs keeps the same quantile while the real error grows; `missing_features` shows by how much.
* Without renovation or building-type data the model cannot explain a lot of price variation, which is why
  intervals are wide.
* Never replace a withheld interval with the observed standard deviation (contract).

## For B07
Load `interval_calibration.json` with `IntervalCalibration.from_json` and `ServingGate.from_json`, verify the
recorded `b04_model_sha256` against the loaded model, call `ServingGate.reasons` on the request, then
`prediction_interval(...)` and `price_status(...)`.
