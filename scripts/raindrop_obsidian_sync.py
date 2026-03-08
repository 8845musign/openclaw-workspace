#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
from urllib.request import Request, urlopen

SECRETS_PATH = os.path.expanduser("~/.openclaw/secrets.json")
STATE_PATH = os.path.expanduser("~/.openclaw/workspace/memory/raindrop-sync-state.json")
PENDING_PATH = os.path.expanduser("~/.openclaw/workspace/memory/raindrop-obsidian-pending.json")
AUTH_PROFILES_PATH = os.path.expanduser("~/.openclaw/agents/main/agent/auth-profiles.json")


def now_ts() -> int:
    return int(time.time())


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def get_access_token(auto_refresh=True):
    if auto_refresh:
        cmd = ["python3", "scripts/raindrop_oauth.py", "token", "--auto-refresh"]
        out = subprocess.check_output(cmd, cwd=os.path.expanduser("~/.openclaw/workspace"), text=True).strip()
        if out:
            return out
    s = load_json(SECRETS_PATH, {})
    return s.get("RAINDROP_ACCESS_TOKEN") or s.get("RAINDROP_SECRET")


def api(method, path, token, payload=None):
    url = f"https://api.raindrop.io/rest/v1{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "openclaw-raindrop-sync/1.0",
    }
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(url, method=method, headers=headers, data=data)
    with urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def classify_with_llm(raindrop, collections):
    profiles = load_json(AUTH_PROFILES_PATH, {}).get("profiles", {})
    anthropic = profiles.get("anthropic:default") or {}
    api_key = anthropic.get("key")
    if not api_key:
        raise RuntimeError("Anthropic API key not found")

    available = []
    collection_map = {}
    for c in collections:
        cid = c.get("_id")
        title = c.get("title", "")
        if cid is None or not title:
            continue
        available.append({"id": cid, "name": title})
        collection_map[cid] = title

    link = raindrop.get("link", "")
    domain = urlparse(link).netloc or ""
    tags = raindrop.get("tags") or []
    prompt = (
        "以下のブックマークを、利用可能なコレクションの中から最も適切な1つに分類してください。\n"
        "合うものがなければ collection_id は -1 にしてください。\n"
        "必ず JSON オブジェクトのみを返してください。余計な説明やコードブロックは禁止です。\n"
        '形式: {"collection_id": <int>, "reason": "<brief reason>"}\n\n'
        "ブックマーク情報:\n"
        f"- title: {raindrop.get('title', '')}\n"
        f"- url: {link}\n"
        f"- domain: {domain}\n"
        f"- tags: {json.dumps(tags, ensure_ascii=False)}\n\n"
        "利用可能なコレクション:\n"
        f"{json.dumps(available, ensure_ascii=False)}\n"
    )

    payload = {
        "model": "claude-3-haiku-20240307",
        "max_tokens": 150,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
    }
    req = Request(
        "https://api.anthropic.com/v1/messages",
        method="POST",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        data=json.dumps(payload).encode("utf-8"),
    )
    with urlopen(req, timeout=10) as r:
        response = json.loads(r.read().decode("utf-8"))

    text_parts = []
    for block in response.get("content", []):
        if block.get("type") == "text":
            text_parts.append(block.get("text", ""))
    content = "\n".join(text_parts).strip()
    if not content:
        raise ValueError("Empty Anthropic response")

    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in Anthropic response")
    parsed = json.loads(match.group(0))

    collection_id = parsed.get("collection_id")
    if not isinstance(collection_id, int):
        raise ValueError("Invalid collection_id in Anthropic response")
    if collection_id != -1 and collection_id not in collection_map:
        raise ValueError("Unknown collection_id in Anthropic response")

    if collection_id == -1:
        return -1, "llm:no_match"
    return collection_id, f"llm:{collection_map[collection_id]}"


