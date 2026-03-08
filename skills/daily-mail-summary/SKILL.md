---
name: daily-mail-summary
description: Fetch today's emails via IMAP and deliver a concise daily summary to Slack. Use when the cron job fires at 20:00 JST daily, or when the user asks for today's mail summary on demand. Categorizes each email (important / notification / promo) and formats with emoji bullets.
---

# Daily Mail Summary

Fetch today's emails and deliver a formatted summary to the user's Slack DM.

## Workflow

1. Run `scripts/fetch_today.sh` to get today's emails as JSON.
2. Parse the JSON output and categorize each email:
   - 🔴 **重要** — personal messages, auth/security alerts, replies to user's emails
   - 🔔 **通知** — service notifications, updates, shipping alerts
   - 📢 **プロモ** — newsletters, marketing, ads
3. Format as a Slack-friendly bullet list with emoji per category, sender name, subject, and one-line snippet summary in Japanese.
4. If no emails: report "今日はメールなかったにゃ 💤"
5. Deliver via `sessions_send` to the user's Slack DM session.

## Output format

```
📬 今日のメールまとめ（N通）

🔴 **Sender** — Subject の要約
🔔 **Sender** — Subject の要約
📢 **Sender** — Subject の要約

（だいふくが分類したにゃ 🐱）
```

## Script

`scripts/fetch_today.sh` uses the imap-inbox-reader script with SINCE criteria for today's date. Credentials come from `.env.imap` in the workspace root.

## Cron

Scheduled daily at 20:00 JST. Cron task prompt should invoke this skill by name.
