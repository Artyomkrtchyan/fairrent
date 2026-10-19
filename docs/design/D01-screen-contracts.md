# D01 — FairRent screen design

Owner: Mane (@manemazmand). Status: design draft for Mane and backend review.
Based on C01 v0.2.0 at `ce2265e`; this document does not approve C01 on behalf of any owner.

Open [the responsive visual wireframe](D01-wireframes.html) in a browser. It uses embedded styles and schematic geography, with no external dependencies, tracking, live tiles, or real listing data. Screen tabs, the light/dark toggle and the mobile List/Map switch work; forms, markers, currency and review actions illustrate future behavior. All sample numbers and locations are synthetic.

## Design and shared shell

Professional, colorful and map-focused. Revision 2 replaces teal with navy/royal blue. Light palette: navy `#18294C` text, royal blue `#244AC4` actions, pale blue `#EEF2FA` canvas and white cards; strong navy `#193A90` hero. Dark palette: `#10192D` canvas, `#192640` surfaces, `#EEF2FF` text and `#B7C4DF` secondary text. Use amber for warnings, red for errors, and text labels alongside every status. Rounded 12–20px panels, restrained shadows and a system sans-serif stack.

Light/dark switch is available on all screens, defaults to the OS preference and changes every screen consistently. This wireframe keeps the choice only while the page is open; D02 can retain the non-sensitive theme preference locally. Both themes require contrast and mobile/browser verification before release. Colors must not change map selection or assessment meaning.

The market assessment uses a blue summary header, side-by-side asking/estimated rent with explicit units, a separately labeled illustrative range, a plain-language explanation and visible comparables/freshness. Calculation/version details are expandable. The visual interval is not observed standard deviation; when calibrated bounds are absent the production view omits the band and explains unavailability.

Public navigation: Browse, Check a location, Market analytics. A separate Reviewer entry leads to protected work. Currency USD/AMD is shared across public screens. No sign-in is required for public browsing. Initial interface language: English; translation is a future decision.

Desktop >=1100px: full navigation, 32px gutters, split results/map. Tablet 700–1099px: compact navigation, two-column content where readable and List/Map toggle. Mobile <700px: single-column cards, menu, accessible Filters button opening a modal sheet, and List/Map toggle. Minimum supported width 320px. Details and review columns stack in reading order.

Use semantic headings, real labels, keyboard-operable controls, visible focus, >=44px touch targets, reduced-motion support and tested WCAG AA contrast in D02. Never convey state only through color. A dialog traps focus and restores it on close. The list provides an accessible alternative to map-only selection.

## User journeys and routes

| Journey | Proposed frontend route | Behavior |
| --- | --- | --- |
| Find an apartment | `/browse` → `/listings/:id` | Filter, compare, open details, return with filters/page/scroll preserved. |
| Assess a location | `/valuation` | Enter coordinates and optional characteristics; request assessment; inspect scope, evidence and limitations. |
| Understand the market | `/analytics` | Select district/period; compare weekly asking-price medians and sample counts. |
| Review evidence | `/reviews` → `/reviews/:id` | Authenticate, filter queue, inspect evidence/history, submit reasoned decision, confirm server result. |

These are UI routes, not replacements for C01 API paths.

## Browse — D02/D03, map delivered in D05

Desktop: heading and short purpose statement; filter bar; results count/sort; scrollable listing cards on the left and map on the right. Map remains within its column rather than trapping page scrolling. Mobile: list default, compact filter button with active-count badge, sort and full-width List/Map switch. Pagination follows the list; avoid infinite scroll in v1.

Filters: district, monthly rent min/max, exact rooms, area min/max. Apply validates ranges and resets page; Clear removes property filters. Sort: newest, price ascending/descending, area ascending/descending. Store filters, sort and page in URL; currency preference is separate. Default inventory is active. Missing values do not match numeric filters. Display filtered total and page controls from API metadata.

