# B04: CatBoost vs comparable-median baseline

Code: `ml/train_compare.py`. Tests: `ml/tests/test_train_compare.py`. Deps: `ml/requirements-train.txt`.

```
pip install -r ml/requirements-train.txt
python -m ml.train_compare --snapshot data/processed/v1.0.0 --version b04-v1.0.0
```

`--synthetic` exists only to smoke-test the pipeline. **Synthetic numbers are not findings.**
Real results require an A06 snapshot exported from the database.

## Fair-comparison design
- Split is read unchanged from A06 (chronological, duplicate-group isolated, post-boundary rows excluded).
- Imputation (district median area, district mode rooms), the baseline's comparable pool and the
  naive district median price/m² are fitted on **train only**. Validation is used only for CatBoost
  early stopping; test is scored once.
- Baseline = B03 `ComparableMedianBaseline` with the train split as its pool, queried at each test
  row's own observation date. Its 60-day freshness gate is disabled so the pool's age does not cause
  abstentions; abstentions on <3 comparables are reported. Headline comparison is on rows **both**
  models answer; CatBoost on all rows is reported alongside.
- `renovation` is excluded (always null in A06). `price_usd`, conversion fields and group/date keys
  are never inputs.

## Decision rule (fixed in advance)
Serve ML only if MAE < baseline MAE **and** median AE ≤ baseline median AE on common rows; otherwise
`serving_decision` is `baseline` and B03 stays the fallback. Provisional contract targets (MAE ≤ $45,
MAPE ≤ 12%, R² ≥ 0.82) are reported against, not used as the gate.

## Outputs (`artifacts/b04/<version>/`, git-ignored)
`model.cbm`, `preprocessing.json`, `feature_schema.json`, `metadata.json` (versions, seed, params,
dataset version + snapshot SHA-256, decision), `report.json` (metrics, per-district results, feature
importance, worst-error review, leakage checks), `SHA256SUMS.json` (for E04 integrity checks).

## Leakage checks (in `report.json`)
Group overlap across splits, chronological ordering, train/test near-duplicates under different group
ids, target-derived columns among features, and single-feature/target correlation > 0.95.

## Known limits
- Districts with < 30 test rows are flagged `small_sample_warning`.
- Baseline scoring is O(train × test) in pure Python; fine for thousands of rows, slow beyond ~50k.
- No prediction intervals here (B05).
