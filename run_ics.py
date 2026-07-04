import json
from scripts.ics_calendar_reader import get_upcoming_events
with open('skills/ics-calendar-reader/references/ics-sources.json', 'r') as f:
    sources = json.load(f)
events = get_upcoming_events(sources, look_ahead_hours=48)
print(json.dumps(events, indent=2))
