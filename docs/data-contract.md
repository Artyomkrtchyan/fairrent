# Initial data contract — draft v0

This is a proposal for team agreement, not an implemented API.

## Listing

`id`, `source`, `external_id`, `source_url`, `property_id` (optional), `description`, `price_original`, `currency_original`, `price_monthly_normalized`, `currency_normalized`, `utilities_included` (true/false/unknown), `area_m2`, `rooms`, `floor`, `total_floors`, `condition`, `address`, `district_id`, `latitude`, `longitude`, `published_at`, `first_seen_at`, `last_seen_at`, `status`.

Area is measured in square meters, distances in meters, and timestamps in ISO 8601 UTC. Represent unknown numeric values as null, not zero. Currency normalization preserves the exchange-rate date and source. The source + external_id pair identifies a source listing; store observations separately. Finalize required fields after analyzing source data.

## Estimate

`listing_id`, `expected_price`, `lower_bound`, `upper_bound`, `currency`, `price_status`, `comparable_count`, `confidence_explanation`, `factors`, `model_version`, `rules_version`, `data_as_of`, `created_at`.

For `insufficient_data`, price and bounds may be null; an explanation is required. Return risk signals separately from price status.

## RiskSignal and Review

RiskSignal: `id`, `listing_id`, `rule_id`, `rules_version`, `evidence`, `created_at`.

Review: `id`, `listing_id`, `signal_ids`, `status` (pending/in_review/resolved), `decision` (nullable), `reason`, `reviewed_at` (nullable). Reprocessing the same signal must not duplicate queue entries.

## Proposed API endpoints

- `GET /api/v1/listings` — filtering and pagination.
- `GET /api/v1/listings/{id}` — listing details.
- `GET /api/v1/listings/{id}/estimate` — valuation and explanation.
- `GET /api/v1/market-index` — neighborhood, period, observation count.
- `GET /api/v1/reviews` — reviewer queue.
- `PATCH /api/v1/reviews/{id}` — reviewer decision.

Agree on access permissions, error formats, pagination, synthetic responses, and OpenAPI before implementation.
