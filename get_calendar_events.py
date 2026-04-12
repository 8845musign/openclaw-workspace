
import requests
from ics import Calendar
from datetime import datetime, date, timedelta
import pytz
import json

def get_today_events(ics_sources):
    tokyo_tz = pytz.timezone("Asia/Tokyo")
    today = tokyo_tz.localize(datetime(2026, 4, 7, 0, 0, 0)).date() # Ensure time part is 0 for comparison
    all_events = []

    for source in ics_sources["ics"]:
        try:
            response = requests.get(source["url"])
            response.raise_for_status()
            cal = Calendar(response.text)

            for event in cal.events:
                event_start_datetime = event.begin.astimezone(tokyo_tz) if event.begin else None
                event_end_datetime = event.end.astimezone(tokyo_tz) if event.end else None
                
                event_start_date = event_start_datetime.date() if event_start_datetime else None
                event_end_date = event_end_datetime.date() if event_end_datetime else None

                if event_start_date:
                    # Case 1: Event starts today
                    if event_start_date == today:
                        all_events.append({
                            "start_time": event_start_datetime.strftime("%H:%M") if event_start_datetime.time() != datetime.min.time() else "終日",
                            "title": event.name if event.name else "タイトルなし",
                            "calendar_name": source["name"]
                        })
                    # Case 2: Event spans multiple days and today is within that span
                    # For all-day events, event.end is often the day *after* the event ends.
                    # So, if event_start_date < today and today < actual_end_date
                    elif event_end_date and event_start_date < today < event_end_date:
                         # Check if it's an all-day event that started before today and ends after today
                        is_all_day_event = (event_start_datetime and event_end_datetime and 
                                            event_start_datetime.time() == datetime.min.time() and 
                                            event_end_datetime.time() == datetime.min.time())

                        if is_all_day_event or (event_end_datetime and event_start_datetime < tokyo_tz.localize(datetime(today.year, today.month, today.day, 23, 59, 59)) < event_end_datetime):
                            all_events.append({
                                "start_time": "終日", 
                                "title": event.name if event.name else "タイトルなし",
                                "calendar_name": source["name"]
                            })

        except requests.exceptions.RequestException as e:
            print(f"Failed to fetch {source["name"]} calendar: {e}")
        except Exception as e:
            print(f"Error processing {source["name"]} calendar: {e}")

    # Sort events by start_time. "終日" events should appear first.
    all_events.sort(key=lambda x: (0 if x["start_time"] == "終日" else 1, x["start_time"]))

    return all_events

ics_sources_data = {
  "ics": [
    {
      "name": "Work",
      "description": "仕事用カレンダー",
      "url": "https://calendar.google.com/calendar/ical/hiroki.yokouchi%40shirukuru.net/private-a7bbd539e421b408c22ec52ee6c0f912/basic.ics"
    },
    {
      "name": "Private",
      "description": "個人予定",
      "url": "https://calendar.google.com/calendar/ical/8845musign%40gmail.com/private-3c41626828e4c9eef463816faa82f0c5/basic.ics"
    },
    {
      "name": "Family",
      "description": "家族予定",
      "url": "https://calendar.google.com/calendar/ical/family11179808575868051245%40group.calendar.google.com/private-93964c55d3b2d448e438928b52d725e6/basic.ics"
    },
    {
      "name": "Japanese Holidays",
      "description": "祝日カレンダー",
      "url": "https://www.thunderbird.net/media/caldata/autogen/JapanHolidays.ics"
    }
  ]
}

events = get_today_events(ics_sources_data)

if events:
    print(json.dumps(events, ensure_ascii=False))
else:
    print("[]")
