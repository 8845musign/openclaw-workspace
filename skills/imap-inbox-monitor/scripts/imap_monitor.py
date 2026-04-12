#!/usr/bin/env python3
import argparse
import email
import imaplib
import json
import os
import re
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.message import Message
from pathlib import Path
from typing import Any, Dict, List, Tuple


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
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="replace")
                if ctype == "text/html":
                    text = re.sub(r"<[^>]+>", " ", text)
                parts.append(text)
    else:
        payload = msg.get_payload(decode=True) or b""
        charset = msg.get_content_charset() or "utf-8"
        text = payload.decode(charset, errors="replace")
        if msg.get_content_type() == "text/html":
            text = re.sub(r"<[^>]+>", " ", text)
        parts.append(text)
    return re.sub(r"\s+", " ", "\n".join(parts)).strip()


def env_required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def connect() -> Tuple[imaplib.IMAP4, str]:
    host = env_required("IMAP_HOST")
    user = env_required("IMAP_USER")
    password = env_required("IMAP_PASS")
    mailbox = os.getenv("IMAP_MAILBOX", "INBOX")
    port = int(os.getenv("IMAP_PORT", "993"))
    use_tls = os.getenv("IMAP_TLS", "true").lower() != "false"

    imap = imaplib.IMAP4_SSL(host, port) if use_tls else imaplib.IMAP4(host, port)
    imap.login(user, password)
    status, _ = imap.select(mailbox, readonly=True)
    if status != "OK":
        raise SystemExit(f"Failed to open mailbox: {mailbox}")
    return imap, mailbox


def load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"last_seen_uid": 0, "updated_at": None}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_message(imap: imaplib.IMAP4, uid: bytes) -> Dict[str, Any] | None:
    raw = None
    for query in ("(RFC822)", "(BODY.PEEK[])"):
        status, data = imap.uid("fetch", uid, query)
        if status != "OK" or not data:
            continue
        for item in data:
            if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], (bytes, bytearray)):
                raw = bytes(item[1])
                break
        if raw:
            break
    if not raw:
        return None

    msg = email.message_from_bytes(raw)
    snippet = extract_text(msg)[:300]
    return {
        "uid": int(uid.decode()),
        "date": decode_mime(msg.get("Date", "")),
        "from": decode_mime(msg.get("From", "")),
        "to": decode_mime(msg.get("To", "")),
        "subject": decode_mime(msg.get("Subject", "")),
        "snippet": snippet,
    }


def append_memory(path: Path, records: List[Dict[str, Any]]) -> None:
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def run(args: argparse.Namespace) -> None:
    state_path = Path(args.state_file).resolve()
    memory_path = Path(args.memory_file).resolve()
    state = load_state(state_path)
    last_seen_uid = int(state.get("last_seen_uid", 0))

    imap, mailbox = connect()
    try:
        status, data = imap.uid("search", None, "ALL")
        if status != "OK":
            raise SystemExit("IMAP search failed")
        uids = [int(u.decode()) for u in data[0].split() if u]
        if not uids:
            result = {
                "mailbox": mailbox,
                "new_count": 0,
                "messages": [],
                "message": "新着メールはありません",
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return

        new_uids = [u for u in uids if u > last_seen_uid]
        if last_seen_uid == 0:
            # first run: avoid huge backfill
            new_uids = new_uids[-args.limit:]

        fetched: List[Dict[str, Any]] = []
        for uid in new_uids[-args.limit:]:
            m = fetch_message(imap, str(uid).encode())
            if m:
                m["checked_at"] = datetime.now(timezone.utc).isoformat()
                fetched.append(m)

        append_memory(memory_path, fetched)

        max_seen = max(uids) if uids else last_seen_uid
        save_state(
            state_path,
            {
                "last_seen_uid": max_seen,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "mailbox": mailbox,
            },
        )

        result = {
            "mailbox": mailbox,
            "previous_last_seen_uid": last_seen_uid,
            "last_seen_uid": max_seen,
            "new_count": len(fetched),
            "messages": [
                {
                    "uid": m["uid"],
                    "date": m["date"],
                    "from": m["from"],
                    "to": m["to"],
                    "subject": m["subject"],
                    "snippet": m["snippet"],
                }
                for m in fetched
            ],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        imap.logout()


def main() -> None:
    parser = argparse.ArgumentParser(description="Incremental read-only IMAP monitor")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Fetch only new messages since previous run")
    p_run.add_argument("--limit", type=int, default=100)
    p_run.add_argument("--state-file", default="/home/hiroki-yokouchi/.openclaw/workspace/state/imap_state.json")
    p_run.add_argument("--memory-file", default="/home/hiroki-yokouchi/.openclaw/workspace/memory/imap-mail-summaries.jsonl")
    p_run.set_defaults(func=run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
