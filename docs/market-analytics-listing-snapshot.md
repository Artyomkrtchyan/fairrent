# Market analytics — current listings snapshot and published weekly history

**Issue:** #120. The existing A07/C06 weekly aggregation pipeline and `GET /api/v1/market-index` remain implemented and tested. That engineering completion **does not imply** that historical weekly aggregates have been populated in the live database.

## Default: Current listings snapshot

The Market analytics page defaults to **Current listings snapshot**, calculated from actual `GET /api/v1/listings` responses (`status=active`, up to 100 per page). The browser automatically pages through results up to 30 pages (3,000 listing rows), and states when coverage is partial, capped, or affected by an API error.

Displayed information:
- Number of unique active rental listings with available data, selected neighborhood and optional exclusion of API-marked stale records.
- Median *asking* rent per month in the selected display currency, computed from valid positive normalized USD rents.
- Median asking rent per m²/month, computed from the **individual** listings that have both positive normalized asking rent and positive floor area (median of individual rent/area ratios, not median rent divided by median floor area).
- Neighborhood comparison as a bar chart or accessible table, with actual supporting observation counts, unknown/missing metric state, and latest listing observation date.
- Same available API deduplication group/property identifiers are used to avoid counting repeated records in the downloaded pages. Duplicates without common identifiers cannot be inferred.

The figures reflect only the downloaded active-listing sample: **not historical price trends, observed lease prices, a citywide representative study, or a claim that all city rentals are included**. Missing or invalid rent/area is excluded from the corresponding metric rather than changed to zero. Neighborhood comparisons exclude records without a known district; the all-listings summary may include them.

## Optional: Published weekly history

The **Published weekly history** tab still uses the original `GET /api/v1/market-index`, weekly filters, timeline/table, observation counts, and freshness. A database with no published weekly aggregates returns an honest no-data message. The browser does not generate fake time-series points by grouping one current listing snapshot into pretend weeks.

## Report language

Accurate summary for a project report:

> The team implemented and tested the weekly neighborhood asking-price aggregation pipeline, API, and frontend historical view. Since a populated multiweek dataset is not yet available in the deployed environment, the production Market analytics page defaults to a cross-sectional snapshot derived from currently available active rental listings. This supports real neighborhood price comparisons without presenting synthetic history as observed data.

## Acceptance

- [ ] Confirm actual snapshot API pagination, counts, filters and comparison table on the deployed website.
- [ ] Check missing currency/area, unknown district, stale-source and empty-data behavior.
- [ ] Verify partial-coverage warning if more than 3,000 listings exist or a subsequent API page fails.
- [ ] Verify the existing weekly tab still accurately shows an empty dataset when no historical aggregates are published.
- [ ] Validate mobile chart/table, display currency, test suite and CI before release sign-off.
