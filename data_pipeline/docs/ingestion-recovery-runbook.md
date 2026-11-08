# Ingestion recovery runbook (A08)

## Purpose and safety

Use this runbook to reproduce an initial import, an idempotent repeat, a price change,
a failed run, and recovery. The checked-in records are synthetic and use
`example.invalid`; they are suitable for a disposable local or staging database.
Do not load them into production. The commands use the isolated `recovery-demo`
source name so their inventory and staleness policy are separate from `list.am`.

No database schema change is required. The existing `ingestion_runs`, `listings`,
`properties`, and `price_observations` tables contain the fields needed for this demo.

Geographic data uses separate identifiers: the expanded published point registry is
`yerevan-reference-v2`; listing proximity outputs remain `yerevan-geo-v1` and continue
to use the original four campus points. `enrich_geography` reports both identifiers
and cleans stale reference points against the registry version.

## Reproduce the database sequence

From the repository root, configure `DATABASE_URL` for a disposable PostgreSQL
database that has the project migrations applied. Do not paste credentials into a
committed file.

PowerShell example (replace the placeholder with a local test database URL):

```powershell
$env:DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@localhost:5432/fairrent_test"
python -m data_pipeline.cli import-file data_pipeline/recovery_demo_initial.json --source-name recovery-demo
python -m data_pipeline.cli import-file data_pipeline/recovery_demo_initial.json --source-name recovery-demo
python -m data_pipeline.cli import-file data_pipeline/recovery_demo_price_change.json --source-name recovery-demo
```

Expected result:

1. The first import creates two listings and two price observations.
2. The repeated import updates last-seen metadata without adding listings or price observations.
3. The changed snapshot updates `RUNBOOK-001` from USD 700 to USD 725 and adds one price observation.
4. `RUNBOOK-002` remains stored with unknown coordinates recorded in `raw_data.missing_fields`.

Imports are non-crawls, so `is_complete` is false and no inventory is deactivated.
Keep the database disposable: the fixture rows remain after the commands finish.
These three manual import commands create successful run records only; they do not
create the failed-run/recovery sequence shown in the audit queries below.

## Reproduce failure and recovery

The PostgreSQL integration test exercises the same fixture sequence and inserts a
synthetic failed run between the changed snapshot and its recovery import. It verifies
that the failed run deactivates nothing, the next successful import updates
`last_seen_run_id`, and listing/price-history counts remain stable. Its fixture drops
its tables at teardown, so its records are not available to inspect afterward.

To persist and inspect all five runs, use the standalone command against a migrated,
disposable database whose database name contains a separate `test` or `demo` token.
The command refuses to run against other database names. It prints each run ID and
retains the listings, price observations, and ingestion-run audit rows:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@localhost:5432/fairrent_test"
py -3.14 -m data_pipeline.cli demo-recovery
```

The command is safe to repeat for listing and price idempotency, but each invocation
adds five more ingestion-run audit rows. Use the printed IDs to scope the queries below
to one invocation. A fresh disposable database gives the cleanest audit output.

Create a dedicated test database whose database name contains `test`, install PostGIS,
and set `TEST_DATABASE_URL` to it. The test fixture refuses to run if the database name
does not contain `test` and rebuilds its tables, so never point this setting at a shared
or production database.

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@localhost:5432/fairrent_test"
python -m pytest data_pipeline/test_loader_postgres.py -k recovery_demo_initial_repeat_price_change_and_failed_run -v
```

To rerun the complete acceptance coverage for recovery, blocked collections, and
incomplete records:

```powershell
python -m pytest data_pipeline/test_loader_postgres.py -k "recovery_demo or blocked_page_two or collection_failure or without_coordinates" -v
```

The wider ingestion regression coverage can be rerun with:

```powershell
python -m pytest data_pipeline/test_scraper.py data_pipeline/test_cli.py data_pipeline/test_loader_postgres.py -v
```

PostgreSQL tests are skipped when `TEST_DATABASE_URL` is unset. For the CI-equivalent
project run, use `python -m pytest backend/tests data_pipeline ml/tests -v` from the
repository root.

## Inspect the resulting audit trail

Run these read-only queries in `psql` connected to the disposable demo database:

```sql
SELECT id, source, status, is_complete, listings_seen, listings_saved,
       listings_quarantined, listings_deactivated, notes
FROM ingestion_runs
WHERE source = 'recovery-demo'
  AND id BETWEEN 1 AND 5 -- replace with initial and recovery run IDs from command output
ORDER BY id;

SELECT external_id, original_price, original_currency, is_active,
       first_seen_at, last_seen_at, last_seen_run_id,
       raw_data::jsonb -> 'missing_fields' AS missing_fields
FROM listings
WHERE source = 'recovery-demo'
ORDER BY external_id;

SELECT l.external_id, o.original_price, o.original_currency, o.run_id, o.recorded_at
FROM price_observations AS o
JOIN listings AS l ON l.id = o.listing_id
WHERE l.source = 'recovery-demo'
ORDER BY l.external_id, o.recorded_at, o.id;
```

The run query is scoped to the five IDs printed by one `demo-recovery` invocation.
The listing and price-history queries show the retained state for the entire
`recovery-demo` source; run them on a fresh disposable database to avoid mixing prior
manual imports or earlier demo invocations.

The audit should show the failed run, followed by a successful recovery. The changed
listing has two price observations (700 and 725); the unchanged listing has one.
The incomplete-coordinate record stays queryable and shows `coordinates` in
`missing_fields`.

## Production collection limits and recovery steps

The configured source is the List.am Yerevan rental category. Its selectors, page
parameter, and end-of-catalogue markup are documented assumptions; the parser has been
verified against project-owned mock pages, not the live site. Check the current site
markup, robots.txt, and terms before enabling scheduled collection. See
[`source-analysis.md`](source-analysis.md) for field mappings and assumptions.

The collector identifies itself as `FairRentBot/1.0`, waits one second between
requests by default, and retries network failures, HTTP 429, and HTTP 5xx up to three
times with exponential backoff. It does not retry other HTTP 4xx responses. A CAPTCHA,
blocked page, unrecognized page layout, early page cap, or failed index page marks a
crawl incomplete. Incomplete and failed crawls do not evaluate staleness. Only a
verified complete crawl can add a miss, and the default policy deactivates a listing
after two complete misses. Rows are retained; a later observation reactivates them.

For a first connectivity/markup probe after source approval, use a small capped crawl:

```powershell
python -m data_pipeline.cli run --pages 2 --max-listings 10 --delay 1
```

This is intentionally a partial crawl and cannot deactivate inventory. Review its run
summary and quarantines. If it is blocked or the layout has changed, stop collection,
inspect `ingestion_runs.notes` and the application logs, update the source parser only
after confirming the current markup, then retry with the same source name. Do not
lower the seen-ratio or staleness safeguards to force a run to complete. For an outage,
fix the source/database problem and rerun; idempotency prevents duplicate listings and
duplicate price observations when the observed price is unchanged.

Per-item quarantine details are held in the collector's run log; the database run row
stores the quarantine count. Accepted incomplete records remain traceable through
`raw_data.missing_fields`, source identity, and last-seen run metadata.
