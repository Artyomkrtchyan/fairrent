# E05 — Security verification and incident response

**Status:** Runbook drafted; validation **not yet executed**. Owner: @manemazmand. Release approval requires component-owner sign-off. This document does not certify FairRent's security.

**Scope:** FairRent's owned staging environment, backend reviewer-session APIs, frontend, release CI, AWS infrastructure and sanitized application audit data. Do not perform invasive checks on third-party sites, production user data, or live credentials. Use staging and synthetic identities/records whenever possible.

## Preconditions and authorization

- Record the staging hostname, deployed commit SHA, test window, and written approval from the deployment/API owner before manual security tests.
- Use a disposable synthetic reviewer actor and a separate viewer actor. Issue short-lived test sessions via the administrative CLI only; **do not paste bearer tokens** into tickets, scripts committed to Git, screenshots, or logs.
- Keep staging database state isolated from production. Never attempt to read production secrets or copy unrestricted property/raw listing data into evidence files.
- Store evidence in a restricted team location, with the minimum necessary timestamps, request IDs, sanitized statuses and reproducible steps.
- All findings must have severity, impact, owner, mitigation, retest result and release disposition; unresolved release risks require written acceptance by the accountable owner.

## Verification checklist (execute and record evidence)

| ID | Check / expected behavior | Evidence to record | Status |
| --- | --- | --- | --- |
| E05-01 | CI security jobs complete: secrets, Python/frontend dependencies, image scans. Failures are triaged, not waived silently. | Workflow URL, commit SHA, relevant findings and decision | Not run |
| E05-02 | Unauthenticated GET /api/v1/reviews and PATCH /api/v1/reviews/{id} yield 401 and do not expose review data. | Sanitized HTTP status, UTC timestamp, request ID | Not run |
| E05-03 | Malformed, expired and revoked reviewer sessions fail with 401; a valid viewer/non-reviewer session fails with 403. | Synthetic session IDs (not bearer tokens), status, request IDs | Not run |
| E05-04 | Reviewer PATCH rejects malformed input, missing/overlong reasons, unauthorized actor fields, and stale version/conflicting updates; no audit mutation is committed for failures. | Validation status, review version before/after, sanitized DB assertion | Not run |
| E05-05 | Authorized reviewer decision updates version and appends exactly one immutable history event, with correct actor, action/decision, outcome and UTC time. No bearer secret or raw sensitive payload is stored in history. | Sanitized audit field names and representative redacted event | Not run |
| E05-06 | Database interruption causes 503 and fails closed rather than permitting reviewer access or losing prior audit history. | Staging-only failure test and recovery record | Not run |
| E05-07 | Frontend keeps session credentials only in memory, clears state on logout/401, does not display tokens in URLs, and avoids accidental duplicate PATCH submissions. | Manual browser checklist and sanitized console/network observations | Not run |
| E05-08 | HTTPS configuration, allowed origins and security-relevant request headers match deployed configuration; staging and production settings are explicitly distinguished. | Config review, hostname, date, owner | Not run |
| E05-09 | Confirm incident reporting contacts, on-call channel, access to logs, log retention and session revocation procedure are usable by an authorized operator. | Tabletop exercise notes and owner approval | Not run |

Existing implementation references: `backend/reviewer_auth.py` (opaque bearer token, digest-only session storage and revoke CLI), `backend/review_routes.py`, `backend/review_repository.py`, `docs/C05-review-workflow.md`, `docs/E01-security-risk-assessment.md`. These describe implementation, **not evidence that staging checks were run**.

## How to conduct the scoped tests

