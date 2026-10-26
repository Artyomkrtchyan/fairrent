# C03 listing APIs — integrated implementation

Implemented against the existing C01 proposal and the accepted A02/A03/A04 schema
merged in PR #57 (`628f5cb`). No C01 response shapes or source tables are changed.
Implementation and integration tests are ready for teammate review.

## Implemented routes

- `GET /api/v1/listings`: district, inclusive monthly USD price and area ranges,
  exact rooms, active/inactive status (default active), page/page_size and sorting.
- `GET /api/v1/listings/{id}`: UUID lookup, including inactive records; 404 for a
  missing record. Signals are empty and estimate is null until C04 integration.
- Map queries use the collection route with `bbox=west,south,east,north`. Global
  bounds, strictly increasing edges and a maximum 0.5-degree span per axis are
  enforced. Missing coordinates exclude markers, not catalogue records.

Sorting follows C01: null numeric values last in both directions, UUID ascending
as the tie-breaker; newest uses published_at with first_seen_at fallback. Count
and page run in a single repeatable-read snapshot. Empty/out-of-range pages return
200 and retain the filtered total. Map results retain total/has_more.

Unknown/repeated query parameters, malformed UUIDs, inverted ranges and invalid
bounds return 422. Database failure or an unapplied projection returns 503.
Errors use the C01 envelope and a generated request UUID, also in X-Request-ID.
Queries use bound parameters, fixed SQL sort expressions and a five-second
statement timeout. Business endpoints use the same PG* configuration as C02.

## Source integration and publication

`backend/source_adapter.py` maps Alice's accepted storage schema into C01.
`backend/sync_listings.py` publishes a consistent snapshot to the indexed
`api_listing_projection` read model. Source ingestion and history stay owned by
the pipeline. The API has no write endpoint and does not run ingestion itself.

Run publication after ingestion completes. The command creates the projection if
needed, validates eligible `source='list.am'` records, upserts active AND inactive
listings, and removes records that no longer qualify from the API projection only.
It returns counts and safe exclusion reason codes; it never prints raw records or
database credentials. Demo/fixture/synthetic sources are excluded. Legacy rows
without a source run or original-price evidence are excluded until re-observed.

Publication is atomic: repeatable-read source snapshot, a session advisory lock
serializing publishers, and one transaction for all projection updates/removals.
Readers see either the previous publication or the complete next one. Any failure
preserves the previous snapshot. A running list.am ingestion run blocks
publication; finish or resolve interrupted runs first. The command does not infer
inactivity: it copies Alice's explicit `is_active` state.

### Mapping decisions

- Public listing UUID = UUIDv5 of `(source, external_id)` in a fixed namespace;
  repeat publication or source schema changes cannot change it. Property UUIDs
  are separately namespaced from the storage property ID. Integer IDs are not
  exposed as public UUIDs. Dedup group remains null until its public policy is agreed.
- The public long-term catalogue accepts only `month`/`monthly` and
  `year`/`yearly`/`annual` quotations. Daily and weekly quotations are excluded
  with `short_term_rental`: monthly-equivalent arithmetic is not evidence of
  long-term availability. No source evidence field currently authorizes an
  exception. Unknown periods remain excluded as `unsupported_period`.
- `price_original` is the monthly equivalent of an eligible quote (year /12).
  Original quotation and period remain in source storage. Conversion uses
  Decimal arithmetic and half-up cents, not stored rounded floats.
- Re-running publication removes newly ineligible records from the public
  projection, including search, bounded map queries and details. Source records
  and pipeline short-term normalization remain unchanged. Deployments must run
  `sync_listings` after updating the adapter to remove previously published
  short-term records.
- Source `exchange_rate` means original currency per USD; C01 `rate_to_usd` is
  its reciprocal. Preserve `rate_source` and effective `rate_date`, separately
  from conversion time. USD uses identity rate 1 on the source observation date.
  Missing/future-dated historical rate evidence gives null conversion AND null
  normalized rent; no current-rate substitution. Static configured rates stay
  labeled `static-config`; this does not certify an official/live provider.
