# Map district asking-rent layer

Issue: #114. The map uses **actual published** weekly median asking rent in USD/m²/month, via the existing `GET /api/v1/market-index` contract. This is a **district choropleth**, not a continuous street/building heatmap, not sale prices, and not a property prediction.

## Data and geographic method

- Municipal district boundaries are drawn from `infra/valuation-coverage/districts.geojson` (Yerevan Municipality public GIS, source attribution and license caveat in the original file). The frontend bundles a geometrically **simplified rendering copy**, preserving district IDs and coordinate order. It is not a survey-quality or legal boundary.
- The browser requests weekly index rows in the recent 60-day window, following pagination. To avoid mixing time periods, it displays **only the newest shared published week** across districts.
- A district is filled **only if** its latest-week `median_usd_m2` is finite and positive and `area_sample_count >= 5`. Null, unsupported or missing districts are uncolored. The API's minimum source support remains authoritative; the frontend extra guard is defensive.
- Minimum and maximum in the legend are computed from the actual supported values for that week. Stale data triggers an explicit warning. Tooltip text gives district, median, sample count and stale state.
- If no recent published index exists, the layer clearly says so instead of generating a synthetic heatmap. The mock/demo price surface remains separately labeled as synthetic.

## UI and coexistence

The "District rent prices" checkbox toggles the polygon layer. Rental markers, cluster behavior, map viewport, 2D/3D switching, metro and university controls remain separate and functional. The same layer appears on the embedded and expanded maps.

## Verification

- Run frontend `npm run typecheck`, `npm test`, `npm run build`, and existing Chromium Playwright browser smoke.
- Verify both map sizes, panning and toggling, clicking a colored district for its statistics, rental markers, metro and university markers, and 2D/3D behavior.
- Confirm actual production market-index values, week and freshness, that missing districts are uncolored, and that real data isn't confused with the demo.
- Review municipal geometry source/attribution before any separate public data redistribution.

**Before final release sign-off:** Save a redacted live-browser screenshot with timestamp and deployed SHA. Automated fixture-backed tests do not establish the current production data coverage.
