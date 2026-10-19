# C01 integration semantics — proposal v0.2.0

Issue C01 / #17. [OpenAPI](../contracts/openapi.json) defines transport shapes;
[fixtures](../contracts/fixtures.json) are entirely synthetic. This revision incorporates the B02 ML contract and Mane's frontend requirements. Additions remain proposals for affected-owner review; A's source/data confirmation is still pending. These business endpoints are planned, not implemented by C02 health/readiness checks.

## Data

- Entity IDs are opaque UUIDs; district_id uses stable slugs coordinated by A05. ML's district is the resolved district label, not a second identity. `(source, external_id)` uniquely identifies an advertisement. Listings, physical properties and immutable observations remain separate. dedup_group_id is an opaque string (compatible with B02 hashes), nullable until grouping; never merge properties using area/location alone without A04 validation. Model training requires a non-null group ID. Public area_sqm, renovation and building_type adopt B02 vocabulary; unsupported source values remain null. Training price_usd maps from price_monthly_normalized; listing_date maps from published_at where known. A/B must agree how unknown publication dates are handled before exporting training data.
- Prices are monthly asking rent, area is m², distances are meters, coordinates are WGS84 degrees. Timestamps are UTC ISO 8601 ending in Z; dates are ISO dates. Required nullable response keys are present. Unknown values are null, never zero or empty text.
- Original amount is monthly; unsupported periods or unparseable amounts are quarantined upstream. Normalize as original amount × rate_to_usd using decimal arithmetic, rounded half up to two places. Preserve rate date/provider. USD uses identity rate 1/source identity on the observation date. Missing usable conversion yields null conversion and normalized price; do not substitute today's rate into historical observations. Supported currency enum requires A01 confirmation.
- Utilities are true/false/null; never impute costs. Unknown area excludes a record only from per-m² statistics. Coordinate pairs are both present or both null; unknown coordinates require confidence unknown. Floor cannot exceed total floors.
- A02 stores source observations, conversion and ingestion provenance separately from current listing DTOs. Failed collection never deactivates inventory. A04 defines staleness and deduplication policy.

## Queries and errors

- Collection endpoints use page (default 1), page_size (20, max 100), items, filtered total and has_more = page * page_size < total. Out-of-range/empty pages return 200 with empty items. Listing sort is newest (default), price_asc/desc or area_asc/desc. Newest uses published_at with first_seen_at fallback, descending. Unknown numeric sort values are last in both directions; every order uses id ascending as a tie-breaker. Reviews default to pending, ordered updated_at descending/id ascending; filter by status, listing_id, rule_id and signal category (AND; at least one linked signal must match both signal filters). Market periods sort ascending/district_id ascending. Pagination is live, not snapshot-isolated. Frontend resets page to 1 when sorting or filters change and keeps state in the URL.
- Filters combine with AND, numeric boundaries are inclusive, rooms is exact, listing status defaults active. Unknown values cannot match numeric filters. Inactive listings remain available by ID.
- bbox is west,south,east,north with valid global bounds, west < east, south < north, no antimeridian crossing, and maximum span 0.5 degrees per axis. Only geolocated listings match; filters/pagination still apply.
- Reject unknown body/query fields, inverted ranges, malformed IDs and invalid dates with 422. Market dates filter weekly bucket starts inclusively. Weeks run Monday–Sunday in Asia/Yerevan; period dates are inclusive local dates, freshness is UTC.
- last_seen_at is source freshness; freshness.data_as_of identifies the successful source snapshot used; freshness.generated_at is response computation time. freshness also carries is_stale, max_age_days and policy_version. Provisional max ages: listing/market 14 days, valuation 60 days, exchange rate 7 days. Null snapshot implies is_stale=true; otherwise stale means generated_at - data_as_of exceeds max_age_days. Serve available stale observations with explicit metadata, not as fresh results. Valuation older than 60 days abstains per B02 while observed statistics may remain visible; service failure without a usable snapshot is 503. These thresholds need owner confirmation and later operational evaluation.
- Valid global coordinates outside the authoritative A05 Yerevan boundary yield 400/outside_coverage; malformed coordinates yield 422. Do not infer city coverage from fixture coordinates. Missing entities yield 404, dependency failure 503, insufficient evidence 200 with domain status. Every error has code/message/request_id/details; details may be empty.

## ML and statistics

Proposed in-process B07 interface: assess(input: ModelInput) returns the B02 blocks coordinates, versions, valuation_assessment, observed_market_statistics, ml_prediction_interval, feature_attributions and optional area_reference. Backend builds the public ValuationResponse by adding request_id, kind, cohort, freshness, explanation and price_status, and supplements per-m² statistics from B09. Public names preserve B02; the extra fields are explicit C01 integration additions, not claims that B02 already implements them. Backend supplies snapshot cutoff, resolved district label and distances; B owns preprocessing and model inference. ModelInput never contains asking_price_usd_month. Missing API values remain null; only B's internal preprocessing applies its documented training-fitted imputations. Confidence metadata requires calibrated intervals; no calibration means all interval fields null.

