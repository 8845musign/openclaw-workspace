
import requests
from datetime import datetime, timedelta, timezone
import re
import hashlib
import json

def fetch_ics(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching ICS from {url}: {e}")
        return None

def parse_ics_events(ics_content, calendar_name):
    events = []
    current_event = {}
    
    for line in ics_content.splitlines():
        line = line.strip()
        if line == "BEGIN:VEVENT":
            current_event = {"calendar": calendar_name}
        elif line == "END:VEVENT":
            events.append(current_event)
            current_event = {}
        elif current_event:
            match = re.match(r"([^;:]+)(?:;[^:]+)?(:.*)", line)
            if match:
                key = match.group(1)
                value = match.group(2).lstrip(':')
                current_event[key] = value
    return events

def normalize_event(event):
    start_str = event.get('DTSTART', '').split(';')[0].replace('T', '')
    end_str = event.get('DTEND', '').split(';')[0].replace('T', '')
    
    # Handle all-day events vs. specific times
    if 'VALUE=DATE' in event.get('DTSTART', ''):
        # All-day event, treat as UTC start of the day
        try:
            dt_start = datetime.strptime(start_str, '%Y%m%d').replace(tzinfo=timezone.utc)
            dt_end = datetime.strptime(end_str, '%Y%m%d').replace(tzinfo=timezone.utc)
        except ValueError:
            dt_start = None
            dt_end = None
    else:
        # Specific time event
        try:
            dt_start = datetime.strptime(start_str, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
            dt_end = datetime.strptime(end_str, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
        except ValueError:
            try: # Try without Z for non-UTC explicit timezone
                dt_start = datetime.strptime(start_str, '%Y%m%dT%H%M%S').replace(tzinfo=timezone.utc)
                dt_end = datetime.strptime(end_str, '%Y%m%dT%H%M%S').replace(tzinfo=timezone.utc)
            except ValueError:
                dt_start = None
                dt_end = None

    return {
        "calendar": event.get("calendar"),
        "title": event.get("SUMMARY", ""),
        "description": event.get("DESCRIPTION", ""),
        "location": event.get("LOCATION", ""),
        "start": dt_start.isoformat() if dt_start else None,
        "end": dt_end.isoformat() if dt_end else None,
        "uid": event.get("UID", "")
    }

def get_upcoming_events(ics_sources, look_ahead_hours=48):
    all_normalized_events = []
    now_utc = datetime.now(timezone.utc)
    time_limit_utc = now_utc + timedelta(hours=look_ahead_hours)

    for source in ics_sources['ics']:
        ics_content = fetch_ics(source['url'])
        if ics_content:
            raw_events = parse_ics_events(ics_content, source['name'])
            for event in raw_events:
                normalized = normalize_event(event)
                if normalized["start"]:
                    event_start_dt = datetime.fromisoformat(normalized["start"])
                    if now_utc <= event_start_dt < time_limit_utc:
                        all_normalized_events.append(normalized)
    
    # Sort events by start time
    all_normalized_events.sort(key=lambda x: x["start"] if x["start"] else "")
    return all_normalized_events

def calculate_events_hash(events):
    # Create a stable string representation for hashing
    events_string = json.dumps(events, sort_keys=True, default=str)
    return hashlib.sha1(events_string.encode('utf-8')).hexdigest()

if __name__ == "__main__":
    # For testing purposes, you can load your ics-sources.json here
    # and call get_upcoming_events, then print results and hash.
    # This block won't run when imported as a module by the agent.
    pass
