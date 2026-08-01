#!/usr/bin/env bash
set -euo pipefail

WORKDIR="/home/hiroki-yokouchi/.openclaw/workspace"
SCRIPT_DIR="$WORKDIR/skills/pdf-digest/scripts"
PYTHON_BIN="$WORKDIR/.venv/bin/python"
LOGDIR="$WORKDIR/logs"
mkdir -p "$LOGDIR"

RUN_LOG="$LOGDIR/pdf-digest-daily.log"
ERR_LOG="$LOGDIR/pdf-digest-daily.error.log"
LOCK_FILE="$LOGDIR/pdf-digest-daily.lock"

exec 1>>"$RUN_LOG"
exec 2>>"$ERR_LOG"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[$(date '+%F %T%z')] error: previous pdf digest run is still active"
  exit 75
fi

cd "$WORKDIR"
OPENCLAW_BIN="$(command -v openclaw || true)"
if [[ -z "$OPENCLAW_BIN" || ! -x "$OPENCLAW_BIN" ]]; then
  echo "[$(date '+%F %T%z')] error: openclaw executable was not found on PATH"
  exit 127
fi
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "[$(date '+%F %T%z')] error: Python executable is unavailable: $PYTHON_BIN"
  exit 127
fi
export OPENCLAW_BIN

echo "[$(date '+%F %T%z')] start pdf digest daily (openclaw=$OPENCLAW_BIN)"
"$PYTHON_BIN" "$SCRIPT_DIR/pdf_digest.py" daily "$@"
echo "[$(date '+%F %T%z')] done pdf digest daily"
