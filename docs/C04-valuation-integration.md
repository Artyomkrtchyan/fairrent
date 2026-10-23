# C04: baseline valuation API

MVP implementation on top of C03 and accepted B03 (`23f4244`). Issue #20.
The final B07 package and B06 ontology rules remain later integration work.

## Behavior

`POST /api/v1/valuations` accepts the existing C01 flat request and returns the
C01 `ValuationResponse`. Unknown fields/query parameters, nonfinite numbers,
invalid coordinates, fractional room counts and invalid feature ranges return
422. Every response/error carries the current request ID.

Example (after configuring authoritative coverage):

```bash
curl -X POST http://localhost:8000/api/v1/valuations \
  -H 'Content-Type: application/json' \
  -d '{"latitude":40.18,"longitude":44.51,"area_sqm":50,"rooms":2}'
```

- Select active, normalized long-term inventory from C03. Daily/weekly entries
  remain excluded by C03 publication, not reinterpreted as long-term comparables.
- Use a bounded indexed PostGIS candidate query (maximum 10,000 candidates,
  five-second statement timeout). A limit overflow returns 422 asking the user
  to reduce radius/window. Exact distance uses B03's Haversine calculation;
  the indexed PostGIS query uses a small conservative radius margin.
- Deduplicate by supplied duplicate group, latest last_seen_at first, UUID
  ascending on timestamp ties. Without a group, each listing counts once.
  Apply exact rooms when supplied; do not silently widen the cohort.
- With `VALUATION_DISTRICTS_FILE` configured (the Compose default), resolve the
  subject and candidate districts using municipal polygons. Supply canonical
  labels to ML and restrict both statistics and prediction to the subject's
  district when uniquely resolved. Shared borders/gaps remain unknown with an
  explicitly disclosed radius-only fallback. No source property is overwritten.
- Window dates use Asia/Yerevan, including the start date and observations no
  later than execution time. B03's 60-day age cap also applies to requests for
  longer windows; effective dates and this cap are disclosed in the response.
- last_seen_at is explicitly an observation date. This is a live observed-market
  baseline, not a training export or an assertion about unknown publication dates.
- Compute monthly statistics even when area is unknown; per-m2 statistics and
  prediction require usable area. Sample standard deviation is null for n < 2.
- Fewer than three usable unit-price comparables abstains with null valuation.
  Empty snapshots have null data_as_of and is_stale=true. No historical estimate
  is substituted when current data is insufficient or the model fails.
- Missing area OR rooms returns an area reference using B03's configured 60 m2,
  explicitly disclosed rather than claimed as a fitted district median.
- B03 has no calibrated interval or attribution factors: interval fields are
  null and factors empty. Therefore price_status remains insufficient_data even
  when a point estimate exists. Asking price never enters model inputs.
- rule_engine_version is `ontology-not-connected`: the demo's price-only fraud
  labels are not production B06 rules. No fraud verdict is generated.

## Persistence and freshness

Apply `backend/sql/002_valuation_estimates.sql` using the CLI below. The append-only
application path saves request, validated response, observation/computation times,
model/policy versions, candidate-snapshot SHA-256 and coverage provenance checksum
inside the same repeatable-read transaction used to read inventory. An invalid
model result is rejected before persistence. Persistence/commit failure fails the
request; it does not claim a saved success. The migration is repeatable.

Saved records are an audit trail, not a response cache. Each POST recomputes from
current inventory; changes to source data cannot silently reuse an old valuation.
No public historical-estimate endpoint is introduced. Listing details retain
`estimate: null`; attaching a subject-specific persisted estimate requires a
subject identity/exclusion contract and is not guessed from matching coordinates.

## Deployment

Docker build context is now the repository root so it can package the accepted
ML module and canonical response schema. `.dockerignore` allows only required
runtime sources; raw data, local configuration and Git files stay out.

```bash
docker build -f backend/Dockerfile -t fairrent-api .
docker compose up --build -d
# After pipeline ingestion/migrations, initialize or refresh the C03 projection:
docker compose exec api python -m sync_listings
# Initialize the estimate table and candidate geography index:
docker compose exec api python -m valuation_repository
```

The union of the 12 municipal district polygons is shipped as
`infra/valuation-coverage/coverage.geojson`; Compose mounts it read-only. See
[coverage configuration](../infra/valuation-coverage/README.md). Outside coverage
returns 400/outside_coverage. Missing/invalid configuration returns 503 rather
than inventing a municipal boundary. Non-Compose use sets
`VALUATION_COVERAGE_FILE` and `VALUATION_DISTRICTS_FILE` to the absolute city
and district GeoJSON paths respectively.

Health/readiness and listing routes remain independent of coverage configuration.
A DB without PostGIS/migrations returns a dependency error for valuations.

## Model provider seam and remaining dependencies

`ValuationService(provider=...)` accepts a versioned provider factory with the
same internal `assess` interface as BaselineGateway. C01 response validation,
calibrated-interval consistency, asking-price isolation, failure mapping and
persistence stay in the service. A synthetic provider verifies interval and
attribution mapping; it is not a real B07 model or measured accuracy claim.

B07 will need an adapter to its delivered package API, artifact/version provenance
and a fitted area-reference policy. B06 will supply authoritative rule results.
A05's district IDs are used by C04's municipal polygon snapshot for coordinate
lookup. C04 derives city coverage from the same polygons so the two checks agree.
Both artifacts have version/provenance checksums. The older HDX city polygon is
retained only for comparison. See coverage documentation for source metadata and
the municipal layer's unspecified reuse license. B06/B07 integration remains open.
Affected owners should review the disclosed MVP configured reference-area policy.

## Validation

Run on a disposable PostgreSQL/PostGIS DB, using isolated schemas per backend test:

```bash
C03_TEST_DATABASE_URL=postgresql://... \
TEST_DATABASE_URL=postgresql+psycopg://... \
python -m pytest backend/tests data_pipeline ml/tests -q
python contracts/validate.py
```

The backend workflow runs all three suites and builds the API from repository root.

Verified locally on 2026-10-21: **238 tests passed** across backend, pipeline and
ML. C01 validation passed (32 schemas, 35 fixtures, 16 rejected inputs); pip check
passed. Final Docker build, packaged API/schema imports, repeatable C04 migration,
synthetic coverage, assessment and PostgreSQL persistence smoke checks passed.

Geography update verified on 2026-10-23: **170 tests passed, 80 skipped** across
backend, pipeline and ML in the available WSL environment. Skips include the
PostgreSQL/PostGIS suites because no test database was configured; the new native
district/coverage checks and valuation persistence regressions still require CI.
Independent Shapely checks confirmed all 12 district geometries are valid, city
coverage equals their union, six known locations resolve correctly, a shared
district junction is ambiguous, and Gyumri lies outside coverage. Importer output
reproduces the pinned export and preserves every district geometry coordinate.
