# E02 — Security scanning and findings

Date: 2026-11-02. Scope: FairRent secret scanning, dependency auditing, container images, and GitHub Actions review. Related issue: #48.

## Checks introduced
- Gitleaks v8.30.1 (full checked-out Git history, redacted results), downloaded with an integrity check.
- pip-audit for backend runtime/development, ML training and contracts requirements.
- npm audit for frontend dependencies (fails on HIGH or CRITICAL).
- Independent Trivy image scans for backend and frontend (HIGH/CRITICAL fail the job).

**CI status:** Locally linted with actionlint; GitHub-hosted jobs and their actual results must still be checked on this PR. A clean workflow syntax is not proof that tools execute successfully.

## Local evidence collected by Mane
| Check | Observation | Status |
|---|---|---|
| actionlint | Passed; exit 0 | Validated syntax |
| Gitleaks history scan | 129 commits, ~16.71 MB; no leaks detected | Passed in local scan |
| Synthetic Gitleaks detection | Temporary custom rule and harmless string; 1 leak detected | Positive control passed; does not prove default rule coverage |
| Frontend npm audit | 16 MODERATE findings, mainly minimatch and dependent tooling; no HIGH or CRITICAL reported; audit-level=high exit 0 | Passed threshold; remediation review pending |
| Frontend image Trivy | Before: 1 CRITICAL (brotli-libs), 2 HIGH (curl/libcurl); after RUN apk upgrade --no-cache and rebuild: 0 HIGH/CRITICAL | Local rescan passed; runtime smoke test and CI rerun needed |
| Backend image Trivy | 47 HIGH, 0 CRITICAL in local scan (45 Debian OS package findings and 2 vendored Python tooling findings) | Open finding; backend owner remediation required |
| pip-audit | Tool installed locally (2.10.1); no completed Python audit results provided | Pending GitHub CI execution |

No genuine credentials were used as fixtures, and no cloud credentials were added to CI. Temporary synthetic test files were removed.

## Findings, severity, owners and next action

1. **Backend container: HIGH** — local image scan reports 47 HIGH findings. Some may not have a published fix; results must be refreshed against the CI image digest and individual CVEs assessed. Owner: Artyom/backend; do not silently suppress findings. Consider fresh base images, minimizing installed packages, dependency updates and rerunning Trivy.
2. **Frontend container: remediated locally, pending CI and smoke test** — Alpine upgrade removed three reported HIGH/CRITICAL issues in the observed local rescan. Rebuild reproducibility and Nginx readiness/runtime checks require verification. Owner: frontend/security.
3. **Frontend dependencies: MODERATE** — 16 reported minimatch-related advisories, largely tooling/transitive packages. Audit fix --force recommends potentially breaking dependency changes; assess safe upgrades, retest after changes. Owner: frontend.
4. **Python dependencies: unknown** — four requirements manifests included in CI audit, but results not yet known. Owner: corresponding component maintainers.
5. **CI supply chain: review required** — checkout, setup-python, setup-node and Trivy action are version-tagged rather than immutable SHA pinned. Coordinate pinning and updates with CI owner. Job token uses contents:read; deploy workflow separately requests id-token:write only in its gated deploy job.

## Workflow threat review
- **Permissions:** new security workflow uses global contents:read only; checkout persist-credentials:false. Existing deployment workflow scopes id-token:write to the main-only deploy job. Confirm repository-level default token permissions and ruleset protections with Artyom.
- **Untrusted PRs:** scanning is attached to pull_request, not pull_request_target; no PR code is executed with elevated cloud credentials by the new security jobs. The backend/frontend Docker builds and dependency tools process untrusted repository contents on ephemeral runners: review third-party action provenance and permissions.
- **Action references:** current workflow references version tags. Prefer full immutable commit SHA with human-readable version comments after CI-owner review.
- **Artifacts and logs:** no upload steps introduced; Gitleaks uses --redact. Ensure logs and future reports contain no secret values, and restrict retention/access if artifacts are added.
- **Runtime privileges:** backend Dockerfile currently defaults to root user, EXPOSE 8000; frontend Nginx runtime defaults to container root for port 80, EXPOSE 80. EXPOSE is image metadata, not host publication. Discuss least-privilege options and runtime port bindings with Artyom before altering backend/deployment.
- **Base image/packages:** python:3.10-slim and nginx:stable-alpine are moving tags. Prefer scheduled rebuilding, vulnerability remediation, and digest pinning after compatibility tests.

## Severity policy and temporary exceptions
- CRITICAL/HIGH: CI job fails; triage promptly with owner. No automatic permanent waiver. The current backend failure is visible and requires owner disposition.
- MODERATE/LOW: track advisory, exploitability and upgrade path; fix in an agreed maintenance window.
- A temporary exception, if necessary, must list specific CVE/package/image digest, justification, compensating controls, approver, creation date, expiry date (suggest at most 30 days for HIGH), and evidence of retest. Store the record in the issue or a reviewed exception file; do not blanket-ignore all findings.
- No exceptions are approved or active in this report.

## Outstanding acceptance and handoff
- Confirm all five jobs run on GitHub and inspect logs, especially Gitleaks checksum/download, pip-audit resolution and docker builds.
- Reproduce a CI-level synthetic negative control in an isolated throwaway branch/fixture without committing fake keys to main; record expected failure.
- Review action SHA pinning, CI token scopes, untrusted PR effects and artifact access with Artyom.
- Request backend owner triage/retest of 47 HIGH findings, root runtime and unnecessary packages; approve only narrowly documented temporary exceptions.
- Smoke test updated frontend runtime and record result.
- Do not close E02 until the above acceptance items are addressed or explicitly accepted by the owner.
