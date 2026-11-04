# C09: weekly collection and operational monitoring

Status: implementation prepared for review; **not activated and not complete**.
C08 is the accepted checkpoint. The owner confirmed CloakBrowser works locally;
the installed local version and unattended Linux behavior are not yet verified.
No production collection, database load or crontab change is performed by this PR.

## Execution contract

Use a dedicated, stable Linux collection host and one non-root OS user. Do not
install this cron on an ephemeral ASG application instance: replacement would
lose its crontab, run state and browser profile, or create duplicate collectors.
The selected host must have private/restricted access to the ingestion database
and the API read model. Use the same database for SQLAlchemy `DATABASE_URL` and
libpq `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSFILE`, `PGSSLMODE`.
Store passwords in a user-readable-only file, not cron commands or Git.
Do not copy existing personal browser profiles to the server.

The wrapper takes a nonblocking `flock`, sets umask 077 and runs five stages:

1. CloakBrowser collection → a unique raw snapshot and hash-bound report.
2. Validate the report and import through the existing A03/A04 validation,
   normalization, deduplication and observation code.
3. Atomically publish the source inventory to the API projection (C03).
4. Refresh this week's neighborhood aggregates (A07/C06, Asia/Yerevan week).
5. Reconcile signals and reviewer queue using the existing C05 producer.

Collection has bounded page/detail caps, sequential requests, a minimum delay,
at most two HTTP-status/challenge attempts and a 45-second navigation timeout.
The entire job has a configurable four-hour deadline; timed-out or terminated
subprocess groups, including browser children, are stopped before releasing the
lock. Individual network exceptions fail promptly. Repeated pages, unexpected
redirects, challenges and changed/empty first-page markup are failures.
Only a recognizable empty later catalogue establishes the end of pagination;
a page or detail cap is partial. The host smoke run must confirm this terminal
markup against the actual site. If that cannot be established, keep runs partial
and investigate rather than enabling automatic deactivation.

Only monthly Yerevan apartments enter this path. Source prices/currencies are
preserved, avoiding the standalone scraper's source-rate conversion followed by
a second conversion. Normalization still uses the project's existing configured
exchange-rate provenance; updating ingestion FX policy is outside this change.
No raw listings, profiles, credentials or browser binaries are added to Git.

## Lifecycle and failure behavior

Each snapshot has a unique identity. Reimporting an already accepted snapshot is
rejected before another lifecycle run, so a replay cannot count as a second missed
observation. Reports must match the snapshot SHA256, segment, record count and success/partial
status, and be less than six hours old. Failed collection preserves any prior
snapshot and replaces its report with a failure, preventing accidental reuse.
Each job also uses a new directory so stale files cannot masquerade as new output.

Only a full, fresh snapshot with every record accepted permits A04 staleness
evaluation. A04 still requires its minimum seen ratio and consecutive missed
complete runs before deactivation. Partial or quarantined imports cannot clear
inventory. Partial accepted records can be published and analyzed, but the job
exits 2 and never advances `last-success.json`.

An import uses the existing per-record commits: a failed import may have saved
observations but does not publish them through subsequent stages. Recovery starts
a new job; A04 deduplicates repeated observations and preserves price history.
Do not replay stale snapshots as fresh observations. Each downstream publication
has its existing transaction boundary; this is not a transaction across all five
stages. A later failure preserves earlier committed stages and is reported as a
job failure, requiring a rerun rather than an automatic database rollback.

On SIGTERM the importer attempts to finish its run as failed. SIGKILL, host loss
or database unavailability can leave an ingestion row `running`; C03 deliberately
blocks publication while such a row exists. Before recovery, confirm no producer
is active, inspect `job.json`, protected logs and the exact `ingestion_runs.id`.
In the staging/production database selected by the operator, mark **only that
confirmed abandoned run** failed, without touching listings or observations:

```sql
-- Replace 123 with the inspected abandoned run ID; never update every running row.
UPDATE ingestion_runs
SET status = 'failed', is_complete = false, finished_at = CURRENT_TIMESTAMP,
    notes = 'Operator confirmed abandoned weekly job; inventory preserved'
WHERE id = 123 AND source = 'list.am' AND status = 'running';
```

Record the affected ID and outcome, then start a fresh collection. This is an
operator recovery step; the job never infers abandonment from elapsed time alone.

The lock prevents overlap on this host/state directory. It is not a distributed
lock; designate exactly one scheduler and avoid concurrent manual producers.

## Prepare and verify (operator steps, not automatic)

From the reviewed checkout on the selected Linux host:

