# E03 — Authorization and untrusted-input verification

Related to #49. Test evidence date: 2026-11-13.

## Changes on this branch

- Centralized URL validation for external rental listing links: allow HTTP(S) only, reject embedded credentials, unsupported schemes, malformed and ambiguous backslash URLs.
- Applied to both listing detail source links and reviewer case links; invalid URLs display a message instead of a clickable link.
- Added Vitest negative cases for active-content schemes and credential-bearing URLs.

## Confirmed automated evidence

- [Component CI run 264](https://github.com/Artyomkrtchyan/fairrent/actions/runs/43492488283): all component jobs passed (frontend tests, backend tests, Docker build, contracts, infrastructure, Chromium browser smoke).
- `backend/tests/test_reviews.py` already covers absent/invalid/duplicate authorization, viewer denied, bounded queue queries, invalid status/reason/extra actor, conflict, fail-closed DB errors and safe error text.
- `backend/tests/test_reviews_postgres.py` covers session expiry and revocation, concurrency, audit history rollback and parameterized rule filters with a SQL-injection-like string.
- `frontend/src/test/reviewer-integration.test.tsx` covers in-memory session flow, HTTPS requirement, failed mutations, version handling and audit response expectations.
- `frontend/src/test/external-url-security.test.ts` verifies the new link allowlist. Initial CI found a backslash normalization issue; after correcting it, the frontend suite passed.

## Remaining manual acceptance (not claimed completed)

- On approved staging, test XSS-looking listing descriptions, source URLs and encoded search parameters without using real user data. Inspect DevTools and browser output for execution, DOM injection or leaking headers.
- Verify listing page size, geographic range and request-body limits with bounded requests only. Test URL-fetching policy if there is any server-side fetch from user-supplied locations.
- Inspect reviewer API authorization against synthetic IDs across object boundaries; coordinate any implementation fix with backend owner.
- Confirm error responses do not disclose internal paths or SQL details and document staging test timestamps/commit.
- Obtain API/frontend owner sign-off before closing E03.

This report records tested code and remaining work; it is **not** a penetration-test certification or permission to test production.