1. Record deployment hash and stage-only reviewer IDs; confirm owner approval and safe test records.
2. Run the configured security workflow and capture relevant URLs and failed/ignored findings. Do not substitute a clean CI run for manual authorization checks.
3. In a test client, omit the Authorization header, then use syntactically invalid and expired credentials. Expect 401. Separately test a valid `viewer` session; expect 403. Never log token content.
4. Create one synthetic pending review. With an authorized reviewer session, exercise bad/empty/overlong reasons and outdated version; assert 422/409 and no state mutation. Apply one valid decision, then confirm the history actor and UTC timestamp and exactly one version increase. Confirm repeat submission cannot duplicate the decision.
5. Revoke the **test** session using the administrative CLI, and verify subsequent requests fail with 401. Do not revoke another person's active session.
6. On staging only, simulate a brief backend database outage with the deployment owner's support; verify 503 fail-closed behavior, then restore and verify successful requests and preserved audit history.
7. Inspect browser DevTools while using the reviewer UI, checking unauthorized errors and logout handling. Record screenshots without credentials or private listing details.
8. Record evidence and outcomes in the matrix below. Every failed check requires a GitHub issue or explicit documented owner acceptance before release.

## Incident response runbook

**Triggers:** suspected reviewer token exposure; unexpected review updates; repeated 401/403 anomalies; secrets found in CI or log output; altered audit history; suspected data access outside intended scope; backend compromise.

**Severity/triage:** P1 = confirmed credential compromise or unauthorized decision/data access; P2 = plausible exposure with no verified abuse; P3 = contained misconfiguration or finding with no demonstrated exploit. The incident coordinator may raise severity on new evidence. Avoid claiming a leak without checking.

**1. Detect and report (immediate):** Notify application/deployment owner and security coordinator through a private team channel. Record UTC first-seen time, affected environment, user-visible symptoms, request IDs, suspected scope and reporter. Do **not** paste a leaked token to GitHub.

**2. Triage and preserve evidence:** Identify affected actor/session IDs, review IDs, UTC intervals, API statuses, deployment SHA and supporting CloudWatch/application audit logs. Limit access to evidence; redact bearer token values, authorization headers, passwords, raw sensitive payloads and unnecessary personal data. Preserve originals in restricted approved storage and note who accessed/collected them. Do not modify audit history to simplify the narrative.

**3. Contain:** Authorized operators revoke compromised reviewer sessions using `python -m reviewer_auth revoke --session-id <session-uuid>` in the appropriate deployed API environment. If compromise is wider, consider temporarily disabling protected mutations, rotating implicated deployment credentials and restricting service access through established IAM/change controls. Containment changes require owner coordination; verify no unrelated users are locked out unnecessarily.

**4. Eradicate and recover:** Fix the identified cause (for example, leaked debug logging, incorrect permissions or missing authorization), review affected decision history, deploy a verified release, invalidate affected credentials and reissue fresh sessions privately. Verify authorized and unauthorized access outcomes, audit integrity and normal data processing. Never silently delete suspicious decisions: reconcile and annotate through an approved audit process.

**5. Communicate:** Coordinator updates the team with factual incident status, impact and next action. Production disclosure or external notification is a decision for authorized owners based on actual affected data and applicable requirements.

**6. Post-incident review:** Record timeline (UTC), root cause, confirmed impact, what worked/failed, corrective actions with owners/deadlines, retest evidence and release decision. Update risk register and CI checks as necessary.

## Tabletop rehearsal — synthetic reviewer session exposure

**Scenario:** A fictional reviewer token is reported as accidentally copied into a private staging diagnostic output. Use an **invented placeholder only** in notes, not a functioning token.

Expected team sequence: classify and notify → identify synthetic session ID and affected interval → review sanitized access logs → revoke test session → confirm further test requests return 401 → inspect synthetic decision history for unauthorized changes → document cleanup, owner sign-off and lessons.

**Rehearsal record (not yet completed):** Date/time UTC: TBD; participants: TBD; environment: staging; simulated evidence: TBD; containment result: TBD; recovery check: TBD; action owners: TBD.

## Evidence and release-decision template

| Check/finding ID | UTC time and environment | Commit / run URL | Observed status and sanitized evidence | Owner / action | Retest | Release disposition |
| --- | --- | --- | --- | --- | --- | --- |
| TBD | TBD | TBD | Not executed | TBD | Pending | Pending |

**Release rule:** Mark E05 complete only when applicable automated and scoped manual checks have recorded results, a synthetic incident rehearsal has occurred, audit evidence has been inspected for actor/action/outcome/UTC time without token disclosure, and remaining risks have owner acceptance. Any non-applicable check needs a documented rationale. 
