# HEARTBEAT.md

## Goal
直近の活動（チャット/メール/カレンダー）を軽く把握し、価値があるときだけ短く通知する。  
追加で、活動に関連するWeb情報を1〜3件だけレコメンドする。

## On each heartbeat
1. Load or create `state/heartbeat-context.json`.
2. Read `MEMORY.md` if it exists and use it as long-term context (preferences, ongoing priorities, constraints). Do not overwrite it during heartbeat.
3. Collect recent context:
   - Chat: summarize recent OpenClaw conversation deltas since `last_chat_cursor`.
   - Mail: run incremental IMAP check (new only) and capture actionable summaries.
   - Calendar: read ICS sources and capture newly added/updated upcoming events.
4. Pick 1〜3 topical keywords from the recent deltas (new tasks, tools, topics discussed).
5. Run lightweight web search using those keywords and keep only high-signal results:
   - practical how-to, official docs, strong explainers, relevant news
   - skip low-quality/duplicate/obviously irrelevant links
6. Append normalized events to `memory/heartbeat-log.jsonl` with fields:
   - `ts`, `source` (`chat|mail|calendar|web`), `summary`, `importance` (`low|med|high`), `action_needed` (bool)
7. Update state cursors/hash:
   - `last_checked_at`, `last_chat_cursor`, `last_mail_uid`, `last_calendar_hash`, `last_digest_at`

## Notify policy
- If any event is `importance=high` or `action_needed=true`: notify immediately with concise bullets.
- Else if useful web recommendations exist: send up to 3 bullet recommendations (title + one-line why + URL).
- Else if there are `med` events and last digest was >12h ago: send one short digest.
- Else: 猫の近況を1行つぶやく（軽いひとこと）。
- **Always-send rule:** 上記のどの分岐でも、heartbeat実行ごとに必ず最低1メッセージを送る（`HEARTBEAT_OK`のみで終了しない）。

## Delivery
- webchatでの返答も通常通り行う（両方に届ける）。

## Quiet hours
- Between 23:00-08:00 JST, high/action-needed itemsを優先。
- ただし Always-send rule を優先し、quiet hoursでも最低1行の短い近況は送る（通知を完全に止めない）。

## Style
- Keep notifications short, concrete, and non-spammy.
- Mention why it matters (deadline, reply-needed, soon event, etc.).
- 猫つぶやきは自然に短く（1行）、重くしない。
