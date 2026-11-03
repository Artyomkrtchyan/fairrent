# C04: versioned valuation and ontology API

Implements issue #20 on top of C03, accepted B03, B06 and B07. The API uses the
B03 baseline when no package is configured, and B07 when `FAIRRENT_MODEL_PACKAGE`
points to a versioned package. A configured package failure abstains; it never
silently switches to the baseline.

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
- Use accepted A05 code for the full district vocabulary and current versioned
  straight-line distances to metro, university and center. Canonical district
  labels and nullable distance fields reach the model for subject and comparables.
  B03 currently ignores proximity distances; they are supplied for the B07 adapter,
  not presented as trained distance effects. Recomputing with the same A05 version
  avoids mixing stale stored features. The A05 geography version is saved with
  each estimate's geography provenance.
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
- B06 supplies versioned rule facts and a readable explanation, with structured
  evidence retained in the audit record. Rule facts and learned price effects
  remain separate. No fraud verdict is generated.
- B07 returns calibrated intervals and SHAP factors for supported complete-property
  predictions, a training-fitted reference area for incomplete features, and null
  estimates/intervals for sparse evidence, serving-gate failures or model/package
  errors. The actual source observation cutoff reaches B07 for freshness checks.
- `deviation_from_baseline_pct` compares the estimate with the observed cohort
  mean. The supplied asking price affects only `price_status`.

## Persistence and freshness

Apply `backend/sql/002_valuation_estimates.sql` using the CLI below. The append-only
application path saves request, validated response, observation/computation times,
model/policy versions, candidate-snapshot SHA-256 and coverage provenance checksum
and `inference_provenance` (package/calibration/training snapshot versions, B06
structured evidence and fallback reasons) inside the same repeatable-read transaction used to read inventory. An invalid
model result is rejected before persistence. Persistence/commit failure fails the
request; it does not claim a saved success. The migration is repeatable.

Saved records are an audit trail, not a response cache. Each POST recomputes from
current inventory; changes to source data cannot silently reuse an old valuation.
No public historical-estimate endpoint is introduced. Listing details retain
`estimate: null`; attaching a subject-specific persisted estimate requires a
subject identity/exclusion contract and is not guessed from matching coordinates.

## Deployment

Docker build context is now the repository root so it can package the accepted
ML module and canonical response schema. `backend/Dockerfile.dockerignore` allows only required
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

## B07 deployment and provider interface

Build a package using `ml.package_inference` as documented in
[B07](B07-inference-package.md). Place it in `artifacts/b07/<version>/` on the
host, set `FAIRRENT_MODEL_PACKAGE=/models/<version>` in `.env`, and recreate the
API container. Compose mounts `artifacts/b07` read-only at `/models`.
Omit the setting to explicitly use the B03 MVP baseline. Package binaries are
not committed. The package evidence level and training limitations remain in
the audit record; synthetic test packages are verification evidence only.

Run `python -m valuation_repository` again to add the `inference_provenance`
column to an existing audit table. The migration preserves existing records.

`ValuationService(provider=...)` retains its injectable provider interface.
The default factory selects `PackagedGateway` when a package path is configured.
The adapter passes only the selected deduplicated cohort and ModelInput fields
to `ml.inference.assess`; asking price never reaches inference. Observed dataset
provenance and training snapshot provenance are stored separately. Each POST
recomputes current comparables and persists the validated public response.

B07 also enforces its documented provisional coverage box after C04's municipal
polygon check. A location outside either supported boundary yields
`400/outside_coverage`. Coverage configuration errors and unexpected/invalid
provider results yield 503; the B07 documented model-failure path returns a
200 abstention with observed statistics and an audited fallback reason.

The backend Dockerfile includes both baseline and package runtimes and preserves
B07's `verify` target. To verify a built package in that image:

```bash
docker build -f backend/Dockerfile --target verify -t fairrent-api-verify .
docker run --rm -v "$(pwd)/artifacts/b07/<version>:/package:ro" fairrent-api-verify
```

## Validation

Run on a disposable PostgreSQL/PostGIS DB, using isolated schemas per backend test:

```bash
C03_TEST_DATABASE_URL=postgresql://... \
TEST_DATABASE_URL=postgresql+psycopg://... \
python -m pytest backend/tests data_pipeline ml/tests -q
python contracts/validate.py
```

The backend workflow runs all three suites and builds the API from repository root.

Prior baseline validation on 2026-10-24: **271 tests passed, none skipped** across backend,
pipeline and ML using a disposable PostGIS 16/3.4 container. C01 validation passed
(32 schemas, 35 fixtures, 16 rejected inputs). The root-context Docker build and
packaged API/A05 imports passed. Native PostGIS checks cover district lookup,
coverage, shared borders and persistence. The end-to-end test runs mock source
HTML through A05 ingestion, source PostgreSQL tables, API publication, real B03
valuation and the estimate audit record, checking district/proximity features,
coordinate provenance, geography versions and asking-price isolation.

Independent Shapely checks confirmed all 12 district geometries are valid, city
coverage equals their union, six known locations resolve correctly, a shared
district junction is ambiguous, and Gyumri lies outside coverage. Importer output
reproduces the pinned export and preserves every district geometry coordinate.


Final integration verification on 2026-11-04: seven HTTP tests exercise a real
checksummed synthetic B07 package (success, calibrated interval/factors, B06
explanation, fitted area reference, missing/corrupt package, model exception,
serving-gate/sparse/stale abstention and coverage rejection). A disposable PostGIS
test also checks package/calibration/ontology provenance and migration upgrades.
The Python 3.10 backend `verify` target returned `VERIFIED`; the API image also
completed real B07 inference, municipal coverage/cohort selection and PostgreSQL
audit persistence. These checks verify integration, not production model quality.
