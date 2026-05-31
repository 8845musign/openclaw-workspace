---
name: js-ts-trend-radar
description: Collect daily JavaScript/TypeScript trend signals with LLM-driven research, then save a strict JSON artifact for downstream publishing. Use when the daily JS/TS trend cron fires or when the user asks for a fresh JS/TS trend scout.
---

# JS/TS Trend Radar

This skill is collection-only.

Do not send Slack messages.
Do not create article capture files.
Do not create prose digests in chat.

Your job is to research current JS/TS signals and save exactly one JSON artifact for the publish step.

## Fixed Sources

Prioritize these buckets, but do not fail if some are unavailable.

- Design / architecture
  - https://martinfowler.com/
  - https://www.thoughtworks.com/radar
  - https://www.infoq.com/
  - Engineering blogs from Vercel / Shopify / Stripe / Airbnb
- Libraries / tools
  - GitHub Trending (TypeScript)
  - https://github.com/trending/typescript?since=daily
  - npm trends / npm weekly top packages
  - JavaScript Weekly / TypeScript Weekly
- Community / practitioner signals
  - Hacker News
  - Reddit: r/typescript, r/javascript, r/webdev
  - YouTube / conference material around TSConf, NodeConf, React

## Selection Rules

Prioritize practical signal over hype.

For each candidate, score with these checks:

1. Recency
2. Maintainer and issue/PR activity
3. Dependency health and release discipline
4. Breaking-change frequency and migration burden
5. Real-world applicability

Never rank by stars alone.

## Freshness Guard

Recency is strict.

- Strongly prefer sources published within the last 30 days.
- Prefer sources published within the last 14 days when enough good candidates exist.
- Do not select year-in-review, predictions, or retrospective pieces about 2025 unless they were published very recently and are directly tied to a concrete 2026 release, announcement, or migration decision.
- Do not describe a 2025 ecosystem summary as if it were today's trend.
- If the available sources are mostly old, return fewer items and set `status` to `partial` or `fallback` instead of padding with stale content.
- In `coverage_notes`, explicitly mention when freshness constraints prevented selecting more items.
- In `why_new`, anchor the novelty to the source publish date or the concrete newly announced change, not to an older background trend.

## Research Execution Guard

In cron runs, assume `web_search` is available unless a tool call proves otherwise.

- Before writing any `partial` or `fallback` artifact, you must attempt live research with at least 3 `web_search` calls that target different buckets.
- Do not claim "time constraints", "execution constraints", or "web search not performed" unless you actually attempted the relevant tool call and it failed or returned unusable results.
- Do not generate dummy, placeholder, or synthetic trend items.
- If live research fails, record the concrete failed queries or tool errors in `coverage_notes`.
- A `partial` artifact is acceptable with 1-2 strong fresh items.
- An empty `items` array is allowed only if live searches were attempted and freshness filtering removed everything.

## Output Contract

Save the artifact under:

- `/home/hiroki-yokouchi/.openclaw/workspace/memory/js-ts-trend/YYYY-MM-DD.json`

Use the current date in `Asia/Tokyo`.

If today's artifact already exists, do not recollect. Inspect it briefly and return a short status line only.

If you create or update today's artifact, the file content must be valid JSON with this exact top-level shape:

```json
{
  "date": "YYYY-MM-DD",
  "generated_at": "ISO-8601 string",
  "status": "ok | partial | fallback",
  "coverage_notes": [
    "string"
  ],
  "tl_dr": [
    "string",
    "string",
    "string"
  ],
  "items": [
    {
      "bucket": "design | library | signal",
      "title": "string",
      "url": "string",
      "source_kind": "string",
      "why_new": "string",
      "why_important": "string"
    }
  ],

}
```

## Required Behavior

- `tl_dr` should contain at most 3 short Japanese bullets.
- `items` should normally contain 3-6 entries.
- `coverage_notes` should mention missing or weakly covered sources when relevant.
- `deep_dive` should point to one of the selected items whenever possible.
- Avoid repeating the same topic for 7 days unless there is a substantial update.
- If there are not enough strong signals, return fewer items instead of padding with weak ones.
- If collection is weak or partially blocked, still write a valid JSON artifact with `status: "partial"` or `status: "fallback"`.
- Before finalizing, sanity-check every selected item for freshness and remove anything that is obviously stale for today's digest.

## Final Reply

Reply with exactly one plain-text status line and nothing else.

Hard requirements:

- Do not acknowledge the request.
- Do not explain what you are about to do.
- Do not use persona, roleplay, emojis, or conversational filler.
- Do not emit `<think>`, `<final>`, markdown, bullets, or code fences.
- Do not output any text before or after the status line.
- The entire final response must be a single line matching one of these patterns:
  - `collect ok: N items saved to memory/js-ts-trend/YYYY-MM-DD.json`
  - `collect partial: N items saved to memory/js-ts-trend/YYYY-MM-DD.json`
  - `collect fallback: N items saved to memory/js-ts-trend/YYYY-MM-DD.json`
  - `collect skipped: existing artifact for YYYY-MM-DD`

Examples:

- `collect ok: 4 items saved to memory/js-ts-trend/2026-04-08.json`
- `collect partial: 2 items saved to memory/js-ts-trend/2026-04-08.json`
- `collect skipped: existing artifact for 2026-04-08`
