# C05 reviewer workflow foundation

This implements the protected C01 queue and decision API. Issue #21 stays open:
production rule generation and C04/B06 integration remain pending. No risk score,
fraud conclusion or production signal is invented by this change.

## Setup and sessions

After initializing the C03 projection, run from the repository root:

```bash
docker compose exec api python -m reviewer_auth migrate
docker compose exec api python -m reviewer_auth issue --actor-id <reviewer-uuid> --hours 8
docker compose exec api python -m reviewer_auth revoke --session-id <session-uuid>
```

The issuer is an administrative CLI requiring database access, not a public
registration or login endpoint. The operator verifies the reviewer identity and
maps it to a stable UUID before issuing a session. A token is shown once after
commit. Deliver it privately; never paste it into an issue, application log or
committed file. Clients send `Authorization: Bearer <token>` over HTTPS outside
local development, keep the token in memory and clear it on logout or 401.
Interactive identity-provider login and automatic refresh are future work.

Tokens use 32 cryptographically random bytes; only SHA-256 digests are stored.
Sessions expire in 1–24 hours (default 8) and are checked on every request.
Revocation applies to subsequent authentication checks; an already authorized
request can finish. Missing, malformed, repeated, unknown, expired or revoked
credentials return 401 with `WWW-Authenticate: Bearer`; non-reviewer sessions
return 403. Database failure returns 503 and never bypasses authorization.
There are no default reviewer tokens and no tokens in environment examples.

## Queue and decisions

- `GET /api/v1/reviews`: optional `status`, `listing_id`, `category`, `rule_id`, `page`, `page_size`
  (1–100), ordered by latest update descending then UUID ascending. A
  repeatable-read snapshot keeps count, rows, listing evidence and history
  consistent. Unknown/repeated parameters are rejected. Category/rule filters
  match the same signal when combined.
- `PATCH /api/v1/reviews/{id}`: C01 `status`, `decision`, `reason`, `version`.
  A nonblank reason of at most 2,000 characters is required. Actor identity is
  derived from the session and cannot be supplied in the request body.
- Allowed transitions: pending → in_review, pending → resolved,
  in_review → resolved. In-review has a null decision; resolved requires
  dismissed, needs_follow_up or confirmed_issue. Resolved reviews cannot reopen.
- Every mutation checks the current version under a row lock. Outdated versions,
  repeated transitions and updates to resolved reviews return 409. Missing IDs
  return 404. Refresh the queue after a conflict instead of blindly retrying.
- A successful mutation increments the version and saves a history event with
  actor UUID, reason, decision and UTC time in the same transaction. An audit
  insert/commit failure rolls back the decision. No token is written to history.
- CORS permits Authorization/Content-Type and PATCH for configured frontend
  origins. All responses retain the existing error envelope and request ID.

## Trusted signal producer boundary

`review_repository.enqueue(connection, listing_id, signals)` accepts explicit
C01 risk-signal documents for an already published listing. It validates unique
IDs, subject identity and timezone-bearing timestamps, stores immutable evidence,
and serializes producers with a subject row lock. The caller owns the transaction.
Identical evidence reuses an open review; changed evidence raises a conflict
instead of silently modifying evidence while a reviewer is working.

This helper has no public HTTP route. Current integration tests use synthetic
evidence only. Without a producer the queue is empty. B06/C04 integration must
define rule evaluation, stable signal identity, cross-run deduplication including
resolved reviews, changed-evidence handling, rule-version provenance, and public
listing-detail signal publication before final C05 acceptance. Price anomalies
and risk evidence retain distinct categories in stored and returned documents.
The review confirms an issue in evidence; it does not establish fraud.

The database stores immutable signal snapshots for each review and loads the
current listing projection with current freshness. Application code only appends
history; database privilege hardening and full denied-action audit logging remain
release security work under E03/E05.

## Verification

```bash
python -m pytest backend/tests/test_reviews.py -q
C03_TEST_DATABASE_URL=postgresql://.../c05_test \
  python -m pytest backend/tests/test_reviews_postgres.py -q
python contracts/validate.py
```

Integration checks use isolated schemas in a disposable test database. They cover
repeatable migrations, real session hashes/roles/expiry/revocation, contract-valid
queue/decision responses, filters, version conflicts, concurrent decisions and
rollback after an audit failure. Existing CI runs these tests with PostGIS.
