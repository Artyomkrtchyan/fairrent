# E02 — Security scanning and findings

## Final isolated E02 verification — November 14, 2026

**The final remediation branch `security/E02-python312-remediation` supersedes the earlier draft scanner branch.** All ten security jobs and all Component CI jobs passed with the distroless Python 3.12 backend image, pinned Pillow 13 and SoupSieve 4.1, non-root API/worker, patched Nginx, and the existing backend/ML/frontend test suites. See [E02 Security CI](https://github.com/Artyomkrtchyan/fairrent/actions/runs/43591264815) and [Component CI](https://github.com/Artyomkrtchyan/fairrent/actions/runs/43591264797); the independent experimental image also passed [Security CI](https://github.com/Artyomkrtchyan/fairrent/actions/runs/43590714521) and [Component CI](https://github.com/Artyomkrtchyan/fairrent/actions/runs/43590714484).

The distroless image contains the required libffi, libstdc++ and libgcc runtime shared libraries. The previous Debian slim image's 47 HIGH OS findings are not concealed by ignored CVEs; the application was rebuilt using a smaller supported runtime and rescanned successfully. A later explicit HTTP /health startup smoke step was added and must remain green on the canonical PR run.

**Release disposition:** CI passing is not permission to deploy. Backend owner must approve Python 3.12 compatibility, API and B06 image changes, and container lifecycle behavior. No AWS or deployed state changed, and no security findings were waived. Earlier failed-run sections below are historical records, not the latest release status.


Date: 2026-11-02. Scope: FairRent secret scanning, dependency auditing, container images, and GitHub Actions review. Related issue: #48.

## Checks introduced
- Gitleaks v8.30.1 (full checked-out Git history, redacted results), downloaded with an integrity check.
- pip-audit for backend runtime/development, ML training and contracts requirements.
- npm audit for frontend dependencies (fails on HIGH or CRITICAL).
- Independent Trivy image scans for backend and frontend (HIGH/CRITICAL fail the job).

**CI status (initial PR run #1):** Component CI passed. Security CI ran and failed: Gitleaks, frontend npm audit, and frontend Trivy passed; Python dependency audit failed on ML training requirements; backend Trivy failed. Python audits were subsequently split into a fail-fast-disabled matrix to display each manifest result independently; latest run needs verification.

## Local evidence collected by Mane
| Check | Observation | Status |
|---|---|---|
| actionlint | Passed; exit 0 | Validated syntax |
| Gitleaks history scan | 129 commits, ~16.71 MB; no leaks detected | Passed in local scan |
| Synthetic Gitleaks detection | Temporary custom rule and harmless string; 1 leak detected | Positive control passed; does not prove default rule coverage |
| Frontend npm audit | 16 MODERATE findings, mainly minimatch and dependent tooling; no HIGH or CRITICAL reported; audit-level=high exit 0 | Passed threshold; remediation review pending |
| Frontend image Trivy | Before: 1 CRITICAL (brotli-libs), 2 HIGH (curl/libcurl); after RUN apk upgrade --no-cache and rebuild: 0 HIGH/CRITICAL | Local rescan passed; runtime smoke test and CI rerun needed |
| Backend image Trivy | 47 HIGH, 0 CRITICAL in local scan (45 Debian OS package findings and 2 vendored Python tooling findings) | Open finding; backend owner remediation required |
| pip-audit | In initial GitHub Actions run, backend runtime and backend development both returned no known vulnerabilities; ML training audit reported 39 Pillow 12.3.0 advisories, with 13.0.0 listed as fix version. Contracts audit was skipped due to sequential job failure; now runs independently in matrix. | ML remediation/retest pending; contracts follow-up run pending |

No genuine credentials were used as fixtures, and no cloud credentials were added to CI. Temporary synthetic test files were removed.

## Findings, severity, owners and next action

1. **Backend container: HIGH** — local image scan reports 47 HIGH findings. Some may not have a published fix; results must be refreshed against the CI image digest and individual CVEs assessed. Owner: Artyom/backend; do not silently suppress findings. Consider fresh base images, minimizing installed packages, dependency updates and rerunning Trivy.
2. **Frontend container: remediated locally, pending CI and smoke test** — Alpine upgrade removed three reported HIGH/CRITICAL issues in the observed local rescan. Rebuild reproducibility and Nginx readiness/runtime checks require verification. Owner: frontend/security.
3. **Frontend dependencies: MODERATE** — 16 reported minimatch-related advisories, largely tooling/transitive packages. Audit fix --force recommends potentially breaking dependency changes; assess safe upgrades, retest after changes. Owner: frontend.
4. **ML training Python dependencies: reported advisories** — GitHub Actions pip-audit detected 39 known vulnerabilities in resolved Pillow 12.3.0, suggesting upgrade to 13.0.0. ML training requirements are unbounded for certain packages; ask ML owner to test Pillow 13.0.0 compatibility and apply an appropriate constraint in the appropriate ML requirements file; do not modify the ML stack blindly. Backend runtime and development audits passed in initial run. Contracts audit was previously skipped; independently scheduled in the matrix. Owner: ML / respective component maintainers.
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

## Latest follow-up (2026-11-02)
- Security CI run #3: Gitleaks, frontend npm, frontend Trivy, backend runtime pip-audit, backend development pip-audit, and contracts pip-audit passed. ML training pip-audit and backend Trivy failed.
- ML audit reported 39 advisories in Pillow 12.3.0, with Pillow 13.0.0 identified as fix. Do not force that major-version update until the ML owner confirms Python interpreter and dependent-library compatibility; current CI sets Python 3.10.
- Added CI synthetic-secret positive control using a temporary test-only regex and a separate frontend static-root runtime smoke test. These changes require hosted CI validation.
- No unapproved backend/ML dependency or deployment changes were made, and no exceptions granted.

## Verification update — 2026-11-13

- [Component CI run 263](https://github.com/Artyomkrtchyan/fairrent/actions/runs/43491403002) passed, including backend/frontend tests, Docker build, infrastructure checks, contracts and browser smoke.
- [Security CI run 9](https://github.com/Artyomkrtchyan/fairrent/actions/runs/43491402951): Gitleaks with synthetic control, frontend npm, frontend Docker image including runtime smoke, backend runtime and contracts audits all passed.
- **ML upgrade feasibility:** Python 3.12 + Pillow 13.0.0 passed pip-audit with no known findings and **89 ML tests passed, 6 skipped** in run 9. This is a proven experimental environment, **not** a migration of the deployed Python 3.10 runtime.
- **ML runtime Python 3.10 audit:** still fails on the older resolved Pillow. Migration requires ML/component-owner approval and compatibility review.
- **Backend development requirements:** now resolve soupsieve 2.10, reporting three advisories (CVE-2026-126190, CVE-2026-126193, CVE-2026-126191), with fix versions 4.0.0/3.0.2 as reported by pip-audit; retest after the owner approves an appropriate compatible version.
- **Backend container:** corrected the security build context to repo root, matching the updated backend Dockerfile. Trivy still reports Debian 13.7 HIGH findings (51 OS HIGH in scan output, plus vulnerable setuptools vendored packages). Needs backend-owner remediation and retest; severity gate remains enforced.
- **Security CI result:** failure due to genuine remaining dependency/container findings. **No waiver was issued**, and do not merge as green.
- Review requested from Artyom on [PR #88](https://github.com/Artyomkrtchyan/fairrent/pull/88) for backend runtime/user/package disposition, action reference pinning and approval.

## Confirmed remediation experiments — November 13, 2026

[Security CI run 13](https://github.com/Artyomkrtchyan/fairrent/actions/runs/43495357452) confirmed:
- **Python 3.12 + Pillow 13.0.0:** pip-audit reported no known vulnerabilities and ML tests yielded **89 passed, 6 skipped**.
- **Python 3.12 + SoupSieve 4.1:** pip-audit reported no known vulnerabilities and reviewer unit tests yielded **19 passed**.
- **Python 3.10 scans still fail:** backend-development resolves SoupSieve 2.10 (3 advisories); ML training resolves Pillow 12.3.0 (42 advisories). These failures are genuine and intentionally remain gating.
- **Backend image Trivy still fails:** separate remediation of OS and Python package issues is required.
- **Component CI passed** for the same head commit.

**Migration decision needed:** Owners must coordinate a compatible Python 3.12 transition in the ML and backend development environments, including runtime Docker images where the affected packages are installed, after complete component/integration testing. Experiment jobs do not update deployed software. Do not change audit interpreter alone or suppress advisories to claim remediation.

## Outstanding acceptance and handoff
- First GitHub Actions run examined: 3 security jobs passed, 2 failed; the Python audit now uses four independent matrix children. Verify the newest runs and archive results.
- Reproduce a CI-level synthetic negative control in an isolated throwaway branch/fixture without committing fake keys to main; record expected failure.
- Review action SHA pinning, CI token scopes, untrusted PR effects and artifact access with Artyom.
- Request backend owner triage/retest of 47 HIGH findings, root runtime and unnecessary packages; approve only narrowly documented temporary exceptions.
- Smoke test updated frontend runtime and record result.
- Do not close E02 until the above acceptance items are addressed or explicitly accepted by the owner.
