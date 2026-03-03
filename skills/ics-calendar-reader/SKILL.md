---
name: ics-calendar-reader
description: Read calendar events from one or more ICS feeds and answer schedule/search requests. Use when the user wants ICS-based calendar integration, including listing events for today/tomorrow/week, filtering by calendar name, or keyword search across title/description/location/attendees.
---

# ICS Calendar Reader

Load config from `skills/ics-calendar-reader/references/ics-sources.json` (or a user-provided equivalent with the same schema).

## Config schema (minimal)

Use a single top-level `ics` array. Each source contains only:
- `name`
- `description`
- `url`

## Workflow

1. Read the config file.
2. Fetch all ICS URLs.
3. Parse VEVENT entries.
4. Normalize fields when present:
   - title (`SUMMARY`)
   - description (`DESCRIPTION`)
   - location (`LOCATION`)
   - attendees (`ATTENDEE`)
   - start/end time (`DTSTART`/`DTEND`)
   - source calendar name
5. Merge results from all sources.
6. If one source fails, continue with others and report which source failed.

## Supported intents

- List events for:
  - today
  - tomorrow
  - this week
- Filter by calendar `name`
- Keyword search over title/description/location/attendees
- Time-window search (for example: next week, this month)

## Output defaults

Return events sorted by start time ascending.
Default compact fields:
- start time
- title
- calendar name

When asked, include extended fields:
- description
- location
- attendees

## Search/result limits

- Cap returned search results at **100** items.
- Prefer asking for a narrower date range if matches are too broad.

## Constraints

- ICS is read-only in this skill.
- Field availability depends on the source ICS publisher.
- Do not assume real-time sync; treat feed refresh as periodic.