- `url` -> source_url; first/last seen -> UTC timestamps; published_at remains null
  because the source has not supplied a publication date. Unknown values stay null.
- Geolocation comes from Property.geom. A05's persisted exact/approximate/unknown
  confidence is preserved; missing coordinates always have unknown confidence.
  Missing coordinates preserve catalogue/detail records but exclude markers.
- District labels use the full A05 registry (12 stable slugs and Armenian/English
  aliases). Current explicit raw district fields take precedence; without one,
  use the validated persisted A05 district_id or normalize the property label.
  Unknown explicit labels remain null. Address enrichment keeps its prior policy.
- Rooms/floor/area are validated; unsupported building materials remain null while
  building_type_raw is preserved. Thumbnails and renovation remain null until
  their collection is integrated. Missing source URL excludes the record.

Freshness is computed at response time from last_seen_at using C01's provisional
14-day policy. API price_status is insufficient_data until valuation integration;
no ML or fraud conclusions are fabricated.

## Provisioning

Apply Alice's migrations through A05 (`a05_geo_20261022`) first, then finish
an A03 crawl/import using the pipeline's DATABASE_URL configuration. With the C02
Compose database running:

```bash
docker compose up --build -d api
docker compose exec api python -m sync_listings
```

From a Python environment instead: set the same PGHOST/PGPORT/PGDATABASE/PGUSER/
PGPASSWORD as C02 and run `python -m backend.sync_listings`. Pipeline DATABASE_URL
and backend PG* settings must refer to the same database. Re-run publication
after each completed ingestion; scheduling is C09. No live source is contacted by
the publisher. A fixture import with its default `fixture` source does not become
live inventory. Before initial publication, listing endpoints return 503.

The initial projection SQL is repeatable, not an automatic source migration runner.
`/ready` retains its C02 meaning (database connectivity), not ingestion readiness.

For the D02 frontend, use VITE_API_MODE=real and VITE_API_BASE_URL pointing at
the API. CORS permits localhost:5173 and 127.0.0.1:5173 GET requests by default.
Set FRONTEND_ORIGINS to an explicit comma-separated allowlist for other origins;
it is passed through Compose. No credentialed cross-origin requests are enabled.

Example queries after provisioning:

```text
/api/v1/listings?district_id=kentron&price_min=500&price_max=900&rooms=2
/api/v1/listings?bbox=44.50,40.17,44.55,40.22&page_size=100
/api/v1/listings?status=inactive&sort=price_desc&page=2
```

## Verification and remaining acceptance work

```bash
python -m pip install -r backend/requirements-dev.txt
python -m pytest backend/tests data_pipeline -v
# Optional locally; mandatory in backend CI. Use a disposable test database.
export C03_TEST_DATABASE_URL=postgresql://postgres:c03-test-only@127.0.0.1:55433/c03_test
export TEST_DATABASE_URL=postgresql+psycopg://postgres:c03-test-only@127.0.0.1:55433/c03_test
python -m pytest backend/tests data_pipeline -v
```

Backend database tests create/drop only their own randomly named schemas. Alice's
pipeline tests rebuild their source tables, so TEST_DATABASE_URL must point to a
disposable database, never development/production inventory. CI uses a dedicated
PostgreSQL 16/PostGIS service. Actual API payloads are checked against C01 JSON
schemas. Without test DSNs, database tests are explicitly skipped.

Integration tests use HTTP MockTransport against project-owned fairrent.test
pages and run collection -> validation/normalization -> source PostGIS tables ->
atomic publication -> HTTP API. They exercise monthly AMD prices, source URLs,
missing coordinates, filters/map bounds, stable UUIDs, changed prices, inactive
details, repeat publication, legacy/demo exclusions and rollback on failure.

Remaining external work: teammate PR review, an agreed
production exchange-rate provider and C09 scheduling. These do not add fake data
or block testing the C03 storage/API integration. Live list.am selector/access
verification remains A03's documented operational work; tests do not claim a live
collection succeeded. Signals/valuation integration stays in C04.