def fallback_choose_collection(raindrop, collections):
    title = norm(raindrop.get("title", ""))
    link = raindrop.get("link", "")
    domain = norm(urlparse(link).netloc)
    tags = " ".join((raindrop.get("tags") or [])).lower()
    text = f"{title} {domain} {tags}"

    # Score against existing collection titles (no hardcoded IDs)
    scored = []
    for c in collections:
        cid = c.get("_id")
        ctitle = norm(c.get("title", ""))
        if cid in (None, -1) or not ctitle:
            continue
        score = 0
        for token in re.split(r"[^a-z0-9ぁ-んァ-ヶー一-龠]+", ctitle):
            if len(token) < 2:
                continue
            if token in text:
                score += max(1, len(token))
        # heuristic boosts
        if any(x in ctitle for x in ["video", "動画", "youtube"]) and "youtube" in domain:
            score += 8
        if any(x in ctitle for x in ["dev", "開発", "github", "tech", "技術"]) and any(x in domain for x in ["github", "qiita", "zenn", "dev.to"]):
            score += 8
        if any(x in ctitle for x in ["news", "ニュース"]) and any(x in domain for x in ["news", "nikkei", "bbc", "reuters"]):
            score += 6
        if score > 0:
            scored.append((score, cid, c.get("title", "")))

    if scored:
        scored.sort(reverse=True)
        top = scored[0]
        return top[1], f"scored:{top[2]}"

    # Fallback to inbox-like collection if exists
    for c in collections:
        t = norm(c.get("title", ""))
        if t in ("inbox", "受信箱", "未分類", "unsorted"):
            return c.get("_id"), "fallback_inbox"

    # Last fallback: keep unsorted
    return -1, "no_match"


def choose_collection(raindrop, collections):
    # Keep existing assignment if present and not unsorted
    current = (raindrop.get("collection") or {}).get("$id")
    if current not in (None, -1):
        return current, "already_assigned"

    try:
        return classify_with_llm(raindrop, collections)
    except Exception:
        collection_id, reason = fallback_choose_collection(raindrop, collections)
        return collection_id, f"heuristic:{reason}"


def main():
    ap = argparse.ArgumentParser(description="Raindrop new-bookmark sync + auto-collection assignment + Obsidian queue")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--state", default=STATE_PATH)
    ap.add_argument("--pending", default=PENDING_PATH)
    args = ap.parse_args()

    token = get_access_token(auto_refresh=True)
    if not token:
        raise SystemExit("No RAINDROP token available")

    state = load_json(args.state, {"seen": [], "lastRun": None})
    seen = set(state.get("seen", []))

    collections = api("GET", "/collections", token).get("items", [])
    items = api("GET", f"/raindrops/0?perpage={args.limit}&sort=-created", token).get("items", [])

    new_items = []
    for it in items:
        rid = it.get("_id")
        if rid in seen:
            continue

        target_id, reason = choose_collection(it, collections)
        current_id = (it.get("collection") or {}).get("$id", -1)
        moved = False

        if current_id in (None, -1) and target_id not in (None, -1):
            api("PUT", f"/raindrop/{rid}", token, {"collection": {"$id": target_id}})
            moved = True

        new_items.append({
            "id": rid,
            "title": it.get("title"),
            "link": it.get("link"),
            "created": it.get("created"),
            "currentCollectionId": current_id,
            "assignedCollectionId": target_id,
            "assignmentReason": reason,
            "moved": moved,
            "tags": it.get("tags", []),
        })
        seen.add(rid)

    pending = load_json(args.pending, [])
    pending.extend([x for x in new_items if x.get("link")])

    save_json(args.pending, pending)
    save_json(args.state, {
        "seen": list(seen)[-5000:],
        "lastRun": datetime.now(timezone.utc).isoformat(),
    })

    print(json.dumps({
        "ok": True,
        "newCount": len(new_items),
        "queuedForObsidian": len([x for x in new_items if x.get("link")]),
        "pendingPath": args.pending,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
