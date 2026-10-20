# C03 listing APIs — implementation in progress

Implemented against the existing C01 proposal; owner agreement is still pending.
No C01 response shapes or A02 source tables are changed. A03/A04 pipeline
integration remains a follow-up after Alice's PR fixes and provenance agreement.

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

## Temporary integration boundary

The existing A02 schema lacks mandatory C01 provenance and lifecycle fields.
Serving it directly would require inventing status, first/last observation times,
original currency or historical rates. C03 therefore reads a backend-owned
`api_listing_projection`, provisioned explicitly by
`backend/sql/001_listing_projection.sql`. It contains only explicitly published,
validated canonical listing records, plus indexed search columns. It is an API
read model, not a second source of ingestion history.

The table starts empty. Current A02 rows and pipeline mock records are **not**
automatically imported. Applying this migration does not modify Alice's tables.
An unavailable/unprovisioned projection returns 503; an initialized empty table
returns an ordinary empty page.

After A03/A04 is fixed, implement the source adapter at `publish_listing` in
`backend/listing_repository.py`. It accepts `ListingData` or an equivalent dict,
validates required source metadata and updates one record atomically. The caller
owns commit/rollback, allowing source and projection changes in one transaction.
Public UUIDs must be stable across re-ingestion and the later schema adaptation;
source/external_id pairs are unique. A02 integer IDs are not exposed as UUIDs.
No HTTP endpoint permits publishing records.

Unknown nullable fields stay null. A usable original monthly amount, currency,
source URL, UTC first/last observation times and explicit status are required
before publishing. Missing historical conversion yields null conversion and
normalized price. USD conversion also needs explicit observation-date identity
provenance. Fixed-rate A01 prices alone cannot establish these fields.

Freshness is computed at response time from last_seen_at using C01's provisional
14-day policy. API price_status is insufficient_data until valuation integration;
no ML or fraud conclusions are fabricated.

## Provisioning

With the C02 Compose database running, apply from a shell that supports input
redirection (for example WSL):

```bash
docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < backend/sql/001_listing_projection.sql
docker compose up --build -d api
```

The SQL is repeatable for this initial schema; it is not an automatic migration
runner. Future schema changes need versioned migrations. `/ready` retains its
C02 meaning (database connectivity), not ingestion readiness.

Example queries after provisioning:

```text
/api/v1/listings?district_id=kentron&price_min=500&price_max=900&rooms=2
/api/v1/listings?bbox=44.50,40.17,44.55,40.22&page_size=100
/api/v1/listings?status=inactive&sort=price_desc&page=2
```

## Verification and remaining acceptance work

```bash
python -m pip install -r backend/requirements-dev.txt
python -m pytest backend/tests -v
# Optional locally; mandatory in backend CI. Use a disposable test database.
export C03_TEST_DATABASE_URL=postgresql://postgres:c03-test-only@127.0.0.1:55433/c03_test
python -m pytest backend/tests -v
```

Database tests create/drop only their own randomly named schemas. They use
synthetic C01 fixtures and verify actual SQL filters, sort ties/nulls, pagination,
bounding-box edges, inactive details, empty results and transactional updates.
Actual responses are validated against the committed C01 JSON schemas. Without
the test DSN, PostgreSQL tests are explicitly skipped; ordinary API tests run.

Before marking C03 done:

- Agree source URL, stable UUID ownership, district slugs, observation times,
  lifecycle status and conversion provenance with Alice.
- Implement and verify the real A03/A04 publishing adapter and backfill policy.
- Run the full collection → normalization → database → API flow, including
  inactive and missing-data records, after her changes land.
- Obtain teammate review and final contract agreement. Do not count synthetic
  database tests as proof of real source ingestion.
