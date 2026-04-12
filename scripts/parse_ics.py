
import re
from datetime import datetime, timedelta, timezone

def parse_ics_date(dt_str, tzid=None):
    # Handle DATE-only format (YYYYMMDD)
    if 'T' not in dt_str and len(dt_str) == 8:
        return datetime.strptime(dt_str, '%Y%m%d').replace(tzinfo=timezone(timedelta(hours=9))) # Assume JST for DATE-only events

    # Handle UTC (Z)
    if dt_str.endswith('Z'):
        dt = datetime.strptime(dt_str, '%Y%m%dT%H%M%SZ')
        return dt.replace(tzinfo=timezone.utc)
    # Handle TZID (assume Asia/Tokyo for now, as it's the dominant one)
    elif tzid == 'Asia/Tokyo':
        dt = datetime.strptime(dt_str, '%Y%m%dT%H%M%S')
        # Tokyo is +9:00 from UTC
        return dt.replace(tzinfo=timezone(timedelta(hours=9)))
    # Default to assuming JST if no timezone info, or if parsing fails.
    else:
        try:
            dt = datetime.strptime(dt_str, '%Y%m%dT%H%M%S')
            return dt.replace(tzinfo=timezone(timedelta(hours=9))) # Assume JST
        except ValueError:
            return None # Fallback if parsing fails


def get_events_for_dates(ics_content, calendar_name, target_dates_jst):
    events = []
    # Regular expressions for extracting event details
    event_pattern = re.compile(r'BEGIN:VEVENT(.*?)END:VEVENT', re.DOTALL)
    summary_pattern = re.compile(r'SUMMARY:(.*)', re.IGNORECASE)
    dtstart_pattern = re.compile(r'DTSTART(?:;TZID=([^:]+))?(?:;VALUE=DATE)?:(\d{8}(?:T\d{6}(?:Z)?)?)', re.IGNORECASE)
    dtend_pattern = re.compile(r'DTEND(?:;TZID=([^:]+))?(?:;VALUE=DATE)?:(\d{8}(?:T\d{6}(?:Z)?)?)', re.IGNORECASE)
    location_pattern = re.compile(r'LOCATION:(.*)', re.IGNORECASE)

    for event_match in event_pattern.finditer(ics_content):
        event_block = event_match.group(1)
        
        summary_match = summary_pattern.search(event_block)
        summary = summary_match.group(1).strip() if summary_match else 'No Summary'

        dtstart_match = dtstart_pattern.search(event_block)
        dtend_match = dtend_pattern.search(event_block)

        start_time = None
        end_time = None

        if dtstart_match:
            tzid_start = dtstart_match.group(1)
            dt_start_str = dtstart_match.group(2)
            start_time = parse_ics_date(dt_start_str, tzid_start)

        if dtend_match:
            tzid_end = dtend_match.group(1)
            dt_end_str = dtend_match.group(2)
            end_time = parse_ics_date(dt_end_str, tzid_end)

        location_match = location_pattern.search(event_block)
        location = location_match.group(1).strip() if location_match else 'No Location'

        if not start_time or not end_time:
            continue

        # Convert to JST for comparison and display
        if start_time.tzinfo and start_time.tzinfo != timezone(timedelta(hours=9)):
            start_time = start_time.astimezone(timezone(timedelta(hours=9)))
        if end_time.tzinfo and end_time.tzinfo != timezone(timedelta(hours=9)):
            end_time = end_time.astimezone(timezone(timedelta(hours=9)))
        
        # Check if the event overlaps with any of the target dates
        for target_date_jst in target_dates_jst:
            target_start_of_day = datetime(target_date_jst.year, target_date_jst.month, target_date_jst.day, 0, 0, 0, tzinfo=timezone(timedelta(hours=9)))
            target_end_of_day = datetime(target_date_jst.year, target_date_jst.month, target_date_jst.day, 23, 59, 59, tzinfo=timezone(timedelta(hours=9)))

            if (start_time < target_end_of_day and end_time > target_start_of_day):
                events.append({
                    'calendar': calendar_name,
                    'summary': summary.replace('\\,', ',').replace('\\n', ' ').replace('\\r', ''),
                    'start': start_time,
                    'end': end_time,
                    'location': location.replace('\\,', ',').replace('\\n', ' ').replace('\\r', '')
                })
                break # Event found for a target date, no need to check other target dates

    return events

if __name__ == '__main__':
    import sys
    import json
    
    current_date_jst = datetime.now(timezone(timedelta(hours=9))).date()
    target_dates_jst = [current_date_jst, current_date_jst + timedelta(days=1)] # Today and Tomorrow

    ics_content = sys.stdin.read()
    
    # Placeholder for calendar name, as it's not in ICS content itself.
    # In a real scenario, this would be passed from the caller.
    # For now, let's assume 'Unknown Calendar' or pass it via argument if running directly.
    # For this heartbeat, I'll pass the name from the `ics-sources.json` config.
    # The script will be called for each calendar, so I need to pass the calendar name.
    # I'll modify this to accept calendar_name as a command line argument or modify the calling approach.

    # Let's assume the script will be called with calendar name as an argument
    if len(sys.argv) > 1:
        calendar_name_arg = sys.argv[1]
    else:
        calendar_name_arg = 'Unknown Calendar'

    upcoming_events = get_events_for_dates(ics_content, calendar_name_arg, target_dates_jst)

    # Sort events by start time
    upcoming_events.sort(key=lambda x: x['start'])

    # Format for output
    formatted_events = []
    for event in upcoming_events:
        start_str = event['start'].strftime('%Y/%m/%d %H:%M')
        end_str = event['end'].strftime('%Y/%m/%d %H:%M')
        formatted_events.append(
            f"  - {event['calendar']} - {start_str} - {end_str}: {event['summary']}"
        )
    
    if formatted_events:
        print(f"Upcoming Events ({current_date_jst.strftime('%Y/%m/%d')} & {(current_date_jst + timedelta(days=1)).strftime('%Y/%m/%d')} JST):")
        for fe in formatted_events:
            print(fe)
    else:
        print(f"No upcoming events for {current_date_jst.strftime('%Y/%m/%d')} & {(current_date_jst + timedelta(days=1)).strftime('%Y/%m/%d')} JST.")
