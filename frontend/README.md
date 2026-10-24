# FairRent frontend

React, TypeScript and Vite frontend for long-term apartment rentals in
Yerevan. Uses TanStack Router, TanStack Query and Tailwind CSS.

## Requirements

- Node.js 24 LTS
- npm
- Run commands inside `frontend/`.
- Keep the repository's `contracts/` directory alongside `frontend/`.

## Install and run

```bash
npm ci
```

```bash
npm run dev
```

Open the local address printed by Vite.

## API modes

Mock mode is the default. It uses synthetic examples from
`../contracts/fixtures.json`; these are not real listings or model results.

Explicit mock mode:

```bash
VITE_API_MODE=mock npm run dev
```

Real mode:

```bash
VITE_API_MODE=real VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

Real mode requires accessible backend business endpoints. A different API
origin must allow the frontend through CORS. Failed requests show errors;
they do not silently fall back to mock data.

Optional local settings can be placed in `.env.local`, using `.env.example`
as a reference. Restart the development server after changing settings.
All VITE_* variables are browser-visible: never put credentials in them.

Mock transport supports catalogue filtering, sorting and pagination using
the shared synthetic fixture. It does not implement authentication or
database writes.

## Currency and theme

The interface supports light, dark and system themes.

USD is the canonical price currency. AMD display conversion uses the
shared exchange-rate response. Mock rates are explicitly synthetic.
AMD conversion is unavailable when the rate fails the freshness or
availability checks.

Display rounding: USD to two decimals, AMD to whole dram, half up.
Currency selection does not change the underlying USD amounts.

## Checks

```bash
npm run typecheck
```

```bash
npm test
```

```bash
npm run lint
```

```bash
npm run build
```

Lint currently reports eight Fast Refresh warnings about mixed
component/helper exports. There are no lint errors at the last check.

## API types

Regenerate types after agreed OpenAPI changes:

```bash
npm run generate:api
```

Types are generated from `../contracts/openapi.json` into
`src/api/schema.d.ts`. Do not edit the generated file manually.

## Production build

```bash
npm run build
```

Static output is written to `dist/`.

```bash
npm run preview
```

Preview serves the last production build, so rebuild after code changes.

Production hosting must serve `index.html` for frontend routes such as
`/analytics`, while preserving asset and API routing. AWS deployment
configuration remains part of the infrastructure tasks.

## D02 scope

Implemented:
- Responsive shared layout, navigation and theme selection.
- Typed API client with mock and real transports.
- C01-backed catalogue and basic listing details.
- USD/AMD display conversion through the shared rate response.
- Loading, error, missing-value and not-found handling.

Later tasks:
- Interactive map and infrastructure layers: D05.
- Integrated analytics: D06.
- Reviewer authentication and mutations: D07.
- Final end-to-end verification: D08.
- Integrated coordinate assessment: D09.

Analytics, coordinate and reviewer preview screens may still use separate
synthetic demonstration data. Their presence does not mean backend
integration is complete. Demo photographs do not depict actual listings.

## D03 catalogue

The catalogue supports:
- District, exact room count, rent range and area range filters.
- Apply, Clear all and individual filter removal.
- Sorting by newest, rent and area.
- Pagination with the filtered total.
- Applied search choices stored in the URL.
- Return from listing details to the previous search and scroll position.
- Expandable mobile filters, with Clear all outside the panel.
- Loading, error, empty-result and missing-value messages.

Prices in API queries and URLs remain USD. Rent inputs follow the selected
display currency. AMD conversion uses the shared exchange-rate response;
mock rates are synthetic.

Filters are applied before pagination. Missing numeric values do not match
numeric filters and appear last when sorting by that value.

The current district suggestions are Kentron and Arabkir. Other district
IDs can be entered; a complete agreed district list remains to be supplied.

The mock catalogue uses the existing C01 listing. Additional listings used
in tests do not appear on the website.

Automated checks include URL parsing, combined filters, inclusive ranges,
exact rooms, missing values, sorting, stable ordering and pagination.
The latest test run passed all 39 tests.

Real backend catalogue integration still requires the C03 endpoint.
The interactive map remains D05 work.

## Planned map renderer (D05)

The agreed renderer is MapLibre GL JS. The target opening screen is a map filling
the viewport below the header, with compact filters, linked listings and a 2D/3D
building mode. This remains planned: no renderer dependency or live tiles are
installed by the documentation update. Provider, Yerevan height-data coverage,
attribution and costs must be validated in D05. Rental color layers need a legend,
counts/freshness and suitable aggregate data; no-data areas remain neutral.
See [the revised map design](../docs/design/D01-screen-contracts.md#map-first-revision--agreed-2026-10-22).


## D05 map layout checkpoint

The homepage introduces Yerevan with a framed OpenFreeMap basemap beneath a
short navy headline. Browse rentals moves to the existing filter panel; the
catalogue, USD/AMD choices and URL search state remain available below. The old
second map placeholder is removed. The basemap currently stays the same in both
UI themes; framing and controls follow the selected theme.

The embedded map keeps cooperative wheel/touch zoom and the +/− controls enabled,
while ordinary scrolling can browse the page. The UI does not display a modifier-key hint. Expand map
opens a native modal dialog with wheel zoom, focus containment, Close/Escape and
page-scroll locking. Closing restores trigger focus, page position and the map
camera. Ordinary clicks or drags never open full screen automatically.

MapLibre 6 uses the bundled `maplibre-gl-worker.mjs?url` worker, explicitly served
by Vite. `VITE_MAP_STYLE_URL` can override the default OpenFreeMap Liberty style.
OpenFreeMap/OpenStreetMap attribution remains visible in the map controls. A map
loading/rendering failure does not remove the catalogue or Browse rentals action.

Small neutral rental dots use only usable source coordinates from the current catalogue
page, with the same filters. Prices remain in the clickable preview and accessible marker names,
using shared USD/AMD formatting. Listings with missing, invalid
or unknown-confidence coordinates remain in the catalogue without invented map
positions. The map explicitly reports page coverage and whether further results
exist. Marker colors indicate selection, not a price comparison or fraud score.
Keyboard-accessible marker buttons open a React-rendered preview with rent,
rooms/area, coordinate precision, synthetic/stale labels and a details link.
Embedded and fullscreen views share selection and preserve catalogue return.
Untrusted titles/labels are rendered as text, never as HTML.

Marker clustering/card highlighting,
3D building data and a rental-price gradient remain D05 work; the visible basemap
is not a visualization of rental-price measurements.

Checkpoint validation: TypeScript, all 108 tests and the static build pass. Changed
map files pass ESLint; full lint still reports the 23 pre-existing SiteHeader
formatting errors and eight existing Fast Refresh warnings. Vite reports a large
MapLibre chunk; the renderer is lazy-loaded separately from the catalogue shell.
Browser checks exercised real WebGL and the bundled worker with a local test
style, native dialog focus/scroll behavior, filters/detail return, dark framing
and 320/390px layouts. Marker browser checks also cover keyboard selection,
currency changes, fullscreen details navigation and filter removal. Live OpenFreeMap/font requests were denied by the cloud
network policy; verify actual Yerevan tile rendering locally after pulling.

The map introduction preserves the shorter heading, compact spacing, 1250px frame
and taller desktop canvas (`clamp(420px, 65svh, 760px)`). Mobile/fullscreen sizing
remains independent. Dots have 44px click targets around an 18px visual marker.
The agreed future area gradient measures monthly asking rent per m², from green
(lower) through yellow/orange to red (higher), with insufficient data neutral.
It does not represent deviation from an estimated range; that comparison remains
separately labelled in listing details. The mock-only design preview described below uses an independent invented surface,
not inferred values from the single rental fixture or a partial catalogue page.

### Explicit map-area search

Moving the map updates only its viewport. Search this area applies
`bbox=west,south,east,north` to the existing catalogue URL/query and resets page
to 1, preserving filters, sorting and page size. Applying ordinary filters keeps
the area restriction; removing the Map area chip removes only bbox. Clear all
removes bbox along with other filters. Links/reloads restore the bounded search.
The embedded map fits a restored bbox; full screen keeps the current camera.
Both map modes offer explicit search, and zoomed-out/crossing/invalid bounds are
blocked with a zoom-in prompt under C01's maximum 0.5° per-axis limit. Results
remain paginated and the coverage message never implies all matches are mapped.
The mock transport applies inclusive coordinate bounds before pagination, just
as the real collection API does. Missing coordinates cannot match an area query.
No API schema or backend changes are needed.

Fullscreen captures its starting camera once when opened. Subsequent viewport
updates do not feed the moving camera back through `jumpTo`; this prevents an
area-search feedback loop interrupting drag/zoom. Closing preserves the last
camera, and reopening starts there. Regression checks cover this lifecycle and
actual fullscreen zoom/drag changes to the searched bounds.

### Synthetic gradient design preview (mock mode only)

Mock mode opens with a smooth green → yellow → orange → red rental-price surface,
plus a persistent legend: **monthly asking rent per m², USD/m²/month, 6–24**.
This deterministic fixture is entirely invented for visual review. Its two smooth
peaks, elliptical extent and value scale are not observations, a prediction model,
administrative boundaries, or evidence of actual Yerevan price/coverage patterns.
Outside the demo extent there are no values. The translucent geographically
anchored raster is inserted below basemap road/label layers, so streets remain
readable. Values/geometry are isolated in `src/lib/map-demo-surface.ts` for later
replacement by an agreed real-data source. There is no real-gradient API fallback:
real mode never renders this fixture, even if requested by a component.

Before an area search, the map shows no apartment dots; the catalogue remains
available below. Search this area, now beside Expand map in the toolbar (beside
Close map in full screen), adds actual current-page fixture/API rental dots while
keeping the surface and legend. Pan/zoom keeps the previous results until another
explicit search, with an update message. Removing the Map area chip or Clear all
hides the dots again and keeps the surface. The surface is independent of listing
filters, pagination, selection and USD/AMD preference; the legend always explicitly
uses USD. Individual rental prices in previews still follow display currency.

Validation includes rendered green/warm raster pixels in a real WebGL browser,
initial hidden dots, search/clear, persistent legend, fullscreen zoom and toolbar
controls at 320/390px. The browser uses a controlled local basemap style because
live OpenFreeMap requests are blocked in the cloud; verify streets/labels locally.

Clear area appears directly in both map toolbars after an area search. It removes
only bbox, resets page to 1 and hides dots/previews while preserving other filters,
sorting, camera and the gradient. Toolbar controls wrap on narrow screens.
Browser checks verify embedded +/− change the actual searched bounds, ordinary
wheel scrolling moves the page, and zoom still works after closing fullscreen.
The compact legend uses one visible Demo data label, the scale/units and a No data
key; the invented fixture provenance and real-mode guard remain unchanged.

### Nearby metro/university layers

Metro and Universities are independent switches below each map toolbar and are
off initially. Enabling a layer queries the current viewport (not the rental bbox)
through the typed C01 GET `/api/v1/infrastructure` client. C01's 0.5° bound limit
applies. Moving the viewport refreshes enabled place layers without applying a
rental area search. Queries are disabled when both switches are off or bounds are
too broad; zoom-in/loading/error/empty states remain visible. Failed real requests
never fall back to fixtures. Retry places and explicit Load more places support
errors and paginated responses without claiming complete coverage.

Place markers use M (metro) and U (university), distinguishable from rental dots
and independent of rent colours. Keyboard buttons open named/type-labelled previews.
An expandable Nearby places list offers an alternative way to select each place.
Turning a selected layer off removes its marker and preview. Selection and switches
are shared between the frame and fullscreen; Clear area removes rental dots only.
The current mock transport extends the existing synthetic metro fixture with one
explicitly synthetic university and supports type/bbox filtering and pagination.
These are invented demo facilities, not an A05 facility inventory. C01 currently
has no point provenance/freshness fields, so the frontend does not invent those.
The real infrastructure route still requires backend implementation on this branch.

Validation: 108 tests, TypeScript, mock/real builds and changed-file lint pass.
Full lint retains the existing 23 SiteHeader formatting errors/eight Fast Refresh
warnings. Browser checks cover independent switches, named marker/list selection,
layer removal, shared fullscreen state, 320/390px layouts, and a real-mode client
with controlled HTTP responses for 503/no-fallback, retry and multi-page loading.
Live Yerevan map/provider and real backend integration remain local/deployment checks.
