---
name: daily-error-review-llm
description: Analyze daily cron/script error logs and propose prioritized fixes. Use when receiving a daily error summary/report (counts, recurring signatures, sample stack traces) and the user wants concrete remediation actions.
---

# Daily Error Review (LLM)

Use this skill to convert daily error summaries into actionable fixes.

## Input

Expect one of:
- A JSON report path (e.g., `logs/daily-error-review-YYYY-MM-DD.json`)
- Inline summary text with:
  - total error count
  - per-file counts
  - top recurring signatures/samples

## Workflow

1. Read the report file if a path is provided.
2. Identify top 3 recurring error groups by impact (`count`, affected job, user impact).
3. For each top group, output:
   - probable root cause (1–2 bullets)
   - concrete fix plan (code/config/ops)
   - validation steps (what to rerun/check next day)
   - risk level (`low|medium|high`)
4. Add a short “tonight patch order” list (priority order).

## Output format

Use exactly these sections:

- `## 今日の診断`
- `## 修正案（優先度順）`
- `## 今夜やるパッチ順`
- `## 明日の確認項目`

Keep it concise and implementation-oriented. Avoid generic advice.
