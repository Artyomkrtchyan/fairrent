# C07: pull-request checks and container builds

Issue #23. C07 is independent of deployment C08 and the unfinished model/rule
integrations in C04. This workflow checks components already present in main.

## Checks

`.github/workflows/backend-ci.yml` (Component CI) runs on every PR targeting main,
push to main, and manual workflow_dispatch. No path filter can silently omit a
required component check. Jobs have read-only repository permissions, bounded
execution times, and checkout without persisted credentials.

| Stable check name | What it verifies |
| --- | --- |
| Backend tests | Python 3.10 dependency compatibility plus backend, data pipeline and B03 ML tests against disposable PostgreSQL 16/PostGIS |
| Frontend checks | Node 22, npm ci from the committed lockfile, TypeScript, frontend tests and production build |
| Backend Docker build | Builds the API Dockerfile from its current backend context, without publishing or deploying |
| Contract validation | C01 schema/fixture validation and a clean diff after regenerating committed contracts |

Python dependencies are pinned in backend requirements and ml/requirements.txt;
the frontend uses the lockfile with npm ci (not npm install). Node major 22 is
selected; npm ci enforces the lock independently of local node_modules. Test DB
credentials are disposable CI-only values, not production secrets.

Backend tests includes pipeline and ML to preserve the existing GitHub check name
when later protections become available. A failed command fails its job; checks
are not hidden by continue-on-error, `|| true`, or a publish/deploy step. All jobs
run independently so a frontend failure still permits backend diagnostics.

Frontend lint is not made a new required C07 check: unchanged main currently has
formatting errors in SiteHeader.tsx. Type/build and test checks are enforced here;
formatting remediation remains separate from this focused CI change.

## Image and tag conventions

Current required image: API (`backend/Dockerfile`). PostGIS is an upstream test
service (`postgis/postgis:16-3.4`), not a project-built image. The frontend produces
static dist output; no frontend image exists or is required by this architecture.

CI builds `fairrent-api:ci-${{ github.sha }}`. For pull_request events, github.sha
is GitHub's synthetic merge commit, so the tested image represents the proposed
combined tree, not necessarily the PR head commit. For main pushes it is the
actual main commit. The full SHA avoids collisions. This tag identifies source;
it is not a claim that unpinned upstream/transitive dependencies are byte-for-byte
reproducible. Dependency compatibility and clean builds are verified in CI.

C08 may publish registry images as `sha-<full commit SHA>` and deploy immutable
image digests. An approved release can additionally have `v<major>.<minor>.<patch>`.
Do not overwrite release tags or deploy an unreviewed floating `latest`. C07 does
not add registry credentials, deployment permissions or a production publisher.
C04 changes the API build context; its merge must retain the new checks here and
update the existing Docker build command to that branch's repository-root context.

## Review and branch protection

CONTRIBUTING requires at least one other teammate's review. Before merging, a
maintainer verifies all four checks above are green for the current PR revision
and obtains that approval. This is a team process, not enforced branch protection.

On 2026-10-22, repository permissions confirmed admin access, but both GitHub's
main branch protection API and rulesets API returned HTTP 403:
`Upgrade to GitHub Pro or make this repository public to enable this feature.`
The repository is private. This is a plan restriction, not missing admin rights.
No billing, visibility or membership settings were changed. Since C07 explicitly
requires protection only where supported by the repository plan, the documented
manual review/check gate applies until the owner chooses a supported plan.

When supported, configure main to require PRs, at least one approving teammate,
and the four stable status checks above; keep force pushes and branch deletion
disabled. Preserve any stricter existing rules and decide administrator bypass
with the team. Do not claim these controls are currently configured.

## Validation evidence

Verified on 2026-10-22 using actual GitHub-hosted runners:

- [Positive run 39832185123](https://github.com/Artyomkrtchyan/fairrent/actions/runs/39832185123)
  for implementation commit `dbc534a`: all four jobs succeeded. Backend/data/ML:
  **203 passed**. Frontend: **39 passed**, TypeScript and production build passed.
  API image build, dependency compatibility and C01 validation/regeneration passed.
- [Controlled negative run 39832209500](https://github.com/Artyomkrtchyan/fairrent/actions/runs/39832209500)
  from [temporary PR #67](https://github.com/Artyomkrtchyan/fairrent/pull/67): the
  intentional backend assertion produced **1 failed, 203 passed** and a failed
  Backend tests check. The intentional TypeScript mismatch produced **TS2322**
  and a failed Frontend checks check. Later frontend steps were skipped rather
  than reporting success after that failure. The independent Docker and C01
  checks still succeeded.
- PR #67 was closed without merge, and its temporary branch was removed. Neither
  intentional fault is present in the implementation PR. The failed run remains
  as audit evidence; it is not an unresolved product failure.

Implementation: [PR #66](https://github.com/Artyomkrtchyan/fairrent/pull/66).
C07 is ready for teammate review and merge after its current revision is green.
The issue closes on merge, not merely when this document is committed. Plan-limited
branch protection remains explicitly documented, not claimed as configured.
