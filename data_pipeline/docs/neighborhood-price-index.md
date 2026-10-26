# A07 weekly neighborhood asking-price index

## Contract and interpretation

The index reports weekly **advertised asking rents**, not signed contracts, completed leases,
or transaction prices. `median_asking_price_usd_month` is USD/month.
`median_asking_price_usd_per_sqm_month` is USD/month/m². These are asking-price statistics,
not a valuation.

A reporting week starts Monday 00:00 in `Asia/Yerevan` and ends at the following Monday
00:00 local time (exclusive), covering Monday through Sunday. The query converts those
local boundaries to UTC before selecting `last_seen_at`. The stored `period_start` is
Monday and `period_end` is Sunday. A record is eligible when it is currently active,
belongs to the requested source, has a `last_seen_at` inside that local reporting week,
maps to a registered district, has an A04 `property_id`, has a valid normalized
USD/month price, and has a supported long-term source period. Daily and weekly rentals,
unknown periods, invalid prices, unknown districts, and ungrouped listings are excluded.

To prevent duplicate ads from overweighting the index, eligible active listings are
grouped by A04 property ID and only the latest observation in the reporting week is kept
for each property. If two observations have the same timestamp, the listing with the larger
database ID is selected deterministically. The selected listing's monthly asking price and,
when its area is valid, USD/month/m² are used. District medians are then calculated across
unique properties.
`sample_count` counts unique properties with a valid monthly asking price;
`per_sqm_sample_count` counts the subset with valid areas.

## Sparse neighborhoods and freshness

The minimum sample is five unique properties. Counts are always returned. Each metric is
published only when its own sample count reaches five; otherwise its median is `null` and
its status is `insufficient_data`. Monthly price and unit-price statuses are independent.

`data_as_of` is the latest source observation used in that district-week. `generated_at`
is when the aggregate was built. Older weekly periods naturally become stale as time passes;
consumers can compare `data_as_of` to their freshness policy.

The inventory selection uses the current `is_active` state and observations recorded in
the requested week. The source schema does not keep a complete historical active-state
snapshot for every listing, so rebuilding an old week after later deactivation may not
reproduce the original inventory. Preserve a published weekly row for historical reporting.

## Generate and query

Apply the migration and configure `DATABASE_URL`, then run the pipeline after the weekly
collection has completed. From the repository root:

```text
cd database
alembic -c alembic.ini upgrade head
cd ..
python -m data_pipeline.aggregate_neighborhoods --week-start 2026-10-19
```

`--week-start` must be a Monday in the `Asia/Yerevan` calendar. The command atomically
replaces aggregates for that week and leaves listing/source tables unchanged. It reports
only aggregate counts, not listing identifiers. The stable backend handoff is the database view
`weekly_neighborhood_asking_price_index`:

```sql
SELECT source, period_start, period_end, median_asking_price_usd_month,
       median_asking_price_usd_per_sqm_month, sample_count,
       per_sqm_sample_count, price_status, per_sqm_status,
       data_as_of, generated_at, price_basis, interpretation
FROM weekly_neighborhood_asking_price_index
WHERE source = 'list.am' AND district_id = 'kentron'
ORDER BY period_start DESC
LIMIT 12;
```

The view is stable for backend consumers. Its `price_basis` is always `asking`, and its
interpretation explicitly says these are advertised prices rather than signed-contract or
transaction prices.
