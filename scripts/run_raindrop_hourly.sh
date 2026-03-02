#!/usr/bin/env bash
set -euo pipefail

WORKDIR="/home/hiroki-yokouchi/.openclaw/workspace"
LOGDIR="$WORKDIR/logs"
mkdir -p "$LOGDIR"

RUN_LOG="$LOGDIR/raindrop-hourly.log"
ERR_LOG="$LOGDIR/raindrop-hourly.error.log"
LOCK_FILE="$LOGDIR/raindrop-hourly.lock"

# Append logs (stdout/stderr split)
exec 1>>"$RUN_LOG"
exec 2>>"$ERR_LOG"

# Prevent overlapping runs
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[$(date '+%F %T%z')] skip: previous run still active"
  exit 0
fi

cd "$WORKDIR"

echo "[$(date '+%F %T%z')] start hourly raindrop job"

python3 scripts/raindrop_obsidian_sync.py --limit 50

TMP_OUT="$(mktemp)"
python3 scripts/raindrop_obsidian_process_pending.py | tee "$TMP_OUT"

python3 - "$TMP_OUT" <<'PY'
import subprocess, sys
from pathlib import Path

p = Path(sys.argv[1])
text = p.read_text(encoding='utf-8', errors='replace').strip()
if not text or text == 'NO_PENDING':
    print('no pending items to notify')
    raise SystemExit(0)

blocks = [b.strip() for b in text.split('---') if b.strip()]
for b in blocks:
    lines = [ln.rstrip() for ln in b.splitlines() if ln.strip()]
    title = ''
    collection = ''
    summary = []
    in_summary = False
    for ln in lines:
        if ln.startswith('TITLE:'):
            title = ln.replace('TITLE:', '', 1).strip()
            in_summary = False
        elif ln.startswith('COLLECTION:'):
            collection = ln.replace('COLLECTION:', '', 1).strip()
            in_summary = False
        elif ln.startswith('SUMMARY:'):
            in_summary = True
        elif in_summary and ln.startswith('- '):
            summary.append(ln)

    if not title:
        continue

    msg = "\n".join([
        f"タイトル: {title}",
        f"コレクション: {collection or '(不明)'}",
        "サマリー:",
        *(summary[:3] if summary else ['- (サマリーなし)'])
    ])

    try:
        subprocess.run([
            'openclaw', 'system', 'event',
            '--text', msg,
            '--mode', 'now'
        ], check=True)
        print(f'notified: {title}')
    except Exception as e:
        print(f'notify failed: {title} :: {e}')
PY

rm -f "$TMP_OUT"

echo "[$(date '+%F %T%z')] done hourly raindrop job"
