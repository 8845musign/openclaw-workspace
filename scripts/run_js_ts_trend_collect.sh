#!/usr/bin/env bash
set -euo pipefail

WORKDIR="/home/hiroki-yokouchi/.openclaw/workspace"
OPENCLAW_BIN="$(command -v openclaw || true)"
if [[ -z "$OPENCLAW_BIN" ]]; then
  echo "openclaw executable was not found on PATH" >&2
  exit 1
fi
NODE_BIN_DIR="$(dirname "$OPENCLAW_BIN")"
LOGDIR="$WORKDIR/logs"
mkdir -p "$LOGDIR"

RUN_LOG="$LOGDIR/js-ts-trend-collect.log"
ERR_LOG="$LOGDIR/js-ts-trend-collect.error.log"
LOCK_FILE="$LOGDIR/js-ts-trend-collect.lock"

exec 1>>"$RUN_LOG"
exec 2>>"$ERR_LOG"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[$(date '+%F %T%z')] skip: previous collect run still active"
  exit 0
fi

cd "$WORKDIR"
export PATH="$NODE_BIN_DIR:$PATH"
export OPENCLAW_BIN

echo "[$(date '+%F %T%z')] start js/ts trend collect"
python3 scripts/collect_js_ts_trend.py "$@"
echo "[$(date '+%F %T%z')] done js/ts trend collect"
