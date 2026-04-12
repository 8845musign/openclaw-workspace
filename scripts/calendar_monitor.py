
import json
import requests
from icalendar import Calendar, Event
from datetime import datetime, timedelta, timezone, date
import hashlib

def get_calendar_events(config_path, days_ahead=7):
    with open(config_path, 'r') as f:
        config = json.load(f)

    all_events = []
    fetch_failures = []
    succeeded_sources = []
    
    jst = timezone(timedelta(hours=9))
    now = datetime.now(jst)
    end_date = now + timedelta(days=days_ahead)

    for source in config['ics']:
        try:
            response = requests.get(source['url'])
            response.raise_for_status()
            cal = Calendar.from_ical(response.text)
            succeeded_sources.append(source['name'])

            for component in cal.walk('vevent'):
                event = Event(component)
                
                # Ensure DTSTART and DTEND are handled correctly
                if 'dtstart' not in event or 'dtend' not in event:
                    continue
                
                start_dt = event.get('dtstart').dt
                end_dt = event.get('dtend').dt

                # Ensure DTSTART and DTEND are datetime objects with timezone
                if isinstance(start_dt, datetime):
                    if start_dt.tzinfo is None:
                        start_dt = start_dt.replace(tzinfo=jst)
                elif isinstance(start_dt, date):
                    start_dt = datetime(start_dt.year, start_dt.month, start_dt.day, tzinfo=jst)

                if isinstance(end_dt, datetime):
                    if end_dt.tzinfo is None:
                        end_dt = end_dt.replace(tzinfo=jst)
                elif isinstance(end_dt, date):
                    # For all-day events, end_dt typically represents the day *after* the event ends.
                    # For comparison, let's set it to the end of the day it actually ends.
                    end_dt = datetime(end_dt.year, end_dt.month, end_dt.day, 23, 59, 59, tzinfo=jst)
                
                # Filter events within the next `days_ahead`
                if start_dt < end_date and end_dt > now:
                    all_events.append({
                        'calendar': source['name'],
                        'summary': str(event.get('summary')),
                        'description': str(event.get('description', '')),
                        'location': str(event.get('location', '')),
                        'start': start_dt.isoformat(),
                        'end': end_dt.isoformat()
                    })
        except Exception as e:
            print(f"Error fetching or parsing calendar {source['name']}: {e}")
            fetch_failures.append({
                'calendar': source['name'],
                'error': str(e),
            })
            continue
    
    # Sort events by start time
    all_events.sort(key=lambda x: x['start'])
    return {
        'events': all_events,
        'fetch_failures': fetch_failures,
        'succeeded_sources': succeeded_sources,
        'total_sources': len(config['ics']),
    }

def generate_events_hash(events):
    events_str = json.dumps(events, sort_keys=True)
    return hashlib.sha1(events_str.encode('utf-8')).hexdigest()

if __name__ == '__main__':
    config_path = '/home/hiroki-yokouchi/.openclaw/workspace/skills/ics-calendar-reader/references/ics-sources.json'
    state_file = '/home/hiroki-yokouchi/.openclaw/workspace/state/heartbeat-context.json'

    # Load current state
    try:
        with open(state_file, 'r') as f:
            state = json.load(f)
    except FileNotFoundError:
        state = {}
    
    last_calendar_hash = state.get('last_calendar_hash')

    result = get_calendar_events(config_path)
    current_events = result['events']
    current_hash = generate_events_hash(current_events)

    new_events = []
    hash_changed = False
    state_updated = False
    fetch_failures = result['fetch_failures']
    succeeded_sources = result['succeeded_sources']

    if succeeded_sources and last_calendar_hash != current_hash:
        print("Calendar events have changed!")
        # For simplicity, if hash changes, we'll just report all current events
        # as "new/updated" if we don't have a sophisticated diffing mechanism.
        # For now, let's just report current_events if hash changes.
        new_events = current_events # Treating all as new/updated on hash change
        hash_changed = True
        
        # Only update the stored hash when at least one source fetched successfully.
        state['last_calendar_hash'] = current_hash
        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2)
        state_updated = True
    elif not succeeded_sources:
        print("Calendar fetch failed for all sources; keeping previous hash.")
    else:
        print("No significant calendar changes.")

    # Output for reporting
    output = {
        'hash_changed': hash_changed,
        'new_events': new_events,
        'current_hash': current_hash,
        'last_hash': last_calendar_hash,
        'state_updated': state_updated,
        'succeeded_sources': succeeded_sources,
        'failed_sources': fetch_failures,
        'total_sources': result['total_sources'],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
