---
name: daily-cron-improvement-suggester
description: Analyze the same-day cron execution results and propose concrete improvements without applying changes. Use when running a daily retrospective for cron operations (delivery quality, noise, errors, duplication, timing, rate-limit handling), and when the user asks for actionable tuning ideas only.
---

# Daily Cron Improvement Suggester

## Overview
Read same-day cron outcomes, find reliability/noise/value issues, and output prioritized improvement proposals.
Do not auto-edit cron jobs or code in this skill; propose changes only.

## Workflow
1. Collect today’s cron evidence.
   - Prefer runtime completion messages from today.
   - If needed, read local logs/state files used by those jobs.
2. Cluster findings by problem type.
   - delivery miss / timeout
   - noisy duplicate notifications
   - weak signal quality (too generic, low value)
   - false positive urgency
   - schedule mismatch (too frequent/too sparse)
   - rate limit / transient API failure
3. Score each candidate fix.
   - Impact: user value if fixed (high/med/low)
   - Risk: chance of regression (high/med/low)
   - Effort: S/M/L
4. Produce proposals only.
   - Include exact target (job name/id, file, field) and expected effect.
   - Avoid broad vague advice.

## Output Format
Return in Japanese with this structure:

- 今日の所見（3-6 bullets）
- 改善提案（最大5件、優先順）
  - `対象:`
  - `変更案:`
  - `期待効果:`
  - `リスク:`
  - `実施コスト:` S/M/L
- 明日まずやる1手（1行）

## Guardrails
- Do not claim changes were applied.
- Do not include secrets/tokens/PII.
- Prefer fewer, high-signal proposals over long lists.
- If evidence is insufficient, state missing evidence and still provide the best low-risk proposal set.
