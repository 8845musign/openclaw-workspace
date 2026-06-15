#!/usr/bin/env bash
set -euo pipefail

WORKDIR="/home/hiroki-yokouchi/.openclaw/workspace"
NODE_BIN_DIR="/home/hiroki-yokouchi/.local/share/mise/installs/node/24.13.1/bin"
OPENCLAW_BIN="/home/hiroki-yokouchi/.local/share/mise/installs/node/24.13.1/bin/openclaw"
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
  echo "[$(date '+%F %T%z')] skip: previous pdf digest run still active"
  exit 0
fi

cd "$WORKDIR"
export PATH="$NODE_BIN_DIR:$PATH"
export OPENCLAW_BIN

echo "[$(date '+%F %T%z')] start pdf digest daily"
"$PYTHON_BIN" scripts/pdf_digest.py daily
echo "[$(date '+%F %T%z')] done pdf digest daily"
