---
name: imap-inbox-monitor
description: Monitor IMAP inbox incrementally for new mail only, store per-mail summaries, and return all newly arrived messages in a chat-ready JSON shape. Use when the user wants a recurring or on-demand mail check workflow that (1) fetches only messages newer than the previous run and (2) remembers summaries for downstream processing.
---

# IMAP Inbox Monitor

Run incremental, read-only IMAP checks using the bundled script.

## What this skill does

- Load prior state (`last_seen_uid`)
- Fetch only messages newer than that UID
- Save summary memory for each new message
- Return all new messages in a stable JSON shape

## Required environment variables

- `IMAP_HOST`
- `IMAP_USER`
- `IMAP_PASS`

Optional:
- `IMAP_PORT` (default `993`)
- `IMAP_MAILBOX` (default `INBOX`)
- `IMAP_TLS` (default `true`)

## Run

```bash
set -a; source ~/.openclaw/.env; set +a
python3 scripts/imap_monitor.py run
# default paths:
# --state-file  /home/hiroki-yokouchi/.openclaw/workspace/state/imap_state.json
# --memory-file /home/hiroki-yokouchi/.openclaw/workspace/memory/imap-mail-summaries.jsonl
```

Optional flags:

```bash
python3 scripts/imap_monitor.py run --limit 100 --state-file /home/hiroki-yokouchi/.openclaw/workspace/state/imap_state.json --memory-file /home/hiroki-yokouchi/.openclaw/workspace/memory/imap-mail-summaries.jsonl
```

## Expected behavior

- First run: initialize state and process up to `--limit` newest messages.
- Next runs: process only UIDs greater than previous `last_seen_uid`.
- Output includes:
  - `new_count`
  - `messages`
  - each message has `uid`, `date`, `from`, `to`, `subject`, `snippet`

## Reporting in chat

After running the script, share only:
- No new mail → short "新着なし" message
- New mail exists → sender + subject を列挙するか、件数を短くまとめる

Keep this skill read-only. Never send email.