```bash
python3 -m venv .venv-weekly
.venv-weekly/bin/python -m pip install -r data_pipeline/requirements-weekly.txt
.venv-weekly/bin/python -m pip check
# Install Linux browser system libraries through the host's normal admin process.
# CloakBrowser supplies its own browser binary; use its official install command.
.venv-weekly/bin/python -m cloakbrowser login
.venv-weekly/bin/python -m cloakbrowser install
.venv-weekly/bin/python -m cloakbrowser info
```

The wrapper is pinned to CloakBrowser 0.7.0. Official documentation states that
current versions require a license key and may select an updated browser binary;
record both wrapper and binary versions in server evidence. Configure the key
locally via `login` or the protected environment; never paste it into a PR.
Linux system dependencies, sandbox support, license readiness and source access
must be checked as the actual cron user. The launch keeps Chromium sandboxing
enabled. Do not change global host security settings to make the browser start.
See [official CloakBrowser documentation](https://github.com/CloakHQ/CloakBrowser).

First run the collector alone (no database writes):

```bash
.venv-weekly/bin/python -m data_pipeline.weekly_collect \
  --output data/raw/c09-probe/listings.json \
  --profile data/raw/weekly/profile --max-pages 1 --details-limit 3
```

This bounded probe is expected to be partial. Check records, original currencies,
districts, coordinates and the report. Then test the full wrapper against an
isolated staging database with migrations/read-model schema already initialized:

```bash
bash infra/scripts/run_weekly_ingestion.sh
.venv-weekly/bin/python -m data_pipeline.weekly_job \
  --state-dir data/raw/weekly --check
```

`FAIRRENT_WEEKLY_PYTHON`, `FAIRRENT_WEEKLY_STATE`, `FAIRRENT_WEEKLY_MAX_PAGES`,
`FAIRRENT_WEEKLY_DETAILS_LIMIT`, `FAIRRENT_WEEKLY_DELAY` and
`FAIRRENT_WEEKLY_TIMEOUT` override defaults. Use an absolute state path.
Set `FAIRRENT_MODEL_PACKAGE` to the reviewed B07 package if calibrated price
signals are required; without it the existing C05 producer withholds those
checks and must not be described as a full price-model evaluation.

## Proposed schedule and monitoring

Keep the original task's Sunday 03:00 Asia/Yerevan time as a **proposal** until
the owner confirms it. On a UTC host that is Saturday 23:00 UTC. After a full
successful staging run and confirmation of the execution host/timezone, an
operator can install a user crontab using absolute paths. The shell wrapper does
not load interactive shell settings; use a protected host-owned launcher to
load database/license configuration before calling it.

```cron
# Example for a UTC server, inactive until explicitly installed by the operator:
0 23 * * 6 /absolute/path/to/protected-weekly-launcher
```

No cron entry is installed or modified by this change. The launcher should
`exec bash /absolute/checkout/infra/scripts/run_weekly_ingestion.sh`; keep secrets
out of the crontab. Do not use a floating unreviewed checkout for scheduled jobs.

Raw snapshots, per-run `job.json`, latest state and logs live under
`data/raw/weekly/`. Exit codes: 0 complete success, 2 partial, 1 failure,
75 overlapping invocation. `--check` exits nonzero for a missing/failed/partial
latest run, absent complete success, future timestamp, or complete success older
than 192 hours (eight days). A recent older success cannot conceal a newer failure.
An abruptly killed host can leave `status=running`; the health check treats it
as unhealthy. Do not automatically mark unfinished database runs complete.

Connect `--check` and runner exit status to the selected host's monitoring before
activation. Neither local JSON nor cron alone is a push alert. Confirm the
existing monitoring/notification destination with the owner; no external messages
or new CloudWatch permissions are created here. Limit filesystem growth using
an agreed raw-data/log retention policy after defining evidence retention; no
automatic deletion is introduced in this PR.

## Acceptance evidence still required

- Actual Linux wrapper/browser versions, sandbox and license readiness.
- Bounded unattended source-access check and accepted field samples.
- Full manual staging run including lifecycle, API publication, analytics and signals.
- Failed run and recovery with active inventory preserved; repeated-load and price-change check.
- Confirmation of host, timezone, weekly time, monitoring destination and retention.
- Cron activation, a scheduled run, and observed failure/freshness monitoring.

Until these are recorded, keep C09 open and this PR in draft.

## Local validation (2026-11-04)

- Linux/WSL: 95 tests passed across the C09 runner and existing CLI/parser/scraper suites before the final descendant-cleanup addition.
- Final C09-specific Linux suite: 23 passed, including process-group cleanup of a child ignoring SIGTERM and flock overlap rejection.
- Disposable PostGIS 16/3.4: lifecycle integration passed, covering partial import, invalid snapshot, replay rejection and two new complete observations.
- OpenAPI/fixtures validation and `git diff --check` passed; shell syntax checked with `bash -n`.
- No live List.am requests, production database writes or cron installation were used as test evidence.