Coordinate requests default to radius 1000 m (100–5000) and window 30 days (7–90). Optional apartment fields are flat, using area_sqm, rooms, floor, total_floors, renovation and building_type; omitted/null fields mean unknown. No property wrapper is used. Coordinate-only or incomplete area/rooms requests return kind=area_reference and assessment_status=COORDINATE_BASELINE_ONLY with the training-fitted reference_area_sqm disclosed separately. Such a reference is never presented as the submitted apartment's size or prediction. No coordinate-only interval is returned until separately calibrated. Valid coordinates outside coverage return the API error outside_coverage; the internal B02 abstention for outside coverage is mapped to that error.

The cohort uses active inventory at data_as_of, observations within the inclusive local date window, geodesic radius and latest eligible observation per duplicate group; ungrouped listings each count once. Timestamp ties break by listing ID ascending. B09 versions exact comparability, fallback and minimum sample size, returning effective cohort metadata. No silent widening. Fixture minimum 3 is illustrative, not evaluated policy.

Each unit reports its own count/mean/sample standard deviation using n−1. Count 0 has null mean/stddev; count 1 has observed mean and null stddev. Monthly and per-m² samples can differ. Three prices 500/600/700 with areas 50 yield monthly mean 600/stddev 100 and per-m² mean 12/stddev 2. Observed dispersion is separate from a prediction interval; never derive an interval as mean ± stddev.

With fewer than 3 monthly comparables or source age above 60 days, use INSUFFICIENT_DATA_ABSTAIN, insufficient_data=true, null estimated_price_usd/price_per_sqm_usd/deviation_from_baseline_pct and null interval fields. Thresholds are provisional, as in B02. Explanation is required. Valid observed statistics can remain visible. No snapshot also abstains. Bounds must enclose the expected price, width equals upper minus lower, and confidence_level/calibration_version are present only with a supported calibrated interval. Synthetic intervals illustrate payloads, not measured accuracy.

assessment_status describes whether/how an estimate was produced; price_status describes the asking-price comparison. They are separate. price_status is insufficient_data for area references or missing asking price/interval; otherwise compare asking_price_usd_month with interval bounds, inclusive edges within_range, above upper above_range, below lower below_range. This preserves the business-rule statuses without renaming B02 assessment_status. valuation_tier is explanatory text, never parsed by the frontend as an enum. Attribution percentages describe model factors, not fraud scores.

Market indexes deduplicate the same way, returning monthly/area sample counts and medians. Sparse/empty cohorts have null medians/status insufficient_data; A07 agrees/version-controls the threshold. Asking prices never imply signed-contract prices.

## Reviews and risk

Price anomalies and risk_evidence are separate categories. High price alone never implies fraud. Existing ontology demo price-only HIGH/predatory labels conflict with business rules: B06 must revise them or map them to price_anomaly before integration.

Review endpoints require reviewer role: invalid/missing/expired bearer token gives 401; authenticated users without the role get 403. Proposed frontend session: configured OIDC Authorization Code with PKCE, bearer access token kept in memory and sent only to the API in Authorization. Issuer/client ID/audience/role mapping are deployment configuration to be finalized in C05, not invented login endpoints. Until then frontend uses synthetic authorized/401/403 fixtures; no real shared token is committed. A 401 triggers reauthentication while preserving the unsaved reason in UI memory; 403 displays lack of permission. Login integration remains an explicit C05/D07 decision gate.

Transitions: pending → in_review or resolved; in_review → resolved. Resolved records cannot reopen in v1. Updates need a nonblank reason and current version; in_review requires null decision, resolved requires decision. Server atomically compares/increments version, records authenticated actor/time/history, sets reviewed_at on resolution. Stale versions/invalid transitions return 409 without mutation. Retrying an applied request with old version cannot duplicate audit events. Signals deduplicate by listing, rule/version and evidence identity; replay cannot create another queue entry.

## Owner approval

| Owner | Required confirmation | State |
| --- | --- | --- |
| A / @alisamanukyann | A01 field mapping, USD/AMD, absent/approximate coordinates and listing identity received through PR #53; confirm preservation of original price/currency and null handling | Input received; two normalization rules pending confirmation |
| B / @Lazr22 | B02 names, examples, abstention, training-only fitting and split isolation received; public extensions and B09 interface still need confirmation | Input received; integration revision pending |
| C / @Artyomkrtchyan | Backend accepts B02 as integration basis; v0.2 additions, freshness and auth proposal require final agreement | Integration revision prepared |
| D / @manemazmand | Screen data, USD/AMD, sorting, maps, reviewer and missing/stale/error requirements received; v0.2 response needs review | Input received; revision pending |

