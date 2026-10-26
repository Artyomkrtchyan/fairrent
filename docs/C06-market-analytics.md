# C06: market analytics and source freshness

`GET /api/v1/market-index` implements the C01 market contract. It reads the A07
`weekly_neighborhood_asking_price_index` view in the same PostgreSQL database
configured for listing queries (the existing `PGHOST`, `PGPORT`, `PGDATABASE`,
`PGUSER`, `PGPASSWORD` environment variables).

## Prerequisite and setup

A07 was merged in PR #71 (`141b8c3`); its Alembic migration must be applied. Run migrations and
publish weekly aggregates through the data pipeline, as described in
`data_pipeline/docs/neighborhood-price-index.md`. The API neither creates the
source view nor recomputes its medians. No additional synchronization command is
needed after publication.

The API currently serves source `list.am`, matching the listing API. Source is
fixed server-side; other sources cannot inflate counts or create duplicate
district-week entries. Missing migrations or an unavailable database produce
503 with the standard error envelope, rather than a misleading empty response.

## Query behavior

Supported query fields are `district_id`, `period_start`, `period_end`, `page`
(default 1), and `page_size` (default 20, maximum 100). Unknown or repeated fields,
invalid ISO dates, reversed date ranges and invalid pagination return 422.

Date filters apply **inclusively to weekly bucket start dates**, not observation
timestamps or period overlap. Dates need not be Mondays. A07 defines the stored
Monday–Sunday periods in `Asia/Yerevan`; timestamp values are UTC and end in `Z`.
Results sort by `period_start ASC, district_id ASC`.

`total` counts filtered stored aggregates. Out-of-range pages return empty items
with that same total. `available_from` and `available_to` are the earliest and
latest **bucket starts** for the selected source/district, ignoring date filters
and pagination. They are null only if that source/district has no stored data.
This follows C01's written date-coverage semantics; the original illustrative
chart fixture uses a Sunday for `available_to`, which is not a bucket start.

Unpublished weeks stay absent. The API does not fill gaps, interpolate rents or
manufacture district-week records. An empty stored dataset returns 200 with
empty items, zero total and null coverage. The frontend should plot missing and
sparse periods as gaps.

## A07 to C01 field mapping

| A07 view field | API field |
| --- | --- |
| `district_id`, `period_start`, `period_end` | Same names |
| `sample_count` | `sample_count` |
| `per_sqm_sample_count` | `area_sample_count` |
| `median_asking_price_usd_month` | `median_usd_month` (USD/month) |
| `median_asking_price_usd_per_sqm_month` | `median_usd_m2` (USD/month/m²) |
| `price_status` | `status` |
| `data_as_of` | `data_as_of` and `freshness.data_as_of` |
| Asking-price basis | `measure: asking_price` |

A07 owns the minimum sample policy (currently five unique properties per
metric). The API preserves published counts, medians and nulls, rather than
using the illustrative fixture's three-property threshold. C01 has one status
field, so `status` follows the monthly metric; an available monthly metric can
coexist with a null per-m² median and a smaller `area_sample_count`.

Freshness uses the latest included source observation, not aggregate publication
time. `freshness.generated_at` is response computation time and is identical for
all items in a response. Data older than 14 days is stale; exactly 14 days is
still fresh. Missing observation time is stale. Stored stale aggregates remain
visible with their metadata. These are advertised asking rents, not completed
lease or transaction prices.

Count, coverage and page queries share a read-only repeatable-read transaction
with a five-second statement timeout. Every response retains the existing
request ID and C01 error handling.

## Verification

```bash
python -m pytest backend/tests/test_market_index.py -v
C03_TEST_DATABASE_URL=postgresql://postgres:local-test-only@localhost:5432/c06_test \
  python -m pytest backend/tests/test_market_postgres.py -v
```

The PostgreSQL tests create a random isolated schema and apply the actual A07
migration there, including its constraints and view. They check filtering,
pagination/order, coverage, missing weeks, independent sparse metrics, source
isolation, stale data and missing-view errors. A further test publishes the
A07 generator's known five-property calculation and verifies the API values.
Chart-fixture tests verify C01 response shapes, counts, nulls and asking-price
units. Real-database tests skip explicitly when the database or A07 prerequisite
is absent; the existing Backend tests CI job supplies the test database.

Verified locally on 2026-10-26 against main `376384c` plus the reviewed A07
dependency `df23e5b` in an isolated combined checkout: **247 backend/pipeline
tests passed**, including all C06 database tests. C01 validation passed (32
schemas, 35 fixtures, 16 rejected inputs). The backend image built successfully
on Python 3.10, and the container imported the app and registered the market
endpoint in OpenAPI. These are local checks, not GitHub CI results.

After PR #71 merged, the C06 branch was fast-forwarded to main `141b8c3`.
Its implementation and test files match the combined checkout verified above;
the A07 prerequisite is now present directly in the branch.

The local Compose database was then upgraded from `5b7d2e91c4a6` through A05
to `a07_neighborhood_price_index`, and the API was rebuilt and started. Both
`/ready` and `/api/v1/market-index` returned 200. With no published aggregates,
the market endpoint returned the expected empty page with null date coverage.
