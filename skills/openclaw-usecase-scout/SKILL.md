---
name: openclaw-usecase-scout
description: Find, score, and summarize high-value OpenClaw use cases with novelty filtering against prior memory notes. Use when the user asks to collect new OpenClaw use cases, avoid duplicates with previously gathered ideas, or turn use-case research into actionable shortlists.
---

# OpenClaw Usecase Scout

Collect practical OpenClaw use cases from externally published examples (blogs, social posts, community threads, GitHub repos) that are high-impact and distinct from previously logged ideas.

## Workflow

1. Read memory files (`memory/*.md`) and extract previously collected use cases.
2. Build a "covered themes" list in 1 line per theme.
3. Gather candidate use cases from the web with evidence preference:
   - Prefer real-world implementations and reports (blogs, social posts, community threads, GitHub repos/issues)
   - Official docs can be used as capability reference, but are not required and not prioritized
   - Avoid pure idea posts with no concrete setup, execution details, or outcomes
4. Score each candidate (1-5) on:
   - Impact (time/risk reduction)
   - Feasibility (how quickly usable)
   - Novelty (distance from covered themes)
5. Keep top N requested by the user (default 3).
6. Return each use case with this exact compact format:
   - Name
   - Why it is compelling (1 line)
   - Minimal implementation sketch (3 bullets)
   - Risk/guardrail (1 line)
   - Evidence URLs (2+ links; prioritize independent real-world sources)

## Dedup rule

Reject a candidate if it is only a wording variation of an already covered theme.
Example: "daily summary bot" and "morning digest automation" are duplicates.

## Source quality rules

- Always include clickable URLs for every selected use case.
- Prioritize URLs that show concrete real-world usage (setup steps, code/config snippets, screenshots, results, or postmortems).
- Use at least 2 links per use case from independent sources when possible.
- Clearly label weakly evidenced claims as hypothesis and lower feasibility score.
- Prefer deep links that directly support the claim (avoid homepage-only links).

## Output style

- Keep the shortlist concise and concrete.
- Prefer use cases that combine 2+ OpenClaw capabilities (e.g., cron + message, nodes + notify, browser + approvals).
- Do not prioritize by language; include any language if evidence quality is high.
- Avoid vague categories ("productivity", "automation").

## If user asks to persist

Write accepted use cases into `references/latest-shortlist.md` with date and source links so future runs can deduplicate faster.
