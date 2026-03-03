# HEARTBEAT.md

## Goal
Keep lightweight context from recent chat/mail/calendar, and notify only when valuable.

## On each heartbeat
1. Load or create `state/heartbeat-context.json`.
2. Read `MEMORY.md` if it exists and use it as long-term context (preferences, ongoing priorities, constraints). Do not overwrite it during heartbeat.
3. Collect recent context:
   - Chat: summarize recent OpenClaw conversation deltas since `last_chat_cursor`.
   - Mail: run incremental IMAP check (new only) and capture actionable summaries.
   - Calendar: read ICS sources and capture newly added/updated upcoming events.
4. Append normalized events to `memory/heartbeat-log.jsonl` with fields:
   - `ts`, `source` (`chat|mail|calendar`), `summary`, `importance` (`low|med|high`), `action_needed` (bool)
5. Update state cursors/hash:
   - `last_checked_at`, `last_chat_cursor`, `last_mail_uid`, `last_calendar_hash`

## Notify policy
- If any event is `importance=high` or `action_needed=true`: notify immediately with concise bullets.
- Else if there are `med` events and last digest was >12h ago: send one short digest.
- Else: reply `HEARTBEAT_OK`.

## Quiet hours
- Between 23:00-08:00 JST, only notify for high/action-needed items.

## Style
- Keep notifications short, concrete, and non-spammy.
- Mention why it matters (deadline, reply-needed, soon event, etc.).