Cards: optional thumbnail or intentional architectural placeholder; title or neutral generated summary; monthly rent; district; rooms/area; last seen; market comparison label when supported. Missing asking rent says “Rent unavailable.” Do not invent an address, photo or estimate. An unavailable comparison says “Estimate unavailable,” distinct from a service error.

Map: price markers, selected marker/card synchronization and a keyboard-accessible popup opening details. Use one accent for selection; do not make marker color a fraud score. Optional metro/university layers have labeled icons. After panning, “Search this area” explicitly applies bbox and resets pagination. When `has_more=true`, show “Showing part of the results — zoom in or load more”; fetching only one page never implies complete coverage. No coordinates means no marker, but the listing remains in catalogue. Final tile provider and attribution require selection during D05; wireframe geography is not a real map.

## Listing details — D04

Desktop: back link; title/location; optional image; property facts/description/source; valuation panel alongside; risk evidence below in a distinct section. Mobile: asking rent and core facts first, then valuation, description, risk evidence and source.

Show expected rent and calibrated interval only when available; comparable count, freshness, factors and versions remain inspectable. Label “Above estimated range,” never “Fraudulent.” Explain price status separately from risk evidence. Price anomalies and other evidence keep their category and traceable rule. An inactive banner takes priority over promotional actions. The external source link uses safe URL handling and indicates an external destination; listing descriptions are plain text by default.

## Check a location — D09

Desktop form left, result right; stacked on mobile. Required latitude/longitude; optional area, rooms and supported apartment features. Radius/window controls follow C01 limits. Clear validation errors appear next to fields without deleting input.

Result begins with “Area reference” or “Property assessment.” Area reference explicitly says it is not a prediction for a particular apartment; disclose reference area separately from submitted features. Present assessment, monthly statistics, per-m² statistics, each sample count, radius/window, freshness and explanation. Observed standard deviation has its own labeled section, never a prediction-interval chart. Missing count/dispersion is not zero. Outside coverage is a specific input/result error, not an empty successful assessment.

## Analytics — D06

District/date controls; summary cards; weekly median chart; accessible data table beneath it. Show monthly and per-m² measures with their separate sample counts, reporting period and snapshot date. Plot gaps for absent/sparse periods, never a zero rent or a line implying missing measurements. Date coverage follows available_from/available_to. Heading says “Asking-price trends”; avoid promises of real-time or transaction-price accuracy.

## Reviewer workspace — D07

Separate protected workspace; queue filters for status, rule and signal category. Default pending, newest updated first. Queue shows listing summary, evidence category, status and update time. Detail shows asking-price context, evidence/rule version, full review history and decision form.

Follow C01 transitions and decision enum. Required nonblank reason, current version in update, disabled duplicate submission while saving. No optimistic success. Confirm from returned saved review. On 409, refetch and explain conflict while retaining typed reason; require deliberate resubmission against current data. On 401 request reauthentication and preserve draft in memory; 403 shows permission denial. Do not persist reviewer tokens/reasons in URL or local storage. Real OIDC setup remains a C05/D07 gate; mocks are labeled as such.

## USD/AMD behavior

Use GET exchange-rate metadata; USD remains canonical. Convert rents, estimates, bounds, means, medians, per-m² amounts and monetary standard deviations using the same rate. Counts, distances and percentages do not change. USD displays two decimals, AMD whole dram, half up. Show conversion source/date near currency help. Preserve original listing amount/currency in details.

Currency switching preserves canonical USD filters. Editing AMD min converts down to USD cents, max up to USD cents. Do not round intermediate conversions. If rate is stale/unavailable disable new AMD conversions and keep USD usable with an explanatory message. Fixture rate 400 is synthetic, not a production default.

## State matrix — applies across desktop and mobile

