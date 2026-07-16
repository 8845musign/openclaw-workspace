import imaplib
import email
import json
import os
import sys

def load_env():
    try:
        with open('.env', 'r') as f:
            for line in f:
                if '=' in line:
                    key, val = line.strip().split('=', 1)
                    os.environ[key] = val.strip('"').strip("'")
    except:
        pass

load_env()

def get_emails_since_uid(target_uid):
    mail = imaplib.IMAP4_SSL(os.environ.get('IMAP_HOST', 'imap.gmail.com'))
    mail.login(os.environ.get('IMAP_USER'), os.environ.get('IMAP_PASS'))
    mail.select('INBOX')
    
    typ, data = mail.search(None, f'UID {target_uid + 1}:*')
    new_emails = []
    
    for item in data:
        for uid in item.split():
            typ, msg_data = mail.fetch(uid, '(RFC822)')
            # msg_data looks like [(b'1246 (UID 1246 FLAGS (\\Seen))', b'header...')]
            if len(msg_data) > 0 and isinstance(msg_data[0], tuple):
                msg = email.message_from_bytes(msg_data[0][1])
                new_emails.append({
                    'uid': int(uid.decode()),
                    'from': msg.get('From'),
                    'subject': msg.get('Subject')
                })
        
    mail.logout()
    return new_emails

print(json.dumps(get_emails_since_uid(1191)))
