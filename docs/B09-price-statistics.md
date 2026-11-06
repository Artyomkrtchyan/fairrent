# B09 – Coordinate-based price statistics and assessment

Module: `ml/market_stats.py` (Pandas + scikit-learn `BallTree`, haversine). Tests: `ml/tests/test_market_stats.py`.
CLI: `python -m ml.market_stats listings.csv --lat 40.18 --lon 44.51 --as-of 2026-11-01T12:00:00+00:00 [--area 50 --rooms 2]`

## Rules (`b09-cohort-v1`)
| Rule | Value |
|---|---|
| Inventory | one observation per listing, dated by `last_seen_at` |
| Window | inclusive Asia/Yerevan local dates, `window_days` default 30, cap 60 |
| Radius | geodesic ≤ `radius_m` (default 1000, max 5000), boundary inclusive |
| Comparability | exact `rooms` when supplied; optional district; no silent widening |
| Duplicates | eligibility first, then latest observation per dedup group; tie → listing ID ascending; ungrouped counted once |
| Minimum sample | 3 (**provisional – data owner must confirm**) |

## Output
Cohort metadata (incl. counts at each filtering stage), count, mean, sample std (n−1) in USD/month and USD/m²,
`area_comparables_count`, and an assessment:
- `INSUFFICIENT_DATA_ABSTAIN` – below minimum sample (monthly, or with-area for property-specific); no estimate.
- `COORDINATE_BASELINE_ONLY` – area/rooms missing; estimate = observed cohort mean.
- `ASSESSED` (property-specific) – mean USD/m² × area, with `observed_dispersion_usd` (std/m² × area).
`prediction_interval` is always `None` here: observed dispersion is not a prediction interval (see B05).
Outside the provisional coverage bbox → `OutsideCoverage`.

## Difference from the backend inline logic (`valuation_service.py`)
The backend de-duplicates before the rooms/district filter; the contract says "latest eligible observation per duplicate group",
which this module implements (eligibility first). Example: a group's newest listing has 3 rooms, an older one 2 rooms; for a
2-room query this module keeps the older one, the backend drops the group. Backend owner/C11 should align.
Coverage here is the provisional bbox, not the A05 polygon.
