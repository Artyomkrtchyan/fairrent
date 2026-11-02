# C05/D07 reviewer integration

This integration combines C05 PR #75 (`a729994`) and D07 PR #82 (`93722ee`)
with the browser session boundary and saved decisions. It uses existing C01 GET
queue and PATCH review contracts; no login or case-by-id endpoint is invented.

## Administrative session flow

1. Apply the C03 projection and C05 migration, then issue an expiring reviewer
   session as described in [C05 setup](C05-review-workflow.md).
2. An administrator verifies identity and delivers the token privately. In real
   mode, open `/reviews` and enter it in the password field. The queue request
   verifies backend access; supplying a token alone does not prove a role.
3. The token is kept only in React memory, never in localStorage, sessionStorage,
   URLs, query keys, environment variables or public API defaults. Reloading the
   page or signing out clears it. Sign out clears local access only; administrators
   use the existing revoke CLI to revoke the server session.
4. Only review GET/PATCH calls attach the token. They disable HTTP caching, omit
   cookies and reject redirects. HTTPS is required outside loopback HTTP
   development. `VITE_API_BASE_URL` is a trusted deployment setting, never a token.
5. 401/403 clears the session, aborts pending review requests and removes private
   query/mutation caches. New sessions have a new cache revision. A 503 retains
   the session and shows an unavailable state without substituting synthetic data.
   The backend checks expiry, revocation and the reviewer role on every request.
   Viewer sessions are denied review access.

This uses administrative C05 sessions, not identity-provider sign-in or automatic
refresh. Do not add tokens to logs, screenshots, issues or commits. Aborting a
request or signing out cannot undo a transaction already committed by the server.
Refresh the case before repeating a decision after any uncertain response. CORS
allows Authorization and Content-Type for configured frontend origins; bearer
credentials are supplied explicitly rather than via cookies.

## Decisions and evidence

- Pending cases can move to in-review or resolved; in-review cases can only
  resolve; resolved cases are read-only. Resolution requires a decision.
- Every action requires a nonblank reason of at most 2,000 characters and the
  current version. The form prevents duplicate submissions while saving.
- Saving is confirmed only after HTTP 200 with the matching case, a higher
  version and matching returned history event. The UI then displays the returned
  evidence/history and invalidates cached queue pages.
- A 409 refreshes the case and discards the stale draft. The reviewer must enter
  a new decision. Mutations are never automatically retried. Other write failures
  require a successful refresh before another decision.
- Queue status, listing, category and rule filters are supported by C05. Combined
  category/rule filters match the same signal in mock and real mode; counts and
  pagination use the same predicate.
- Queue links include a non-secret listing UUID so details filter by listing
  before locating the review. Older direct links without this hint scan at most
  50 pages of 100 records. Large queues still need an agreed C01 detail-lookup
  solution; the UI reports the limit instead of inventing an endpoint.
- USD stays canonical. `Money`/`RateNote` use shared display preferences; AMD is
  disabled when the shared exchange-rate endpoint cannot provide a valid rate.
- Mock mode uses the shared synthetic fixture, accepts no reviewer tokens and
  never writes. Price anomalies and risk evidence remain distinct; neither
  alone establishes fraud.

## Validation

```bash
cd frontend
npm ci
npm run typecheck
npm test -- --maxWorkers=2
npm run lint
npm run build
cd ..
python contracts/validate.py
python -m pytest backend/tests/test_reviews.py -q
# Only a disposable PostgreSQL database; tests use isolated schemas.
C03_TEST_DATABASE_URL=postgresql://.../c05_test python -m pytest backend/tests/test_reviews_postgres.py -q
```

Frontend integration tests cover protected reads, allowed transitions, returned
history/version, reason validation, duplicate submission, 401/403 cleanup,
stale-session responses and conflict refresh. PostgreSQL tests cover roles,
expiry/revocation, repeatable migrations, atomic history, concurrent updates,
rollback and category/rule filters. Backend tests validate C01 envelopes and CORS.
See C05-D07-validation.md for the local results and remaining verification limits.

Production signal generation, stable cross-run signal identity and denied-action
auditing remain outside this integration. Deployment requires the C05 migration
and administrator-issued sessions. This work does not merge or deploy the drafts.
