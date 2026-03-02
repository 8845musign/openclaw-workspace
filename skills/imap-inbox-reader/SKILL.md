---
name: imap-inbox-reader
description: Read-only IMAP inbox access for fetching newest emails and searching existing emails without sending. Use when the user asks to connect an IMAP account and needs only (1) latest message retrieval or (2) inbox search by keyword/from/subject/date.
---

# IMAP Inbox Reader

Implement read-only IMAP workflows via the bundled script.

## Use the bundled script

Run `scripts/imap_reader.py` for both supported actions:

- Latest messages: fetch newest N messages from INBOX
- Search messages: run IMAP search criteria and return parsed headers/snippets

## Configure credentials safely

Prefer environment variables over command-line secrets.

Required:
- `IMAP_HOST`
- `IMAP_USER`
- `IMAP_PASS`

Optional:
- `IMAP_PORT` (default: `993`)
- `IMAP_MAILBOX` (default: `INBOX`)
- `IMAP_TLS` (`true` by default)

## Command patterns

### Get latest N

```bash
IMAP_HOST=... IMAP_USER=... IMAP_PASS=... \
python3 scripts/imap_reader.py latest --limit 10
```

### Search by free text (subject/from/body)

```bash
IMAP_HOST=... IMAP_USER=... IMAP_PASS=... \
python3 scripts/imap_reader.py search --text "invoice" --limit 20
```

### Search by sender and date

```bash
IMAP_HOST=... IMAP_USER=... IMAP_PASS=... \
python3 scripts/imap_reader.py search --from "billing@example.com" --since 2026-03-01 --limit 20
```

### Raw IMAP criteria (advanced)

```bash
IMAP_HOST=... IMAP_USER=... IMAP_PASS=... \
python3 scripts/imap_reader.py search --criteria '(UNSEEN SINCE "01-Mar-2026")'
```

## Output

Script returns JSON with:
- `mailbox`
- `count`
- `messages[]`
  - `uid`
  - `date`
  - `from`
  - `to`
  - `subject`
  - `snippet`

Keep this skill read-only. Do not implement SMTP/send behavior.
