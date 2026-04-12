
import imaplib, email, json, datetime; from dateutil import parser; import pytz; import random
import os

STATE_FILE = 'state/heartbeat-context.json'
LOG_FILE = 'memory/heartbeat-log.jsonl'

JST = pytz.timezone('Asia/Tokyo')

def load_state():
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            'last_checked_at': None,
            'last_chat_cursor': None,
            'last_mail_uid': None,
            'last_calendar_hash': None,
            'last_digest_at': None
        }

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def append_log(event):
    with open(LOG_FILE, 'a') as f:
        json.dump(event, f, ensure_ascii=False)
        f.write('\n')

state = load_state()

mail_events = []
print(json.dumps({'mail_events': mail_events}))

calendar_events = []
print(json.dumps({'calendar_events': calendar_events}))

chat_events = []
print(json.dumps({'chat_events': chat_events}))

web_recommendations = []
print(json.dumps({'web_recommendations': web_recommendations}))

current_time_jst = datetime.datetime.now(JST)
state['last_checked_at'] = current_time_jst.timestamp()

is_quiet_hours = 23 <= current_time_jst.hour or current_time_jst.hour < 8

cat_messages = ["ひなたぼっこは最高だにゃ", "今日のおやつは何だにゃん", "しっぽフリフリごきげんだにゃ", "Zzz すぴー", "毛繕い ペロペロ（毛繕い）"]
cat_message = random.choice(cat_messages)

save_state(state)

print(json.dumps({
    'notification': cat_message,
    'slack_dm_key': 'agent:main:slack:direct:u08t8s3bbfx'
}, ensure_ascii=False))
