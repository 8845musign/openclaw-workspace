---
name: obsidian-article-capture
description: Capture a web article from a URL into an Obsidian vault as Japanese notes. Use when the user asks to save/summarize/translate an article into Obsidian, especially with files under vault/articles and date-prefixed filenames.
---

# Obsidian Article Capture

Accept a URL, fetch article text, and create Markdown files in `articles/` inside the target Obsidian vault.

## Workflow

1. Confirm the vault path and ensure `articles/` exists.
   - If unknown, ask once for vault path.
   - Default for this environment can be `~/ドキュメント/openclaw` when confirmed by user.
2. Fetch readable content from the URL using `web_fetch` (`extractMode: markdown`).
3. Derive article title.
   - Prefer page title from fetched content.
   - Sanitize title for filenames: remove `/\\:*?"<>|`, collapse spaces to `-`.
4. Build date prefix with local date: `YYYY-MM-DD`.
5. Always create Japanese summary file:
   - `YYYY-MM-DD-{article-title}-sumary.md`
   - Content sections:
     - `# 要約`
     - `## 3行サマリー`
     - `## 重要ポイント`
     - `## 次に読むべき人`
     - `## 元URL`
6. If source article is mainly English, also create translation file:
   - `YYYY-MM-DD-{article-title}-ja.md`
   - Translate naturally into Japanese (not literal word-by-word).
   - Preserve headings/lists/code blocks.
   - Start with `> Source: {URL}`.
7. Write files under `{vault}/articles/`.
8. Report created filenames and paths to the user.

## Quality Rules

- Keep Japanese clear and concise.
- Do not invent facts not present in the article.
- If fetch is truncated, state that summary/translation is partial.
- If article is paywalled or unreadable, report failure and ask for pasted text.

## Output Template

For `*-sumary.md`:

```md
# 要約

## 3行サマリー
- ...
- ...
- ...

## 重要ポイント
- ...

## 次に読むべき人
- ...

## 元URL
- <https://...>
```