| State | UI behavior |
| --- | --- |
| Initial loading | Stable layout with skeletons, an accessible loading announcement and no fake result count. |
| Refreshing | Retain prior results labeled as updating; prevent out-of-order requests replacing newer selections. |
| Empty catalogue | “No rentals match these filters” plus Clear filters. Successful empty collection, not an error. |
| Empty analytics | “No observations for this period.” Chart gaps and no fabricated summary. |
| Empty reviews | “No pending reviews.” Normal successful outcome. |
| Service error | Clear message and Retry; preserve input, filters and drafts. Separate failed refresh from stale saved results. |
| Validation | Inline explanation, error summary/focus, preserve values. |
| Not found | Dedicated listing/review unavailable message and navigation back. |
| Insufficient evidence | Explanation and available sample statistics; null estimate/interval shown as unavailable. |
| Stale | Amber text/banner with actual source snapshot date, not just response-generation time. |
| Partial fields | “Not available” or neutral placeholder; hide unsupported marker/image, retain listing. |
| Inactive | Visible inactive label; accessible detail, excluded from default active results. |
| Partial map | Explicit total/shown count and load/zoom action; never suggest completeness. |
| Saving review | Progress indicator, prevent duplicate click, confirm only after server success. |
| Unauthorized/forbidden | Separate login-needed and permission-denied messages. |
| Review conflict | Explain newer server version, refresh evidence, retain reason, no silent overwrite. |

## C01 mapping and review checklist

| Screen | API/data source | Contract checks |
| --- | --- | --- |
| Browse/map | GET listings; GET infrastructure | ListingPage pagination, bbox, nullable coordinates/images, canonical USD, freshness. |
| Details | GET listings/{id}; GET listings/{id}/estimate | ListingDetail listing/signals/estimate; distinguish missing estimate from dependency failure. |
| Location | POST valuations | kind, cohort, assessment/statistics/interval blocks, explanation, price_status, freshness. |
| Analytics | GET market-index | Weekly periods, available date coverage, separate unit counts, null sparse buckets. |
| Reviews | GET reviews; PATCH reviews/{id} | Listing summary, signals/history, version, reason/decision and 401/403/409. |
| Currency | GET exchange-rate | amd_per_usd, status, source, effective_at, freshness. |

Use C01 fixtures, with the wrapper's `value` as the actual mock response. Do not create alternate public field names. C01 is a proposed contract even though files are merged; business endpoints are not implemented merely by existing schemas.

Before D01 is marked Done:
- Mane reviews wireframes and journeys, including mobile and states.
- Artyom confirms mapping, freshness/currency behavior and remaining C01 owner decisions; record agreement in the PR, not implied by this document.
- Resolve any schema mismatches together. Currency provider remains A/C decision; OIDC configuration remains C05 decision; map tiles remain D05 decision.
- Another teammate reviews the design PR. No approval or usability testing is claimed yet.

D02 follows agreed D01/C01: Vite + React + TypeScript, shared shell/routes, typed client and fixture-backed mocks, type/build validation. Real map, charts, review auth and valuation integration follow their corresponding D tasks.


## Revision 3 — agreed presentation direction

Keep “A clearer view of your next home.” with a large navy hero and original Yerevan-inspired city illustration. The illustration is schematic, not a source photo or an actual rental. A future licensed photo can replace it after image rights and mobile performance are checked. The current SVG has no third-party image dependency.

Scope remains long-term apartments only. Daily rentals are future development requiring a separate team-approved source, price-unit and valuation design; no enabled daily-rental option appears in this design.

Repeat USD/AMD next to prices, including cards and map markers. Place a synchronized currency control beside min/max rent fields as well as in the header. The static wireframe shows USD; actual conversions await D02 and the exchange-rate API, so clicking AMD does not simulate a fabricated rate.

Within-range badges use green; above-range badges amber; below-range badges blue with an explicit label; unavailable estimates neutral gray. Reserve red for errors and any future severe-price category only after a validated threshold and coordinated contract change. Median remains a statistical value, not a warning level. Text labels accompany every color in both themes.

Navigation includes Reviewer sign in; it opens an authorized-state mock solely for design inspection, not a real login. Public profiles, favorites and saved searches remain future features. Light/dark mode works across the design screens.
