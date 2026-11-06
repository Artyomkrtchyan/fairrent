# D08 — Frontend demo and release verification

Status: **partially implemented; live acceptance is pending**. Owner: @manemazmand. Issue #34.

## Automated browser checks

Playwright tests in `frontend/e2e/d08.spec.mjs` run a real-mode Vite frontend against controlled synthetic API fixtures. They cover browsing, filters, listing details, coordinate and property assessments, chart/table analytics, reviewer access page, and mobile navigation. A dedicated GitHub Actions job runs Chromium and uploads failure screenshots.

Run locally from `frontend`:

```bash
npm ci
cd e2e
npm install --no-package-lock --ignore-scripts
npx playwright install chromium
npm test
```

These tests do not verify production API availability or production data.

## Live demo acceptance

For each scenario record the date, deployment SHA, device/browser, screenshots and result:

| Scenario | Verification | Status |
| --- | --- | --- |
| Browse | Real listing count, filters, pagination, source links | Pending |
| Map | Accurate markers, missing-coordinate fallback, responsive layout | Pending |
| Valuation | Real endpoint response, area vs property mode, errors and sparse data | Pending |
| Analytics | Real weekly aggregates, count, dates, missing and stale values | Pending |
| Reviewer workspace | Authorized staging workflow and saved decision history | Pending |
| Accessibility | Keyboard focus, mobile behavior, form labels and errors | Pending |
| Environment | Confirm frontend uses real API rather than mock fixtures | Pending |

Suggested demo: browse and filter a real listing; open its details; show map; switch analytics view; submit area-only and property valuation; demonstrate an authorized staging review; show a mobile view.

### Release sign-off

D08 is complete only after the automated job passes **and** the live acceptance results are recorded. Any unavailable backend data or manual access should be documented as a known limitation rather than reported as passed.
