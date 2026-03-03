#!/usr/bin/env python3
import html
import json
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

PENDING_PATH = os.path.expanduser("~/.openclaw/workspace/memory/raindrop-obsidian-pending.json")
SECRETS_PATH = os.path.expanduser("~/.openclaw/secrets.json")
VAULT_ARTICLES = os.path.expanduser("~/ドキュメント/openclaw/articles")


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def api_get(path, token):
    req = Request(
        f"https://api.raindrop.io/rest/v1{path}",
        headers={"Authorization": f"Bearer {token}", "User-Agent": "openclaw-raindrop-obsidian/1.0"},
    )
    with urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def web_fetch_markdown(url: str) -> str:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=40) as r:
        raw = r.read().decode("utf-8", "replace")
    return raw


def extract_text(raw: str) -> str:
    # Remove scripts/styles/comments first
    raw = re.sub(r"<script[\s\S]*?</script>", " ", raw, flags=re.IGNORECASE)
    raw = re.sub(r"<style[\s\S]*?</style>", " ", raw, flags=re.IGNORECASE)
    raw = re.sub(r"<!--([\s\S]*?)-->", " ", raw)

    # Preserve rough paragraph boundaries
    raw = re.sub(r"</(p|div|section|article|h[1-6]|li|br|tr)>", "\n", raw, flags=re.IGNORECASE)

    # Strip tags and decode entities
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)

    # Normalize lines while keeping newlines
    lines = []
    for ln in text.splitlines():
        ln = re.sub(r"\s+", " ", ln).strip()
        if ln:
            lines.append(ln)

    # de-duplicate consecutive same lines
    deduped = []
    for ln in lines:
        if not deduped or deduped[-1] != ln:
            deduped.append(ln)

    return "\n".join(deduped)


def detect_lang(text: str) -> str:
    sample = text[:4000]
    ja_chars = re.findall(r"[ぁ-んァ-ヶ一-龠]", sample)
    latin_chars = re.findall(r"[A-Za-z]", sample)
    if len(ja_chars) >= max(40, int(len(latin_chars) * 0.25)):
        return "ja"
    return "other"


def translate_to_japanese(text: str) -> str:
    # Unofficial Google endpoint. If it fails, caller should fallback to original text.
    chunks = []
    size = 1800
    for i in range(0, len(text), size):
        chunks.append(text[i:i + size])

    out = []
    for ch in chunks:
        q = quote(ch)
        url = (
            "https://translate.googleapis.com/translate_a/single"
            "?client=gtx&sl=auto&tl=ja&dt=t&q=" + q
        )
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        translated = "".join(seg[0] for seg in data[0] if seg and seg[0])
        out.append(translated)
        time.sleep(0.2)

    return "\n".join(out).strip()


def sanitize_filename(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|]', "", s)
    s = re.sub(r"\s+", "-", s.strip())
    return s[:120] or "untitled"


def summarize(text: str):
    # Split by punctuation-like boundaries for Japanese/English mixed text
    chunks = re.split(r"(?<=[。！？.!?])\s+", text)
    chunks = [c.strip() for c in chunks if c and len(c.strip()) >= 40]
    # Filter obvious boilerplate fragments
    bad = ["DOCTYPE", "<meta", "cookie", "JavaScript", "利用規約", "プライバシー", "All rights reserved"]
    cleaned = []
    for c in chunks:
        if any(b.lower() in c.lower() for b in bad):
            continue
        cleaned.append(c)
    picks = cleaned[:3]
    if len(picks) < 3:
        # fallback: take long spans from raw text
        spans = re.findall(r".{60,180}", text)
        for s in spans:
            if len(picks) >= 3:
                break
            if not any(b.lower() in s.lower() for b in bad):
                picks.append(s.strip())
    if len(picks) < 3:
        picks += ["(要約抽出が不十分なため本文確認推奨)"] * (3 - len(picks))
    return picks[:3]


def main():
    pending = load_json(PENDING_PATH, [])
    if not pending:
        print("NO_PENDING")
        return

    secrets = load_json(SECRETS_PATH, {})
    token = secrets.get("RAINDROP_ACCESS_TOKEN") or secrets.get("RAINDROP_SECRET")
    if not token:
        raise SystemExit("No RAINDROP token")

    collections = api_get("/collections", token).get("items", [])
    c_map = {c.get("_id"): c.get("title", "(unknown)") for c in collections}

    os.makedirs(VAULT_ARTICLES, exist_ok=True)
    date = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")

    remaining = []
    for it in pending:
        try:
            title = it.get("title") or "Untitled"
            url = it.get("link")
            if not url:
                continue
            coll = c_map.get(it.get("assignedCollectionId"), "(未分類)")

            raw = web_fetch_markdown(url)
            text = extract_text(raw)
            bullets = summarize(text)
            stem = f"{date}-{sanitize_filename(title)}"

            summary_path = os.path.join(VAULT_ARTICLES, f"{stem}-summary.md")
            ja_path = os.path.join(VAULT_ARTICLES, f"{stem}-ja.md")

            with open(summary_path, "w", encoding="utf-8") as f:
                f.write(
                    f"---\nsource_url: \"{url}\"\ntitle: \"{title}\"\ncaptured_at: \"{date}\"\ntype: \"article-summary\"\n---\n\n"
                    "# 要約\n\n## 3行サマリー\n"
                    + "\n".join([f"- {b}" for b in bullets])
                    + "\n\n## 重要ポイント\n- Realtime連携向けに保存\n\n## 次に読むべき人\n- 関連分野の実装担当\n"
                )

            src_lang = detect_lang(text)
            ja_text = text
            translated = False
            if src_lang != "ja":
                try:
                    ja_text = translate_to_japanese(text)
                    translated = True
                except Exception:
                    ja_text = text
                    translated = False

            with open(ja_path, "w", encoding="utf-8") as f:
                f.write(
                    f"---\nsource_url: \"{url}\"\ntitle: \"{title}\"\ncaptured_at: \"{date}\"\ntype: \"article-ja\"\n"
                    f"source_lang: \"{src_lang}\"\ntranslated_to_ja: {str(translated).lower()}\n---\n\n"
                    f"# {title}\n\n"
                    "## 本文（保存）\n\n"
                    f"{ja_text}\n"
                )

            # chat post template
            print(f"TITLE: {title}")
            print(f"COLLECTION: {coll}")
            print("SUMMARY:")
            for b in bullets:
                print(f"- {b}")
            print("---")
        except Exception:
            remaining.append(it)

    save_json(PENDING_PATH, remaining)


if __name__ == "__main__":
    main()
