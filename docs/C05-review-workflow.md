# C05 reviewer workflow and B06 signal production

This implements the protected C01 queue, decision API and B06 consistency-signal
producer. C04/B07 calibrated-price integration remains pending; C05 is not yet
fully complete. Signals are review evidence, never a fraud conclusion.

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

This helper has no public HTTP route. `backend.generate_signals` now evaluates
B06 against the published C03 records and passes validated evidence through
`signal_repository.reconcile_signals` before calling `enqueue`. The review
confirms an issue in evidence; it does not establish fraud.

## Generate B06 signals after publication

Apply migrations before serving the new listing-detail code (001 must already
exist). The existing administrative command now applies both 003 and 004:

```bash
docker compose exec api python -m reviewer_auth migrate
docker compose exec api python -m sync_listings
docker compose --profile signals run --build --rm signals
```

Alternatively, from the repository root with PG* configured:

```bash
python -m pip install -r backend/requirements-signals.txt
python -m backend.generate_signals
```

The worker is a separate one-shot image (`backend/Dockerfile.signals`, repository
root build context). It ships B06, the A05 geography registry and numpy/pandas,
without CatBoost or model artifacts. The API image stays small and only reads
published signals. Generation is an explicit post-publication step; scheduling
belongs to C09. All signal and queue writes in one run commit together, and a
failed run rolls them all back. Output contains counts and versions, not raw
listing descriptions or credentials. Concurrent runs serialize using an advisory
transaction lock; listing row locks also serialize other trusted producers.

The command evaluates active listings only. Description/field consistency and
area plausibility can produce `risk_evidence`. District/location support requires
the optional **train-fitted** B06 artifact; without it no district-support finding
is raised. To supply it, bind-mount the artifact into the worker:

```bash
docker compose --profile signals run --build --rm \
  -v "$PWD/artifacts/b06:/artifacts/b06:ro" signals \
  python -m backend.generate_signals --district-support /artifacts/b06/district_support.json
```

Use `python -m ml.fit_district_support` to create that artifact from a training
snapshot; never fit it on the current serving inventory. Its rules version must
match the loaded B06 rules. Record the snapshot/reference version with the release.
No price anomaly is generated until B07 provides a model-bound calibrated interval;
the asking price alone does not trigger a review.

## Evidence lifecycle and public detail

- B06 deterministic UUIDs bind listing, rule, rules version and evidence. A replay
  preserves the first `created_at` and does not rewrite stored evidence. Reusing
  an ID with a different payload fails the transaction.
- Current findings live in `api_listing_signals`. `GET /api/v1/listings/{id}`
  reads the listing and active signals in the same snapshot. It does not expose
  reviewer identities, decisions or session information.
- Publication immediately deactivates signals when rule inputs change or the
  listing becomes inactive. A last-seen timestamp refresh alone keeps them.
  The next producer run computes the new current set. Withdrawn findings remain
  in storage and in historical review snapshots, but disappear from public detail.
- A new batch contains only active IDs absent from **all** previous reviews for
  the listing, including resolved reviews. Dismissed/confirmed evidence is not
  automatically reopened, even if the same finding disappears and later returns.
- While a review is open, new evidence is counted as `deferred`; the current
  review, version and audit history stay immutable. After resolution, the next
  producer run queues still-active, previously unseen IDs in a new review.
  Deferred evidence that has already cleared is never queued. No automatic
  reviewer decision or system actor is invented.
- Public active findings are independent of the review decision; a dismissed
  finding remains visible while the rule still flags the current listing. Review
  decisions are available only through the protected reviewer API.
- Each review retains a validated listing snapshot. If publication removes the
  listing, public detail returns 404 and current signals are deleted. The protected
  review still returns its archived listing (marked inactive), evidence and audit
  history; the missing public row does not block ingestion/publication or decisions.

On deployment, run migrations before switching API traffic. Regenerate signals
after a rules/reference upgrade; do not overwrite older review evidence.

The database stores immutable signal snapshots for each review and loads the
current listing projection when present, otherwise its archived listing snapshot.
Application code only appends
history; database privilege hardening and full denied-action audit logging remain
release security work under E03/E05.

## Verification

```bash
python -m pytest backend/tests/test_reviews.py backend/tests/test_generate_signals.py -q
C03_TEST_DATABASE_URL=postgresql://.../c05_test \
  python -m pytest backend/tests/test_reviews_postgres.py backend/tests/test_signals_postgres.py -q
python contracts/validate.py
```

Integration checks use isolated schemas in a disposable test database. They cover
repeatable migrations, real session hashes/roles/expiry/revocation, contract-valid
queue/decision responses, filters, version conflicts, concurrent decisions and
rollback after an audit failure. Existing CI runs these tests with PostGIS.
Signal tests also cover independent description contradictions, missing inputs,
no uncalibrated price alerts, concurrent producers, replay across resolved reviews,
deferred changed evidence, public invalidation, first-observation timestamps,
archived listings, existing-review migration and transaction rollback. These
backend signal tests need PostgreSQL but do not require the PostGIS extension.
The pipeline-to-API tests remain a separate PostGIS check in CI. CI also builds
and imports the worker image so omission of the B06/geography modules fails early.
