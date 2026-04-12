#!/usr/bin/env bash
set -euo pipefail

WORKDIR="/home/hiroki-yokouchi/.openclaw/workspace"
NODE_BIN_DIR="/home/hiroki-yokouchi/.local/share/mise/installs/node/24.13.1/bin"
OPENCLAW_BIN="/home/hiroki-yokouchi/.local/share/mise/installs/node/24.13.1/bin/openclaw"
LOGDIR="$WORKDIR/logs"
mkdir -p "$LOGDIR"

RUN_LOG="$LOGDIR/js-ts-trend-publish.log"
ERR_LOG="$LOGDIR/js-ts-trend-publish.error.log"
LOCK_FILE="$LOGDIR/js-ts-trend-publish.lock"

exec 1>>"$RUN_LOG"
exec 2>>"$ERR_LOG"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[$(date '+%F %T%z')] skip: previous publish run still active"
  exit 0
fi

cd "$WORKDIR"
export PATH="$NODE_BIN_DIR:$PATH"
export OPENCLAW_BIN

echo "[$(date '+%F %T%z')] start js/ts trend publish"
python3 scripts/publish_js_ts_trend.py
echo "[$(date '+%F %T%z')] done js/ts trend publish"
