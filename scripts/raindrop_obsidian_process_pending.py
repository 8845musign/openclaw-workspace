#!/usr/bin/env python3
import html
import json
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote
from urllib.request import Request, urlopen

PENDING_PATH = os.path.expanduser("~/.openclaw/workspace/memory/raindrop-obsidian-pending.json")
SECRETS_PATH = os.path.expanduser("~/.openclaw/secrets.json")
VAULT_ARTICLES = os.path.expanduser("~/ドキュメント/openclaw/articles")

NOISE_HINT_RE = re.compile(
    r"(nav|menu|header|footer|sidebar|breadcrumb|social|share|related|recommend|promo|advert|ad-|banner|cookie|comment|pager|pagination)",
    re.IGNORECASE,
)


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


def web_fetch_html(url: str) -> str:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def extract_article_markdown(raw: str) -> str:
    """Extract likely article body and convert to Markdown.
    Prefers BeautifulSoup + markdownify when available, with regex fallback.
    """
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return fallback_markdown(raw)

    soup = BeautifulSoup(raw, "html.parser")

    for t in soup(["script", "style", "noscript", "iframe", "svg", "canvas", "form", "button", "input"]):
        t.decompose()

    for tag_name in ["nav", "header", "footer", "aside"]:
        for t in soup.find_all(tag_name):
            t.decompose()

    # Remove noise by id/class hints
    for t in soup.find_all(True):
        try:
            if getattr(t, "attrs", None) is None:
                continue
            attrs = " ".join(
                [
                    " ".join(t.get("class", [])) if t.get("class") else "",
                    t.get("id", "") or "",
                    t.get("role", "") or "",
                    t.get("aria-label", "") or "",
                ]
            )
            if attrs and NOISE_HINT_RE.search(attrs):
                t.decompose()
        except Exception:
            continue

    # Pick the most content-dense root
    candidates = []
    for c in soup.find_all(["article", "main", "section", "div"]):
        txt = c.get_text(" ", strip=True)
        if len(txt) < 400:
            continue
        p_count = len(c.find_all(["p", "li", "h1", "h2", "h3"]))
        score = len(txt) + p_count * 200
        candidates.append((score, c))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        root = candidates[0][1]
    else:
        root = soup.body or soup

    # Convert to markdown
    try:
        from markdownify import markdownify as md

        markdown = md(str(root), heading_style="ATX", bullets="-")
    except Exception:
        markdown = root.get_text("\n", strip=True)

    cleaned = cleanup_markdown(markdown)
    if cleaned:
        return cleaned

    # last resort: keep any text rather than empty output
    return cleanup_markdown((soup.body or soup).get_text("\n", strip=True))


def fallback_markdown(raw: str) -> str:
    raw = re.sub(r"<script[\s\S]*?</script>", " ", raw, flags=re.IGNORECASE)
    raw = re.sub(r"<style[\s\S]*?</style>", " ", raw, flags=re.IGNORECASE)
    raw = re.sub(r"<!--([\s\S]*?)-->", " ", raw)
    raw = re.sub(r"</(p|div|section|article|h[1-6]|li|br|tr)>", "\n", raw, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    lines = []
    for ln in text.splitlines():
        ln = re.sub(r"\s+", " ", ln).strip()
        if ln and not NOISE_HINT_RE.search(ln[:80]):
            lines.append(ln)
    return cleanup_markdown("\n\n".join(lines))


def cleanup_markdown(md_text: str) -> str:
    md_text = md_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in md_text.split("\n")]

    cleaned = []
    for ln in lines:
        if not ln.strip():
            cleaned.append("")
            continue
        short = ln.strip()
        # lightweight boilerplate pruning
        if len(short) <= 60 and NOISE_HINT_RE.search(short):
            continue
        cleaned.append(short)

    out = "\n".join(cleaned)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


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
        chunks.append(text[i : i + size])

    out = []
    for ch in chunks:
        q = quote(ch)
        url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=ja&dt=t&q=" + q
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
    chunks = re.split(r"(?<=[。！？.!?])\s+", text)
    chunks = [c.strip() for c in chunks if c and len(c.strip()) >= 40]
    bad = ["DOCTYPE", "<meta", "cookie", "JavaScript", "利用規約", "プライバシー", "All rights reserved"]
    cleaned = []
    for c in chunks:
        if any(b.lower() in c.lower() for b in bad):
            continue
        cleaned.append(c)
    picks = cleaned[:3]
    if len(picks) < 3:
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

            raw = web_fetch_html(url)
            markdown_body = extract_article_markdown(raw)
            bullets = summarize(markdown_body)
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

            src_lang = detect_lang(markdown_body)
            ja_text = markdown_body
            translated = False
            if src_lang != "ja":
                try:
                    ja_text = translate_to_japanese(markdown_body)
                    translated = True
                except Exception:
                    ja_text = markdown_body
                    translated = False

            with open(ja_path, "w", encoding="utf-8") as f:
                f.write(
                    f"---\nsource_url: \"{url}\"\ntitle: \"{title}\"\ncaptured_at: \"{date}\"\ntype: \"article-ja\"\n"
                    f"source_lang: \"{src_lang}\"\ntranslated_to_ja: {str(translated).lower()}\n---\n\n"
                    f"# {title}\n\n"
                    "## 本文（保存）\n\n"
                    f"{ja_text}\n"
                )

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
