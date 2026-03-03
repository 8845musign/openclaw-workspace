#!/usr/bin/env bash
set -euo pipefail

WORKDIR="/home/hiroki-yokouchi/.openclaw/workspace"
OPENCLAW_BIN="/home/hiroki-yokouchi/.local/share/mise/installs/node/24.13.1/bin/openclaw"
LOGDIR="$WORKDIR/logs"
mkdir -p "$LOGDIR"

OUT_LOG="$LOGDIR/daily-error-review.log"
ERR_LOG="$LOGDIR/daily-error-review.error.log"

exec 1>>"$OUT_LOG"
exec 2>>"$ERR_LOG"

DATE_KEY="$(date '+%Y-%m-%d')"

echo "[$(date '+%F %T%z')] start daily error review"

if [[ ! -x "$OPENCLAW_BIN" ]]; then
  echo "[$(date '+%F %T%z')] error: openclaw binary not executable at $OPENCLAW_BIN"
  exit 1
fi

python3 - "$LOGDIR" "$DATE_KEY" "$OPENCLAW_BIN" <<'PY'
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

logdir = Path(sys.argv[1])
date_key = sys.argv[2]
openclaw_bin = sys.argv[3]

error_files = sorted([p for p in logdir.glob('*.error.log') if p.is_file()])
if not error_files:
    print('NO_ERROR_LOG_FILES')
    raise SystemExit(0)

line_total = 0
by_file = {}
sig_counter = Counter()
samples = defaultdict(list)

for f in error_files:
    lines = []
    for ln in f.read_text(encoding='utf-8', errors='replace').splitlines():
        if date_key in ln or True:
            # fallback: include all lines if no date prefix in logs
            lines.append(ln)
    # Prefer lines that contain explicit errors
    filtered = [ln for ln in lines if re.search(r'(error|traceback|exception|failed)', ln, re.I)]
    if not filtered:
        continue
    by_file[f.name] = len(filtered)
    line_total += len(filtered)
    for ln in filtered:
        sig = re.sub(r'\d+', '<n>', ln.strip())
        sig = re.sub(r'\s+', ' ', sig)
        sig_counter[sig] += 1
        if len(samples[sig]) < 1:
            samples[sig].append(ln.strip())

if line_total == 0:
    print('NO_ERRORS_TODAY')
    raise SystemExit(0)

top = sig_counter.most_common(5)

msg_lines = []
msg_lines.append(f"【日次エラーレビュー {date_key}】")
msg_lines.append(f"総エラー行数: {line_total}")
msg_lines.append("ファイル別:")
for k,v in sorted(by_file.items(), key=lambda x: x[1], reverse=True)[:8]:
    msg_lines.append(f"- {k}: {v}")
msg_lines.append("再発上位:")
for i,(sig,cnt) in enumerate(top,1):
    sample = samples[sig][0] if samples[sig] else sig
    if len(sample) > 140:
        sample = sample[:140] + '…'
    msg_lines.append(f"{i}. x{cnt} {sample}")

msg_lines.append("次アクション:")
msg_lines.append("- この内容を基にLLMで根本原因と修正案（優先度付き）を作成")
msg_lines.append("- 明日再発有無を確認")

msg = "\n".join(msg_lines)
prompt = (
    "[DAILY_ERROR_REVIEW_REQUEST]\n"
    "Use skill: daily-error-review-llm\n"
    "次のエラー要約から、優先度付きの修正案を作成してください。\n\n"
    + msg
)
print(prompt)

# notify chat via openclaw system event
import subprocess
subprocess.run([
    openclaw_bin,'system','event','--text',prompt,'--mode','now'
], check=False)

# save JSON report
report = {
    'date': date_key,
    'line_total': line_total,
    'by_file': by_file,
    'top_signatures': [{
        'count': c,
        'sample': samples[s][0] if samples[s] else s
    } for s,c in top]
}
report_path = logdir / f'daily-error-review-{date_key}.json'
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f'REPORT_SAVED {report_path}')
PY

echo "[$(date '+%F %T%z')] done daily error review"