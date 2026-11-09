# Map district asking-rent layer

Issue: #114. The map uses **actual published** weekly median asking rent in USD/m²/month, via the existing `GET /api/v1/market-index` contract. This is a **district choropleth**, not a continuous street/building heatmap, not sale prices, and not a property prediction.

## Data and geographic method

- Municipal district boundaries are drawn from `infra/valuation-coverage/districts.geojson` (Yerevan Municipality public GIS, source attribution and license caveat in the original file). The frontend bundles a geometrically **simplified rendering copy**, preserving district IDs and coordinate order. It is not a survey-quality or legal boundary.
- The browser requests weekly index rows in the past 180 days, following pagination. It displays **the newest week with at least one supported per-m² median**, without mixing different weeks. If newer published weeks are undersampled, the legend explicitly identifies the older observation week; old observations are marked historical.
- A district is filled **only if** its latest-week `median_usd_m2` is finite and positive and `area_sample_count >= 5`. Null, unsupported or missing districts are uncolored. The API's minimum source support remains authoritative; the frontend extra guard is defensive.
- Minimum and maximum in the legend are computed from the actual supported values for that week. Stale data triggers an explicit warning. Tooltip text gives district, median, sample count and stale state.
- If no supported week exists within 180 days, the guide still explains the agreed green/yellow/red palette but says that there are **no supported district values**, leaving the map uncolored instead of generating a synthetic heatmap. The legend remains readable and its API Retry control is clickable. The mock/demo price surface remains separately labeled as synthetic.

## UI and coexistence

The "District rent prices" checkbox toggles the polygon layer. Rental markers, cluster behavior, map viewport, 2D/3D switching, metro and university controls remain separate and functional. The same layer appears on the embedded and expanded maps.

## Verification

- Run frontend `npm run typecheck`, `npm test`, `npm run build`, and existing Chromium Playwright browser smoke.
- Verify both map sizes, panning and toggling, clicking a colored district for its statistics, rental markers, metro and university markers, and 2D/3D behavior.
- Confirm actual production market-index values, week and freshness, that missing districts are uncolored, and that real data isn't confused with the demo.
- Review municipal geometry source/attribution before any separate public data redistribution.

**Before final release sign-off:** Save a redacted live-browser screenshot with timestamp and deployed SHA. Automated fixture-backed tests do not establish the current production data coverage.

## Runtime fallback for deployments without a populated weekly index

When the C06 weekly index has no supported observations (or the weekly API cannot be reached), the frontend can show a **clearly labeled current-active-listing snapshot**. It queries up to 1,500 active listings through the existing listings API, groups unique known properties by district, computes the median of each listing's observed USD monthly asking rent divided by its positive floor area, and fills only districts with at least five suitable listings. The legend identifies the data source, number of loaded rows, observation date and any partial pagination. This is a cross-sectional sample, **not weekly price growth or an inferred historical trend**. No unsupported district is colored.

When weekly medians are present, they remain preferred. When neither source is adequate, the palette guide remains visible but the map stays uncolored. Do not treat missing data as zero.

## Expanded-map performance

Only the embedded map or the modal map is mounted at a time, avoiding duplicate active WebGL renderers, marker trees and ResizeObservers. Expanding preserves the user's camera state and existing controls; closing restores the embedded map. Verify both transitions in production before closing issue #114.
