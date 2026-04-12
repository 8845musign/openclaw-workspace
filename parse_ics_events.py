
import re
import json
from datetime import datetime, timedelta, timezone

# Define Tokyo timezone
TOKYO_TZ = timezone(timedelta(hours=9))

def parse_ics_datetime(dt_str, is_date_only=False):
    if is_date_only:
        return datetime.strptime(dt_str, '%Y%m%d').replace(tzinfo=TOKYO_TZ)
    elif dt_str.endswith('Z'):
        # UTC time
        return datetime.strptime(dt_str, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc).astimezone(TOKYO_TZ)
    else:
        # Local time with TZID
        # For simplicity, assume it's already in TOKYO_TZ if no 'Z' and TZID is Tokyo
        # A more robust parser would use pytz or similar, but we're constrained.
        return datetime.strptime(dt_str, '%Y%m%dT%H%M%S').replace(tzinfo=TOKYO_TZ)

def parse_ics_content(ics_content, calendar_name, today_date, tomorrow_date):
    events = []
    current_event = {}
    in_event = False

    lines = ics_content.replace('\r\n', '\n').split('\n')

    for line in lines:
        if line.strip() == 'BEGIN:VEVENT':
            in_event = True
            current_event = {'calendar': calendar_name}
        elif line.strip() == 'END:VEVENT':
            if in_event:
                # Process the event if it's within today or tomorrow
                if 'DTSTART' in current_event and 'DTEND' in current_event and 'SUMMARY' in current_event:
                    dtstart_str = current_event['DTSTART']
                    dtend_str = current_event['DTEND']
                    
                    is_date_only_start = ';VALUE=DATE:' in lines[lines.index(f'DTSTART{dtstart_str}')-1] if isinstance(lines, list) else False
                    is_date_only_end = ';VALUE=DATE:' in lines[lines.index(f'DTEND{dtend_str}')-1] if isinstance(lines, list) else False
                    
                    try:
                        start_dt = parse_ics_datetime(dtstart_str.split(':')[-1], is_date_only_start)
                        end_dt = parse_ics_datetime(dtend_str.split(':')[-1], is_date_only_end)

                        # Filter for events today or tomorrow (inclusive of all-day events)
                        if (start_dt.date() == today_date or start_dt.date() == tomorrow_date or
                            end_dt.date() == today_date or end_dt.date() == tomorrow_date):
                            events.append({
                                'summary': current_event['SUMMARY'],
                                'start': start_dt.isoformat(),
                                'end': end_dt.isoformat(),
                                'calendar': calendar_name,
                                'uid': current_event.get('UID')
                            })
                    except ValueError:
                        # Skip malformed date/time strings
                        pass
                current_event = {}
                in_event = False
        elif in_event:
            # Handle folded lines (lines starting with space) - basic unfolding
            if line.startswith(' ') and current_event:
                last_key = list(current_event.keys())[-1]
                current_event[last_key] += line[1:]
            else:
                match_summary = re.match(r'SUMMARY:(.*)', line)
                match_dtstart = re.match(r'DTSTART(?:;TZID=Asia/Tokyo|;VALUE=DATE)?:(.*)', line)
                match_dtend = re.match(r'DTEND(?:;TZID=Asia/Tokyo|;VALUE=DATE)?:(.*)', line)
                match_uid = re.match(r'UID:(.*)', line)

                if match_summary:
                    current_event['SUMMARY'] = match_summary.group(1).replace('\\,', ',').replace('\\n', '\n').strip()
                elif match_dtstart:
                    current_event['DTSTART'] = match_dtstart.group(1).strip()
                elif match_dtend:
                    current_event['DTEND'] = match_dtend.group(1).strip()
                elif match_uid:
                    current_event['UID'] = match_uid.group(1).strip()

    return events

# Main execution logic for the script
if __name__ == '__main__':
    import sys
    
    # Expecting ICS content, calendar name, today_date_str, tomorrow_date_str from stdin
    args = json.loads(sys.stdin.read())
    ics_content = args['ics_content']
    calendar_name = args['calendar_name']
    today_date_str = args['today_date']
    tomorrow_date_str = args['tomorrow_date']

    today = datetime.strptime(today_date_str, '%Y-%m-%d').date()
    tomorrow = datetime.strptime(tomorrow_date_str, '%Y-%m-%d').date()

    parsed_events = parse_ics_content(ics_content, calendar_name, today, tomorrow)
    print(json.dumps(parsed_events, ensure_ascii=False, indent=2))
