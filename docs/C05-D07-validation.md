# C05/D07 local validation — 2026-11-01

## Scope and source revisions

- Isolated worktree: `tmp/c05-d07-integration`, branch `codex/c05-d07-integration`.
- Base main: `185b03f3ccd987ba878dc4416293c4cba4b4ad4d`.
- C05 foundation: PR #75, `a72999479910952a7179a3a147a0b26a4b122a52`.
- D07 foundation: PR #82, `93722eeed9396717fb947115dba3a49bfd5ea455`.
- Local changes add session entry in memory, protected review requests, saved
  decisions with confirmed history/version, session cleanup, conflict refresh,
  and backend category/rule filters. C01 schema files are unchanged.
- No scraping code, collection scripts, n8n workflows, listing exports or local
  deployment edits are included. The original checkout's edits remain untouched.
- No commits, pushes, remote PR edits, remote merges or deployments were performed.

The worktree contains both upstream foundations plus the integration changes.
Separate incremental patches are available outside the worktree:
`../c05-d07-backend.patch` applies to the specified PR #75 revision;
`../c05-d07-frontend.patch` applies to the specified PR #82 revision. They contain
only follow-up changes relative to those PRs, not the upstream foundations.

## Results

| Check | Result |
| --- | --- |
| Frontend TypeScript | Passed (`npm run typecheck`) |
| Frontend tests | 143 passed, 20 files (`npm test -- --maxWorkers=2`) |
| Frontend lint | Passed; 0 errors, 9 Fast Refresh warnings, including the new context module |
| Production build | Passed in mock mode and final real mode (`VITE_API_MODE=real npm run build`); bundle-size warning remains |
| C01 validation | Passed: 32 schemas, 35 fixtures, 16 rejected inputs, embedded examples |
| Backend HTTP/auth/regression tests | 78 passed |
| Real PostgreSQL C05/C03 tests | 16 passed, none skipped |
| Git whitespace check | Passed |

Backend commands used the isolated `.venv` with the repository's pinned FastAPI,
psycopg, pytest, httpx and contract-validator versions:

```bash
python -m pytest backend/tests/test_reviews.py backend/tests/test_health.py backend/tests/test_listings.py backend/tests/test_market_index.py -q
C03_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55483/c05_test python -m pytest backend/tests/test_reviews_postgres.py backend/tests/test_listing_postgres.py -q
python contracts/validate.py
```

The database was a disposable PostgreSQL 17.6 instance bound only to localhost,
using synthetic fixtures and isolated per-test schemas. It was stopped after
the tests. This validates C05 transactions and C03 projection regression, not
the full pipeline/ML/PostGIS suite. An initial attempt to include market database
tests stopped at missing Alembic during collection; those tests were not claimed
as passing or run against this non-PostGIS database.

Frontend integration coverage includes session headers/cache isolation, no token
persistence, both allowed transitions, mandatory reasons, returned history,
duplicate submissions, 401/403 cleanup, HTTPS enforcement, uncertain responses,
409 refresh without retry and 422/503 write failures. PostgreSQL coverage includes
session roles/expiry/revocation, optimistic concurrency, audit rollback and
combined category/rule filtering with bound parameters.

## Remaining verification

An interactive browser pass was attempted against the local synthetic servers.
The in-app browser could not reach the page; Windows Computer Use then stopped
because it could not determine Edge's current URL with sufficient confidence.
No token was entered through the UI. Visual layout, mobile responsiveness and
manual keyboard navigation remain unverified. DOM-based UI tests are passing.
The local API/frontend servers were stopped after the attempt.

No production reviewer session was requested, issued or tested. The administrative
session flow must be reviewed with the frontend owner before release. Identity
provider sign-in, automatic refresh and production signal generation remain
outside this integration. See `D07-reviewer-integration.md` for operation and
session/decision behavior.