Record agreement in the PR or this table. Contract changes require affected-owner review before implementation. Type/nullability/enum changes require coordinated migration; additive optional request fields/endpoints may be minor changes. Do not mark C01 Done before owner agreement and teammate PR review.

## USD/AMD display

GET /api/v1/exchange-rate returns base USD, quote AMD, amd_per_usd (AMD per 1 USD), source, effective_at, status and freshness. Source/provider selection is pending A/C agreement; 400 in fixtures is synthetic, never a real exchange-rate claim. No usable rate returns status=unavailable and null rate/source/time. Stale rates are labeled stale; frontend disables new AMD conversions until an acceptable rate is available and keeps USD usable.

API valuations and price filters remain USD. Frontend applies the same rate to monetary amounts, price/m² and monetary standard deviations. Counts, percentages, confidence, area and distance are unchanged. Preserve original listing currency separately. Use decimal arithmetic without intermediate rounding; display USD to 2 decimals and AMD to whole dram (half up). Convert an AMD minimum filter to USD rounding down to cents, maximum rounding up to cents; inclusive comparisons prevent boundary exclusions due solely to conversion precision. Changing display currency preserves the canonical USD filter values; only editing an amount recalculates them. The response rate is for display, not a replacement for each observation's historical conversion provenance.

## Maps, analytics and frontend states

GET /api/v1/infrastructure requires bbox and supports type=metro/university, the same geographic bounds validation and pagination as listings. Points sort id ascending. Bounded listing responses use ordinary listing pagination; total/has_more explicitly identify incomplete map results. Frontend may request subsequent pages or ask the user to zoom, never imply a complete map when has_more=true. Missing coordinates exclude markers, not catalogue entries. Infrastructure provenance/coverage comes from A05. Thumbnail is nullable and optional for collection; absence never hides a listing. Tile attribution is configured by frontend.

MarketIndexPage includes available_from/available_to (earliest/latest weekly bucket starts in the accessible dataset, independent of selected date filters), null when no dataset exists. Sparse bucket values are null, not zero. Fixtures cover empty, sparse, missing, inactive, stale, coordinate-only, paginated/truncated and error states. Loading/refreshing/saving are frontend states rather than fake API payloads. Review responses include listing summary, linked signals and audit history. 409 causes a refetch and explicit conflict UI without discarding the typed reason.

Deferred: optional condition/proximity/valuation-status filters, collection of images, and external identity-provider setup. They do not block frontend mock development. New exchange-rate provider policy, stale thresholds and infrastructure availability are proposals pending data-owner confirmation; do not mark C01 fully agreed yet.

## Source mapping from A01

PR #53 defines a parser record, not the public listing DTO. Backend/normalization owns the following adapter; the parser does not need to rename its fields:

| A01 field | Public/ML field | Handling |
| --- | --- | --- |
| external_id | external_id | Preserve source identity; source URL and collection timestamp come from the collector context. |
| title | title | Preserve as nullable text. |
| area_sqm | area_sqm | Same name; nonpositive parser defaults become null or quarantine evidence, not real zero area. |
| rooms_count | rooms | Rename; zero default becomes null, negative/nonintegral values are invalid. |
| address_raw | address | Preserve as source-provided text without claiming verified geolocation. |
| district | district_id / ModelInput.district | Resolve the district slug through the shared geographic registry; pass the resolved label to ML. Unknown/unmatched district remains null with traceable enrichment status. |
| building_type | building_type_raw / building_type | Preserve source text in building_type_raw. Map only known equivalent material categories to monolith/stone/panel. new_building and unknown yield null model building_type; do not infer construction material from newness. |
| images | thumbnail_url | First valid absolute HTTP(S) image URL or null. Image ingestion/gallery support is deferred; do not fabricate or require images. |
| price_usd / price_amd | price_monthly_normalized | Use only when original currency/amount and conversion provenance establish the calculation. Two converted amounts alone cannot establish original currency or a historical rate. |

The source currently confirms USD/AMD. The API's wider currency vocabulary describes supported normalization inputs, not evidence that A01 found other currencies. Publishing-date availability is unconfirmed: published_at remains null when unavailable. Collection assigns first_seen_at and last_seen_at; A/B must explicitly agree any observation-date fallback for training rather than pretending it is a publication date.

Current PR #53 uses zero/empty parser defaults and a fixed conversion placeholder. The adapter may convert documented missing defaults to null, but cannot reconstruct discarded original-price provenance. Records without a usable original price are quarantined until normalization can validate them. This is an A03 implementation requirement, not a requirement to finish A03 before agreeing C01. Fallback synthetic fixtures must remain marked as test/import data and cannot imply a successful source observation or deactivate inventory.

The listing-source-mapping fixture demonstrates raw building type preservation and missing coordinates; it is synthetic, not a transformed real listing or proof of collection. Source pagination, access constraints and parser correctness remain A01/A03 responsibilities and do not change public response field names.
