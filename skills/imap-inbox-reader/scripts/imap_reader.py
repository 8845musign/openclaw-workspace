#!/usr/bin/env python3
import argparse
import email
import imaplib
import json
import os
import re
import sys
from datetime import datetime
from email.header import decode_header, make_header
from email.message import Message
from typing import List, Tuple


def env(name: str, default: str = "") -> str:
    v = os.getenv(name, default)
    if not v:
        raise SystemExit(f"Missing required environment variable: {name}")
    return v


def decode_mime(value: str) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def extract_text(msg: Message) -> str:
    parts: List[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disp:
                continue
            if ctype in ("text/plain", "text/html"):
                try:
                    payload = part.get_payload(decode=True) or b""
                    charset = part.get_content_charset() or "utf-8"
                    text = payload.decode(charset, errors="replace")
                    if ctype == "text/html":
                        text = re.sub(r"<[^>]+>", " ", text)
                    parts.append(text)
                except Exception:
                    continue
    else:
        payload = msg.get_payload(decode=True) or b""
        charset = msg.get_content_charset() or "utf-8"
        text = payload.decode(charset, errors="replace")
        if msg.get_content_type() == "text/html":
            text = re.sub(r"<[^>]+>", " ", text)
        parts.append(text)

    merged = "\n".join(parts)
    merged = re.sub(r"\s+", " ", merged).strip()
    return merged


def build_search_criteria(args: argparse.Namespace) -> str:
    if args.criteria:
        return args.criteria

    clauses: List[str] = []

    if args.unseen:
        clauses.append("UNSEEN")
    if args.since:
        dt = datetime.strptime(args.since, "%Y-%m-%d")
        clauses.append(f'SINCE "{dt.strftime("%d-%b-%Y")}"')
    if args.sender:
        clauses.append(f'FROM "{args.sender}"')

    if args.text:
        # Broad search across common fields
        t = args.text.replace('"', "")
        clauses.extend([f'SUBJECT "{t}"', f'FROM "{t}"', f'BODY "{t}"'])
        return "(OR " + " ".join(clauses[-2:]) + ")" if len(clauses) >= 2 else clauses[0]

    return "(" + " ".join(clauses) + ")" if clauses else "ALL"


def connect() -> Tuple[imaplib.IMAP4_SSL, str]:
    host = env("IMAP_HOST")
    user = env("IMAP_USER")
    password = env("IMAP_PASS")
    mailbox = os.getenv("IMAP_MAILBOX", "INBOX")
    port = int(os.getenv("IMAP_PORT", "993"))
    use_tls = os.getenv("IMAP_TLS", "true").lower() != "false"

    if use_tls:
        imap = imaplib.IMAP4_SSL(host, port)
    else:
        imap = imaplib.IMAP4(host, port)

    imap.login(user, password)
    status, _ = imap.select(mailbox, readonly=True)
    if status != "OK":
        raise SystemExit(f"Failed to open mailbox: {mailbox}")
    return imap, mailbox


def fetch_by_uids(imap: imaplib.IMAP4_SSL, uids: List[bytes], limit: int):
    out = []
    for uid in uids[-limit:][::-1]:
        raw = None
        for query in ("(RFC822)", "(BODY.PEEK[])"):
            status, data = imap.uid("fetch", uid, query)
            if status != "OK" or not data:
                continue
            for item in data:
                # Typical shape: (b'123 (RFC822 {4567}', b'...raw bytes...')
                if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], (bytes, bytearray)):
                    raw = bytes(item[1])
                    break
            if raw:
                break
        if not raw:
            continue

        msg = email.message_from_bytes(raw)
        body = extract_text(msg)
        out.append(
            {
                "uid": uid.decode() if isinstance(uid, bytes) else str(uid),
                "date": decode_mime(msg.get("Date", "")),
                "from": decode_mime(msg.get("From", "")),
                "to": decode_mime(msg.get("To", "")),
                "subject": decode_mime(msg.get("Subject", "")),
                "snippet": body[:300],
            }
        )
    return out


def cmd_latest(args: argparse.Namespace):
    imap, mailbox = connect()
    try:
        status, data = imap.uid("search", None, "ALL")
        if status != "OK":
            raise SystemExit("IMAP search failed")
        uids = [u for u in data[0].split() if u]
        messages = fetch_by_uids(imap, uids, args.limit)
        print(json.dumps({"mailbox": mailbox, "count": len(messages), "messages": messages}, ensure_ascii=False, indent=2))
    finally:
        imap.logout()


def cmd_search(args: argparse.Namespace):
    imap, mailbox = connect()
    try:
        criteria = build_search_criteria(args)
        status, data = imap.uid("search", None, criteria)
        if status != "OK":
            raise SystemExit(f"IMAP search failed with criteria: {criteria}")
        uids = [u for u in data[0].split() if u]
        messages = fetch_by_uids(imap, uids, args.limit)
        print(
            json.dumps(
                {
                    "mailbox": mailbox,
                    "criteria": criteria,
                    "count": len(messages),
                    "messages": messages,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        imap.logout()


def main():
    parser = argparse.ArgumentParser(description="Read-only IMAP latest/search utility")
    sub = parser.add_subparsers(dest="command", required=True)

    p_latest = sub.add_parser("latest", help="Fetch newest messages")
    p_latest.add_argument("--limit", type=int, default=10)
    p_latest.set_defaults(func=cmd_latest)

    p_search = sub.add_parser("search", help="Search messages")
    p_search.add_argument("--text", help="Free text keyword")
    p_search.add_argument("--from", dest="sender", help="Sender filter")
    p_search.add_argument("--since", help="Date filter, YYYY-MM-DD")
    p_search.add_argument("--unseen", action="store_true", help="Only unseen messages")
    p_search.add_argument("--criteria", help="Raw IMAP search criteria")
    p_search.add_argument("--limit", type=int, default=20)
    p_search.set_defaults(func=cmd_search)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
