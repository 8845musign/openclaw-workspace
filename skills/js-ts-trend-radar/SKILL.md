---
name: js-ts-trend-radar
description: Discover broad JavaScript/TypeScript trends and deliver a daily practical digest covering architecture discussions, new libraries, and community signals (not only official release notes). Use when the user asks for recurring JS/TS trend scouting, daily digests, source curation, and saving translated full articles to Obsidian.
---

# JS/TS Trend Radar

Produce a concise daily digest and archive source articles in Japanese in Obsidian.

## Fixed Sources

Scan these buckets every run.

- 設計論（実戦）
  - https://martinfowler.com/
  - https://www.thoughtworks.com/radar
  - https://www.infoq.com/
  - Engineering blogs from Vercel / Shopify / Stripe / Airbnb
- 新ライブラリ発見
  - GitHub Trending (TypeScript)
  - npm trends / npm weekly top packages
  - JavaScript Weekly / TypeScript Weekly
- 現場の温度感
  - Hacker News
  - Reddit: r/typescript, r/javascript, r/webdev
  - YouTube / conference materials around TSConf, NodeConf, React

## Selection Rules

Prioritize practical signal over hype.

For each candidate, score with these checks:

1. Recency (updated recently)
2. Maintainer and issue/PR activity
3. Dependency health and release discipline
4. Breaking-change frequency and migration burden
5. Real-world applicability

Never rank by stars alone.

## Output (chat)

Return this structure in Japanese:

1. TL;DR (max 3 bullets)
2. 注目トピック（設計論 / ライブラリ / 現場）
3. 各項目: 何が新しいか / なぜ重要か / URL
4. 今日の深掘り1本

Keep it short and useful for a weekday morning read.

## Obsidian Archival

Save under this vault unless the user overrides it:

- Vault root: `~/ドキュメント/openclaw`
- Digest note: `tech-digest/YYYY-MM-DD-js-ts.md`
- Full article captures: `articles/YYYY-MM-DD-<slug>-ja.md`

For each selected item:

1. Fetch article text.
2. If full text is accessible and allowed, create full Japanese translation preserving headings/lists/code blocks.
3. If full capture is unavailable (paywall, blocked, extraction failure), save a fallback note with:
   - reason
   - source URL
   - concise Japanese summary
4. Include frontmatter fields in saved notes:
   - `source_url`
   - `title`
   - `captured_at`
   - `type` (`trend-digest` or `article-ja` or `article-fallback`)
   - `tags` (`javascript`, `typescript`, `trend`)

## De-duplication

Avoid repeating the same topic for 7 days unless there is a substantial update.

## Failure Handling

If some sources fail, continue with remaining sources and mention partial coverage briefly.