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
  abstentions; abstentions on <3 comparables are reported. Headline and per-district comparisons use rows **both**
  models answer; CatBoost on the full cohort and baseline coverage are reported separately.
- `renovation` is excluded (always null in A06). `price_usd`, conversion fields and group/date keys
  are never inputs.

## One-date snapshots: grouped-random fallback (non-temporal)
A06's split is chronological, which needs at least three distinct observation dates. A single scrape
imported in one run stamps every listing with the same `last_seen_at`, so the default export puts all
rows in `train` and B04 stops ("Validation split is empty").

For that case only, export with an explicit fallback:

```
python -m data_pipeline.export_dataset --as-of 2026-10-31 --version v1.0.0-grouped --split-mode grouped-random --merge-near-duplicates
python -m ml.train_compare --snapshot data/processed/v1.0.0-grouped --version b04-v1.0.0-grouped
```

- Duplicate groups are ordered by SHA-256(seed:`dedup_group_id`) and cut 70/15/15, so the split is
  deterministic, independent of database row order, and keeps every group in one split. The seed is
  recorded in `manifest.json`.
- `--as-of` must be on or after the import date (rows observed later than the end of that day are excluded).
- The manifest and `quality_report.json` are labeled `temporal: false`. B04 reports the chronological check as
  `not_applicable` (it would pass trivially on one date), still enforces every other leakage check, and adds
  `evidence_level` and `limitations` to its outputs.
- **This is not a forward-looking evaluation.** Metrics are in-time estimates and are optimistic. Per
  `docs/contract-semantics.md`, the A and B owners must explicitly agree this fallback before the numbers are
  used as project evidence. Treat the serving decision as provisional and re-run on a chronological snapshot once
  at least three distinct observation dates exist.
- `--merge-near-duplicates` is needed on scraped data. Listings that repeat one apartment (or identical units in one
  building) share rounded coordinates, area and USD price but have separate groups, so a split can put twins in
  train and test; B04's near-duplicate leakage check then refuses to train. The flag merges such groups into one
  (same fingerprint the B04 check uses), keeps every row, and reports counts in `quality_report.json`
  (`duplicates.near_duplicate_merge`). On the 2026-10-29 scrape about 19% of listings sit in such clusters. Big
  towers with many identical units form large groups, so a few clusters can weigh heavily in the test set.
- The default mode is unchanged.

## Decision rule (fixed in advance)
Serve ML only if MAE < baseline MAE **and** median AE ≤ baseline median AE on common rows; otherwise
`serving_decision` is `baseline` and B03 stays the fallback. Provisional contract targets (MAE ≤ $45,
MAPE ≤ 12%, R² ≥ 0.82) are reported against, not used as the gate.

## Outputs (`artifacts/b04/<version>/`, git-ignored)
`model.cbm`, `preprocessing.json`, `feature_schema.json`, `metadata.json` (versions, seed, params,
dataset version + snapshot SHA-256, decision), `report.json` (metrics, per-district results, feature
importance, worst-error review, leakage checks), `SHA256SUMS.json` (for E04 integrity checks).

## Leakage checks
Run **before any training**; a failure raises `SplitValidationError` and no model or artifacts are
written. The same result is saved in `report.json`. The experiment fails on any of: group overlap
across splits, non-chronological splits, near-duplicate rows (coords + area + price) in more than one
split under different group ids, target-derived columns among the features, or a single-feature/target
correlation above 0.95.

## Known limits
- Districts with < 30 test rows are flagged `small_sample_warning`.
- Baseline scoring is O(train × test) in pure Python; fine for thousands of rows, slow beyond ~50k.
- No prediction intervals here (B05).
