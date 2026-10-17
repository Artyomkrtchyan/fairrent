# Shared data contract — C01 proposal v0.2.0

The shared contract incorporates B02 ML naming and frontend requirements. Final data-owner confirmation and review of the new integration fields remain pending.

## Contract sources

- [OpenAPI schemas](../contracts/openapi.json): exact requests, responses, required/nullable fields, enums, filters, pagination and errors.
- [Integration semantics](contract-semantics.md): units, original/historical currency conversion, USD/AMD display, ML/public mapping, freshness, statistics and reviews.
- [Synthetic examples](../contracts/fixtures.json): normal, empty, sparse, stale, inactive, coordinate-only, missing-field, exchange-rate and error cases. Each entry wraps a schema name and a value; frontend mocks return value.
- [Generation and verification](../contracts/README.md): reproduce and validate the artifacts.
- [ML contract](https://github.com/Artyomkrtchyan/fairrent/blob/main/ml/CONTRACT.md): training features, internal imputation, split isolation and evaluation methodology. Additional public fields are documented in integration semantics.

## Planned endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | /api/v1/listings | Filtered, sorted and paginated catalogue/map results |
| GET | /api/v1/listings/{id} | Details, signals and nullable valuation |
| GET | /api/v1/listings/{id}/estimate | Current listing valuation with source freshness |
| POST | /api/v1/valuations | Coordinate/property valuation and observed price dispersion |
| GET | /api/v1/market-index | Weekly neighborhood asking-price statistics |
| GET | /api/v1/infrastructure | Paginated metro/university points within map bounds |
| GET | /api/v1/exchange-rate | USD→AMD display rate and provenance |
| GET | /api/v1/reviews | Protected reviewer queue |
| PATCH | /api/v1/reviews/{id} | Protected, version-checked decision and saved review |

These are planned business endpoints. C02's implemented health/readiness endpoints do not imply that these routes are operational.

## Shared conventions

Report monthly asking rent in USD, area_sqm in square meters, distances in meters and UTC timestamps in ISO 8601 with Z. Preserve original source amounts and conversion provenance. Unknown fields are null rather than invented zeros. Listings, physical properties and observations have separate identity; dedup_group_id supports duplicate-group isolation.

Valuation responses preserve B02 blocks: coordinates, versions, valuation_assessment, observed_market_statistics, ml_prediction_interval and feature_attributions. Public metadata adds cohort selection, freshness, explanation, kind and price_status. Area references disclose any training-fitted reference area; they are not apartment-specific predictions. Observed sample standard deviation uses n−1 and remains separate from calibrated intervals. Price anomalies and risk evidence remain separate.

## Remaining decisions

A must confirm source fields/currencies, district vocabulary/geography, duplicate identity, observation dates and rate provenance. A/C must select the USD/AMD provider. Freshness defaults, public B09 additions and identity-provider integration are documented proposals requiring the corresponding owners' confirmation. Optional images and advanced filters can follow later. Record actual approval in the integration semantics checklist rather than treating submitted requirements as approval of this revision.
