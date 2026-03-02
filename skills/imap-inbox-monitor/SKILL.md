---
name: imap-inbox-monitor
description: Monitor IMAP inbox incrementally for new mail only, store per-mail summaries, and report actionable items in chat. Use when the user wants a recurring or on-demand mail check workflow that (1) fetches only messages newer than the previous run, (2) remembers summaries, and (3) alerts on emails likely needing response.
---

# IMAP Inbox Monitor

Run incremental, read-only IMAP checks using the bundled script.

## What this skill does

- Load prior state (`last_seen_uid`)
- Fetch only messages newer than that UID
- Save summary memory for each new message
- Classify actionable messages
- Print a chat-ready report

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
```

Optional flags:

```bash
python3 scripts/imap_monitor.py run --limit 100 --state-file ./state/imap_state.json --memory-file ../../memory/imap-mail-summaries.jsonl
```

## Expected behavior

- First run: initialize state and process up to `--limit` newest messages.
- Next runs: process only UIDs greater than previous `last_seen_uid`.
- Output includes:
  - `new_count`
  - `actionable_count`
  - message list for actionable items

## Reporting in chat

After running the script, share only:
- No new mail → short "新着なし" message
- New actionable mail → sender + subject + one-line reason
- Non-actionable new mail exists → mention count briefly

Keep this skill read-only. Never send email.
