#!/usr/bin/env bash
# Linux only. Install scheduling separately after a successful manual server run.
set -euo pipefail
umask 077
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"
PYTHON="${FAIRRENT_WEEKLY_PYTHON:-$PROJECT_ROOT/.venv-weekly/bin/python}"
STATE="${FAIRRENT_WEEKLY_STATE:-$PROJECT_ROOT/data/raw/weekly}"
mkdir -p "$STATE/logs"
command -v flock >/dev/null || { echo 'flock is required' >&2; exit 1; }
[[ -x "$PYTHON" ]] || { echo 'Weekly Python environment missing' >&2; exit 1; }
exec 9>"$STATE/job.lock"
flock -n 9 || { echo 'Weekly job already active' >&2; exit 75; }
LOG="$STATE/logs/$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
echo "Weekly ingestion log: $LOG"
exec "$PYTHON" -m data_pipeline.weekly_job --state-dir "$STATE" \
  --max-pages "${FAIRRENT_WEEKLY_MAX_PAGES:-50}" \
  --details-limit "${FAIRRENT_WEEKLY_DETAILS_LIMIT:-2000}" \
  --delay "${FAIRRENT_WEEKLY_DELAY:-3}" \
  --timeout "${FAIRRENT_WEEKLY_TIMEOUT:-14400}" >"$LOG" 2>&1
