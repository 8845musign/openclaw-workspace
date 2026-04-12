import imaplib
import email
import os
import json
import re
import sys # ADDED: Import sys module
from datetime import datetime, timedelta

def get_env_var(name, default=None):
    return os.getenv(name) if os.getenv(name) is not None else default

def connect_imap():
    host = get_env_var('IMAP_HOST')
    user = get_env_var('IMAP_USER')
    password = get_env_var('IMAP_PASS')
    port = int(get_env_var('IMAP_PORT', 993))
    use_tls = get_env_var('IMAP_TLS', 'true').lower() == 'true'

    if not all([host, user, password]):
        raise ValueError("IMAP_HOST, IMAP_USER, and IMAP_PASS environment variables must be set.")

    if use_tls:
        mail = imaplib.IMAP4_SSL(host, port)
    else:
        mail = imaplib.IMAP4(host, port)

    mail.login(user, password)
    return mail

def parse_message(msg_data):
    if not isinstance(msg_data, bytes):
        raise TypeError(f"Expected bytes for message data, but got {type(msg_data)}") # ADDED: Type check for msg_data

    msg = email.message_from_bytes(msg_data)
    subject_parts = email.header.decode_header(msg['Subject'])
    subject = ''
    for s, charset in subject_parts:
        if isinstance(s, int): s = str(s) # ADDED: Handle int type
        if isinstance(s, bytes):
            try:
                subject += s.decode(charset if charset else 'utf-8')
            except (UnicodeDecodeError, LookupError):
                subject += s.decode('latin-1', errors='ignore')
        else:
            subject += str(s) # Ensure it's a string

    # From
    from_parts = email.header.decode_header(msg['From'])
    from_header = ''
    for f, charset in from_parts:
        if isinstance(f, int): f = str(f) # ADDED: Handle int type
        if isinstance(f, bytes):
            try:
                from_header += f.decode(charset if charset else 'utf-8')
            except (UnicodeDecodeError, LookupError):
                from_header += f.decode('latin-1', errors='ignore')
        else:
            from_header += str(f) # Ensure it's a string

    # To
    to_parts = email.header.decode_header(msg['To']) if msg['To'] else []
    to_header = ''
    for t, charset in to_parts:
        if isinstance(t, int): t = str(t) # ADDED: Handle int type
        if isinstance(t, bytes):
            try:
                to_header += t.decode(charset if charset else 'utf-8')
            except (UnicodeDecodeError, LookupError):
                to_header += t.decode('latin-1', errors='ignore')
        else:
            to_header += str(t) # Ensure it's a string

    date_header = msg['Date']
    
    snippet = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdisposition = str(part.get('Content-Disposition'))
            if ctype == 'text/plain' and 'attachment' not in cdisposition:
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    try:
                        snippet = payload.decode('utf-8', errors='ignore')
                        break
                    except Exception:
                        pass
                elif isinstance(payload, str): # Handle if payload is already str
                    snippet = payload
                    break
    else:
        payload = msg.get_payload(decode=True)
        if isinstance(payload, bytes):
            try:
                snippet = payload.decode('utf-8', errors='ignore')
            except Exception:
                pass
        elif isinstance(payload, str): # Handle if payload is already str
            snippet = payload
    
    # Simple snippet extraction for the first line or few sentences
    snippet = snippet.strip()
    first_newline = snippet.find('\n')
    if first_newline != -1:
        snippet = snippet[:first_newline]
    
    if len(snippet) > 150: # Limit snippet length
        snippet = snippet[:150] + "..."

    return {
        'date': date_header,
        'from': from_header,
        'to': to_header,
        'subject': subject,
        'snippet': snippet
    }

def fetch_messages(mail, search_criteria, limit=None):
    mailbox = get_env_var('IMAP_MAILBOX', 'INBOX')
    mail.select(mailbox)
    
    status, msg_ids = mail.search(None, *search_criteria)
    if status != 'OK':
        return []

    messages = []
    id_list = msg_ids[0].split()
    
    if limit:
        id_list = id_list[-limit:] # Get newest N messages

    for uid in id_list:
        status, msg_data = mail.fetch(uid, '(RFC822)')
        if status == 'OK':
            # ADDED: Robust check for msg_data structure
            if isinstance(msg_data, list) and len(msg_data) > 0 and \
               isinstance(msg_data[0], tuple) and len(msg_data[0]) > 1 and \
               isinstance(msg_data[0][1], bytes):
                messages.append(parse_message(msg_data[0][1]))
            else:
                # 予期しない形式のメッセージデータをスキップまたはログ記録
                print(f"Skipping message with unexpected data format: {msg_data}", file=sys.stderr)
    return messages

def main():
    import argparse
    parser = argparse.ArgumentParser(description='IMAP Inbox Reader Script')
    subparsers = parser.add_subparsers(dest='action', required=True)

    # Latest messages sub-command
    latest_parser = subparsers.add_parser('latest', help='Fetch the newest messages')
    latest_parser.add_argument('--limit', type=int, default=10, help='Number of latest messages to fetch')

    # Search messages sub-command
    search_parser = subparsers.add_parser('search', help='Search messages based on criteria')
    search_parser.add_argument('--text', type=str, help='Free text search (subject, from, body)')
    search_parser.add_argument('--from', dest='sender', type=str, help='Search by sender email address')
    search_parser.add_argument('--since', type=str, help='Search for messages since a specific date (YYYY-MM-DD)')
    search_parser.add_argument('--criteria', type=str, help='Raw IMAP search criteria (e.g., \"(UNSEEN SINCE \"01-Mar-2026\")\" )')
    search_parser.add_argument('--limit', type=int, default=20, help='Maximum number of messages to return')

    args = parser.parse_args()

    try:
        mail = connect_imap()
        
        search_criteria = []
        if args.action == 'latest':
            search_criteria = ['ALL']
            messages = fetch_messages(mail, search_criteria, args.limit)
        elif args.action == 'search':
            if args.criteria:
                search_criteria = [args.criteria]
            else:
                if args.text:
                    search_criteria.extend(['TEXT', args.text])
                if args.sender:
                    search_criteria.extend(['FROM', args.sender])
                if args.since:
                    try:
                        since_date = datetime.strptime(args.since, '%Y-%m-%d')
                        # IMAP's SINCE criteria uses DD-Mon-YYYY format
                        imap_since_date = since_date.strftime('%d-%b-%Y')
                        search_criteria.extend(['SINCE', imap_since_date])
                    except ValueError:
                        print(json.dumps({"status": "error", "message": "Invalid date format for --since. Use YYYY-MM-DD."}))
                        return

                if not search_criteria:
                    print(json.dumps({"status": "error", "message": "No search criteria provided for search action."}))
                    return
                search_criteria.insert(0, 'ALL') # Ensure 'ALL' is at the beginning for proper search
            
            messages = fetch_messages(mail, search_criteria, args.limit)
        
        mail.logout()
        print(json.dumps({
            "status": "success",
            "mailbox": get_env_var('IMAP_MAILBOX', 'INBOX'),
            "count": len(messages),
            "messages": messages
        }, indent=2, ensure_ascii=False))

    except ValueError as e:
        print(json.dumps({"status": "error", "message": str(e)}))
    except Exception as e:
        print(json.dumps({"status": "error", "message": f"An unexpected error occurred: {str(e)}"}))

if __name__ == '__main__':
    main()