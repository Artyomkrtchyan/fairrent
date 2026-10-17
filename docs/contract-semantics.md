# C01 integration semantics — proposal v0.1.0

Issue C01 / #17. [OpenAPI](../contracts/openapi.json) defines transport shapes;
[fixtures](../contracts/fixtures.json) are entirely synthetic. This proposal is not yet approved by component owners or implemented by a server.

## Data

- Entity IDs are opaque UUIDs; district IDs are stable slugs coordinated by A05. `kentron` is fixture vocabulary, not a complete registry. `(source, external_id)` uniquely identifies an advertisement. Listings, physical properties and immutable observations remain separate. Unknown duplicate/property identity is null.
- Prices are monthly asking rent, area is m², distances are meters, coordinates are WGS84 degrees. Timestamps are UTC ISO 8601 ending in Z; dates are ISO dates. Required nullable response keys are present. Unknown values are null, never zero or empty text.
- Original amount is monthly; unsupported periods or unparseable amounts are quarantined upstream. Normalize as original amount × rate_to_usd using decimal arithmetic, rounded half up to two places. Preserve rate date/provider. USD uses identity rate 1/source identity on the observation date. Missing usable conversion yields null conversion and normalized price; do not substitute today's rate into historical observations. Supported currency enum requires A01 confirmation.
- Utilities are true/false/null; never impute costs. Unknown area excludes a record only from per-m² statistics. Coordinate pairs are both present or both null; unknown coordinates require confidence unknown. Floor cannot exceed total floors.
- A02 stores source observations, conversion and ingestion provenance separately from current listing DTOs. Failed collection never deactivates inventory. A04 defines staleness and deduplication policy.

## Queries and errors

- Collection endpoints use page (default 1), page_size (20, max 100), items and filtered total. Out-of-range/empty pages return 200 with empty items. Stable order: listings last_seen_at descending/id ascending, reviews updated_at descending/id ascending, market periods ascending/district_id ascending. Pagination is live, not snapshot-isolated.
- Filters combine with AND, numeric boundaries are inclusive, rooms is exact, listing status defaults active. Unknown values cannot match numeric filters. Inactive listings remain available by ID.
- bbox is west,south,east,north with valid global bounds, west < east, south < north, no antimeridian crossing, and maximum span 0.5 degrees per axis. Only geolocated listings match; filters/pagination still apply.
- Reject unknown body/query fields, inverted ranges, malformed IDs and invalid dates with 422. Market dates filter weekly bucket starts inclusively. Weeks run Monday–Sunday in Asia/Yerevan; period dates are inclusive local dates, freshness is UTC.
- last_seen_at is source freshness, data_as_of is the successful snapshot actually used, created_at is computation time. C04/C06 must agree a freshness threshold; stale results cannot masquerade as current. Until a policy is approved, expired cached results produce 503.
- Valid global coordinates outside the authoritative A05 Yerevan boundary yield 400/outside_coverage; malformed coordinates yield 422. Do not infer city coverage from fixture coordinates. Missing entities yield 404, dependency failure 503, insufficient evidence 200 with domain status. Every error has code/message/request_id/details; details may be empty.

## ML and statistics

Proposed in-process B07 interface: `assess(input: ModelInput) -> ValuationResponse` using JSON-compatible objects. Backend supplies snapshot cutoff, resolved district, and distances; B owns preprocessing, feature schema, cohort selection and inference. Missing distances are null. Asking price is a comparison target and must never be a model feature.

Coordinate requests default to radius 1000 m (100–5000) and window 30 days (7–90). If property is supplied, all its keys are present, unknown values null. Coordinate-only requests return area_reference. Property valuation needs at least area and rooms plus sufficient comparables; B02 may require additional features.

The cohort uses active inventory at data_as_of, observations within the inclusive local date window, geodesic radius and latest eligible observation per duplicate group; ungrouped listings each count once. Timestamp ties break by listing ID ascending. B09 versions exact comparability, fallback and minimum sample size, returning effective cohort metadata. No silent widening. Fixture minimum 3 is illustrative, not evaluated policy.

Each unit reports its own count/mean/sample standard deviation using n−1. Count 0 has null mean/stddev; count 1 has observed mean and null stddev. Monthly and per-m² samples can differ. Three prices 500/600/700 with areas 50 yield monthly mean 600/stddev 100 and per-m² mean 12/stddev 2. Observed dispersion is separate from a prediction interval; never derive an interval as mean ± stddev.

Insufficient evidence returns null prices/bounds and an explanation. Area references provide local statistics but no apartment prediction. Bounds are both null or both present, ordered around the expected price. If interval or asking price is unavailable, price_status is insufficient_data (expected price may still be available). Interval edges are within_range; values above/below yield above_range/below_range. Fixture intervals are synthetic; B05 calibrates real intervals.

Market indexes deduplicate the same way, returning monthly/area sample counts and medians. Sparse/empty cohorts have null medians/status insufficient_data; A07 agrees/version-controls the threshold. Asking prices never imply signed-contract prices.

## Reviews and risk

Price anomalies and risk_evidence are separate categories. High price alone never implies fraud. Existing ontology demo price-only HIGH/predatory labels conflict with business rules: B06 must revise them or map them to price_anomaly before integration.

Review endpoints require reviewer role: invalid/missing bearer token gives 401; authenticated users without the role get 403. C05 chooses issuer/session details. No login endpoint or credentials are implied.

Transitions: pending → in_review or resolved; in_review → resolved. Resolved records cannot reopen in v1. Updates need a nonblank reason and current version; in_review requires null decision, resolved requires decision. Server atomically compares/increments version, records authenticated actor/time/history, sets reviewed_at on resolution. Stale versions/invalid transitions return 409 without mutation. Retrying an applied request with old version cannot duplicate audit events. Signals deduplicate by listing, rule/version and evidence identity; replay cannot create another queue entry.

## Owner approval

| Owner | Required confirmation | State |
| --- | --- | --- |
| A / @alisamanukyann | Source fields/currencies, nullability, conversions, IDs, geography, observations | Pending |
| B / @Lazr22 | Features, cohort/thresholds, inference interface, status semantics, ontology mapping | Pending |
| C / @Artyomkrtchyan | API/errors/auth, review transitions and freshness policy | Pending |
| D / @manemazmand | Filters, pagination, fixtures and empty/sparse/error states | Pending |

Record agreement in the PR or this table. Contract changes require affected-owner review before implementation. Type/nullability/enum changes require coordinated migration; additive optional request fields/endpoints may be minor changes. Do not mark C01 Done before owner agreement and teammate PR review.
