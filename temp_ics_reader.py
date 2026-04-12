import json
import requests
from datetime import datetime, timedelta, timezone

def get_events_for_days(ics_urls, target_dates):
    all_events = []
    tokyo_tz = timezone(timedelta(hours=9)) # JST is UTC+9

    for calendar_name, url in ics_urls.items():
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status() # Raise an exception for HTTP errors
            ics_content = response.text

            current_event = {}
            for line in ics_content.splitlines():
                line = line.strip() # Strip leading/trailing whitespace
                if line.startswith("BEGIN:VEVENT"):
                    current_event = {"calendar": calendar_name}
                elif line.startswith("END:VEVENT"):
                    if "DTSTART" in current_event and "SUMMARY" in current_event:
                        try:
                            # Parse DTSTART (example: DTSTART;VALUE=DATE:20260320 or DTSTART:20260320T100000Z)
                            dtstart_line = current_event["DTSTART"]
                            event_start_jst = None

                            if 'VALUE=DATE:' in dtstart_line:
                                date_str = dtstart_line.split('VALUE=DATE:')[1][:8]
                                event_start_utc = datetime.strptime(date_str, '%Y%m%d').replace(tzinfo=timezone.utc)
                                event_start_jst = event_start_utc.astimezone(tokyo_tz).replace(hour=0, minute=0, second=0, microsecond=0) # Treat as all-day
                            elif 'DTSTART:' in dtstart_line:
                                date_str_raw = dtstart_line.split('DTSTART:')[1]
                                if date_str_raw.endswith('Z'): # UTC time
                                    date_str = date_str_raw[:-1]
                                    event_start_utc = datetime.strptime(date_str, '%Y%m%dT%H%M%S').replace(tzinfo=timezone.utc)
                                    event_start_jst = event_start_utc.astimezone(tokyo_tz)
                                else: # Local time without TZ, assume JST
                                    date_str = date_str_raw
                                    event_start_jst = datetime.strptime(date_str, '%Y%m%dT%H%M%S').replace(tzinfo=tokyo_tz)
                            else:
                                continue # Skip if DTSTART format is unexpected

                            if event_start_jst:
                                # Check if the event falls on any of the target dates (in JST)
                                for target_date in target_dates:
                                    if event_start_jst.date() == target_date.date():
                                        all_events.append({
                                            "calendar": current_event["calendar"],
                                            "start_time": event_start_jst.strftime('%H:%M'),
                                            "date": event_start_jst.strftime('%Y-%m-%d'),
                                            "summary": current_event["SUMMARY"],
                                            "location": current_event.get("LOCATION", "N/A")
                                        })
                                        break # Event found for this date, no need to check other target dates
                        except Exception as e:
                            # print(f"Error parsing event in {calendar_name}: {e}")
                            pass
                    current_event = {"calendar": calendar_name} # Reset for next event
                elif line.startswith("DTSTART"):
                    current_event["DTSTART"] = line
                elif line.startswith("SUMMARY:"):
                    current_event["SUMMARY"] = line[len("SUMMARY:"):]
                elif line.startswith("LOCATION:"):
                    current_event["LOCATION"] = line[len("LOCATION:"):]
                # Handle folded lines (e.g., SUMMARY:Some\n  text)
                elif line.startswith(' ') and current_event and list(current_event.keys())[-1] in ['SUMMARY', 'DESCRIPTION', 'LOCATION']:
                    last_key = list(current_event.keys())[-1]
                    current_event[last_key] += line[1:] # Append to previous line

        except requests.exceptions.RequestException as e:
            # print(f"Failed to fetch ICS from {url} ({calendar_name}): {e}")
            pass
    return sorted(all_events, key=lambda x: (x['date'], x['start_time']))

# Get today and tomorrow's date in JST
now_jst = datetime.now(timezone(timedelta(hours=9)))
today_jst = now_jst
tomorrow_jst = now_jst + timedelta(days=1)
target_dates = [today_jst, tomorrow_jst]

# ICS configuration (hardcoded for this script based on previous read)
ics_config = {
    "Work": "https://calendar.google.com/calendar/ical/hiroki.yokouchi%40shirukuru.net/private-a7bbd539e421b408c22ec52ee6c0f912/basic.ics",
    "Private": "https://calendar.google.com/calendar/ical/8845musign%40gmail.com/private-3c41626828e4c9eef463816faa82f0c5/basic.ics",
    "Family": "https://calendar.google.com/calendar/ical/family11179808575868051245%40group.calendar.google.com/private-93964c55d3b2d448e438928b52d725e6/basic.ics",
    "Japanese Holidays": "https://www.thunderbird.net/media/caldata/autogen/JapanHolidays.ics"
}

events = get_events_for_days(ics_config, target_dates)

output_str = ""
if events:
    output_str += "📅 **Upcoming Events (Today & Tomorrow):**\n"
    current_date = None
    for event in events:
        if event['date'] != current_date:
            output_str += f"\n**{event['date']}**\n"
            current_date = event['date']
        output_str += f"- {event['start_time']} [{event['calendar']}] {event['summary']} (場所: {event['location']})\n"
else:
    output_str += "📅 今日の予定と明日の予定はないにゃ。\n"

print(output_str)