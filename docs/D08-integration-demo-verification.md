# D08 — Integrated frontend verification and demo

**Owner:** @manemazmand · **Issue:** [#34](https://github.com/Artyomkrtchyan/fairrent/issues/34)

**Status as of 2026-11-07:** Automated frontend checks pass and the owner has confirmed in-browser that the requested visual changes look correct. **Final D08 acceptance remains open** until outstanding live-flow evidence is recorded. A deployed CI job is not, by itself, a manual end-to-end verification.

## What is implemented

| Change | PR | Result |
| --- | --- | --- |
| Real-mode browser checks with contract fixtures, filter and valuation checks, reviewer workflow mock, accessibility smoke | [#99](https://github.com/Artyomkrtchyan/fairrent/pull/99) | Merged |
| Sticky **Back to map** control | [#102](https://github.com/Artyomkrtchyan/fairrent/pull/102) | Merged |
| Pagination returns to rental results; subtle Back to map transparency | [#106](https://github.com/Artyomkrtchyan/fairrent/pull/106) | Merged |
| Asking rent uses original source amount and original currency; valid current FX rate is used for display conversion | [#107](https://github.com/Artyomkrtchyan/fairrent/pull/107) | Merged |
| Balanced listing details sections, consolidated source and freshness information | [#108](https://github.com/Artyomkrtchyan/fairrent/pull/108) | Merged |

## Automated verification

- `frontend/e2e/` runs **Chromium Playwright in real API mode with intercepted synthetic contract fixtures**. The regression suite covers catalogue/filter/detail, coordinate and property valuation, analytics, reviewer authorization UI and synthetic decision response, mobile controls, empty/error/stale states, pagination, and source-currency display.
- The main commit `7c139aafd3142eb221bfcef4c32d9f138728f958` had successful **D08 Chromium browser smoke**, **Frontend checks**, **Backend tests**, **Backend Docker build**, **Infrastructure checks**, and **Contract validation** when reviewed on 2026-11-07.
- At that check, **Deploy main to AWS was still in progress** for that specific commit. Verify its final result separately: [GitHub Actions](https://github.com/Artyomkrtchyan/fairrent/actions).
- The previously merged listing-layout change (#108) had a successful main-branch AWS deploy workflow (run [42320296812](https://github.com/Artyomkrtchyan/fairrent/actions/runs/42320296812)).

To run the controlled browser suite from `frontend`:

```bash
npm ci
cd e2e
npm install --no-package-lock --ignore-scripts
npx playwright install chromium
npm test
```

**Limit:** Fixture-backed browser tests are not evidence of production content, deployed authorization, real reviewer audit persistence, or actual external API availability.

## Browser feedback and live acceptance evidence

On **2026-11-07**, the frontend owner reported reviewing the **deployed site in a browser** and confirmed that the requested visual changes appear as intended. This supports visual acceptance of the user-requested changes to the listing detail layout, Back to map positioning/transparency, pagination behavior and price display. No independent URL/viewport-specific screenshots or request traces were supplied with that confirmation.

| Scenario | Evidence currently available | Result |
| --- | --- | --- |
| Listing details layout and placement | Owner-reported in-browser visual approval; changes merged via #108 | **Owner visually approved** |
| Back to map styling/behavior and pagination scroll | Owner-reported browser approval; fixture regression in CI | **Owner visually approved** |
| Original AMD/USD asking rent display | #107 merged; CI tests for original amount and current-rate conversion; owner says requested changes look right | **Owner visually approved; live FX trace not recorded** |
| Browse, filter and source-link response from real API | Automated controlled fixture checks, but no production HTTP evidence attached | **Manual/API evidence pending** |
| Map pins, missing-coordinate fallback and mobile map behavior | Browser owner's general approval; no map-specific screen/response evidence | **Detailed acceptance pending** |
| Analytics backed by actual weekly aggregates | Fixture tests only; no evidence of live weekly data accuracy | **Pending** |
| Coordinate/property valuation, sparse/out-of-coverage handling | Fixture tests only; backend response and error proof not captured | **Pending** |
| Authorized reviewer decision and immutable audit history | Controlled synthetic browser mock only; staging reviewer test not documented | **Pending** |
| Keyboard access, form labels, narrow viewport, empty/error/stale scenarios | Automated smoke; no full manual accessibility record | **Pending** |
| Production frontend configuration and latest deployment SHA | GitHub deploy evidence for #108; no production request headers/build identity captured | **Pending latest-release confirmation** |

## Demo sequence

1. Browse actual rental listings and demonstrate district, price and other filters.
2. Open a listing's **View details**; show the balanced property-information, full-width assessment, source/freshness, and signals sections.
3. Demonstrate **Next/Previous** returning to the rental section and sticky **Back to map**.
4. Compare source-currency asking rent in AMD and USD and explain the effective FX rate. Original asking rent must remain unchanged.
5. Explore map/list correspondence, analytics chart/table, and both valuation modes with their limits/standard deviations.
6. In **authorized staging only**, demonstrate a disposable reviewer session, a saved decision, and sanitized audit history. Do not perform synthetic writes to production.
7. Test a narrow mobile viewport, keyboard navigation, and a known empty/error/stale state.

## Remaining release evidence

Before closing #34, attach or link **redacted** screenshots/check logs including browser/viewport, UTC date, the target URL and deployed commit, and actual outcomes for the still-pending rows. Capture one staging reviewer audit example if that flow is in release scope; otherwise document a reviewer-approved exception and known limitation. Do not include tokens, session credentials or sensitive record contents.

Record any observed defect, owner and disposition in #34. Close D08 only when its full acceptance criteria are evidenced and remaining risks are accepted by the appropriate owner.
