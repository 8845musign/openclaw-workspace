#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


JST = ZoneInfo("Asia/Tokyo")
WORKSPACE = Path("/home/hiroki-yokouchi/.openclaw/workspace")
STATE_DIR = Path(os.environ.get("PDF_DIGEST_DIR", str(WORKSPACE / "pdf-digest")))
OPENCLAW_STATE = Path("/home/hiroki-yokouchi/.openclaw")
OPENCLAW_BIN = os.environ.get("OPENCLAW_BIN") or shutil.which("openclaw")
MESSAGE_ACTION_BIN = WORKSPACE / "scripts" / "openclaw_message_action.mjs"
DEFAULT_TARGET_ENV = "PDF_DIGEST_SLACK_TARGET"
DEFAULT_OBSIDIAN_EXPORT_DIR = Path(
    os.environ.get("PDF_DIGEST_OBSIDIAN_EXPORT_DIR", "/home/hiroki-yokouchi/ドキュメント/openclaw/pdf-digest")
)
BASE_CHUNK_MAX = int(os.environ.get("PDF_DIGEST_BASE_CHUNK_MAX", "8000"))
MAX_CHUNK_MAX = int(os.environ.get("PDF_DIGEST_MAX_CHUNK_MAX", "15000"))
TARGET_DAYS = int(os.environ.get("PDF_DIGEST_TARGET_DAYS", "30"))
DEFAULT_CHUNK_STRATEGY = os.environ.get("PDF_DIGEST_CHUNK_STRATEGY", "paragraph")
MESSAGE_MAX = int(os.environ.get("PDF_DIGEST_MESSAGE_MAX", "7800"))


class PdfDigestError(Exception):
    pass


def require_openclaw_bin() -> str:
    if OPENCLAW_BIN:
        return OPENCLAW_BIN
    raise PdfDigestError("openclaw コマンドがPATHで見つかりません。")


@dataclass
class SendResult:
    summary: str
    message: str


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_dirs() -> None:
    for name in ["inbox", "archive", "text", "chunks", "history"]:
        (STATE_DIR / name).mkdir(parents=True, exist_ok=True)


def state_path() -> Path:
    return STATE_DIR / "state.json"


def load_state() -> dict[str, Any]:
    path = state_path()
    if not path.exists():
        return {"version": 1, "documents": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("version", 1)
    data.setdefault("documents", [])
    return data


def save_state(state: dict[str, Any]) -> None:
    ensure_dirs()
    path = state_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def append_history(doc: dict[str, Any], event: dict[str, Any]) -> None:
    ensure_dirs()
    event = {"at": now_iso(), **event}
    Path(doc["paths"]["history"]).parent.mkdir(parents=True, exist_ok=True)
    with Path(doc["paths"]["history"]).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def normalize_ws(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def slugify(value: str, max_length: int = 80) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return (slug or "pdf")[:max_length].strip("-") or "pdf"


def markdown_fence(text: str, language: str = "text") -> str:
    fence = "```"
    while fence in text:
        fence += "`"
    return f"{fence}{language}\n{text.rstrip()}\n{fence}"


def require_pymupdf():
    try:
        import fitz  # type: ignore
    except ModuleNotFoundError as exc:
        raise PdfDigestError(
            "PyMuPDF が未インストールです。実PDF抽出には `python3 -m pip install pymupdf` が必要です。"
        ) from exc
    return fitz


def extract_pdf_text(pdf_path: Path, dry_run: bool = False) -> str:
    try:
        fitz = require_pymupdf()
    except PdfDigestError:
        if dry_run:
            return (
                "dry-run placeholder text: PyMuPDF is not installed, so this mock text "
                "is used only to verify state/chunk/history creation.\n\n"
                f"source file: {pdf_path.name}\n"
            ) * 80
        raise
    parts: list[str] = []
    with fitz.open(str(pdf_path)) as doc:
        for index, page in enumerate(doc, start=1):
            page_text = normalize_ws(page.get_text("text"))
            if page_text:
                parts.append(f"[page {index}]\n{page_text}")
    text = normalize_ws("\n\n".join(parts))
    if not text:
        raise PdfDigestError("PDFから本文を抽出できませんでした。OCRはv1対象外です。")
    return text


def effective_chunk_max(text_length: int) -> int:
    if BASE_CHUNK_MAX <= 0:
        raise PdfDigestError("PDF_DIGEST_BASE_CHUNK_MAX は1以上にしてください。")
    if MAX_CHUNK_MAX < BASE_CHUNK_MAX:
        raise PdfDigestError("PDF_DIGEST_MAX_CHUNK_MAX は PDF_DIGEST_BASE_CHUNK_MAX 以上にしてください。")
    if TARGET_DAYS <= 0:
        raise PdfDigestError("PDF_DIGEST_TARGET_DAYS は1以上にしてください。")
    required = (max(1, text_length) + TARGET_DAYS - 1) // TARGET_DAYS
    return min(MAX_CHUNK_MAX, max(BASE_CHUNK_MAX, required))


def split_chunk_oversize(part: str, limit: int) -> list[str]:
    if len(part) <= limit:
        return [part]
    return [part[i : i + limit] for i in range(0, len(part), limit)]


def resolve_chunk_strategy(strategy: str | None) -> str:
    value = (strategy or DEFAULT_CHUNK_STRATEGY).strip().lower()
    if value != "paragraph":
        raise PdfDigestError(f"未知のチャンク戦略です: {value}")
    return value


def chunk_text(text: str, strategy: str | None = None, chunk_max: int | None = None) -> list[dict[str, Any]]:
    resolved = resolve_chunk_strategy(strategy)
    max_chars = chunk_max or effective_chunk_max(len(text))
    if resolved == "paragraph":
        return chunk_text_paragraph(text, max_chars)
    raise PdfDigestError(f"未知のチャンク戦略です: {resolved}")


def chunk_text_paragraph(text: str, chunk_max: int) -> list[dict[str, Any]]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidates = split_chunk_oversize(paragraph, chunk_max)
        for part in candidates:
            sep = "\n\n" if current else ""
            if current and len(current) + len(sep) + len(part) > chunk_max:
                chunks.append(current)
                current = part
            else:
                current = f"{current}{sep}{part}"
    if current:
        chunks.append(current)
    if not chunks:
        chunks = [text[:chunk_max]]
    return [{"index": i, "text": value} for i, value in enumerate(chunks)]


def short_title(path: Path, title: str | None) -> str:
    value = (title or path.stem).strip()
    return value[:120] if value else path.name


def new_document_id(pdf_path: Path, source_file_id: str | None, source_message_ts: str | None) -> str:
    seed = "|".join([str(pdf_path.resolve()), source_file_id or "", source_message_ts or "", now_iso()])
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def find_doc(state: dict[str, Any], short_id: str) -> dict[str, Any]:
    matches = [
        doc
        for doc in state["documents"]
        if doc.get("short_id") == short_id or str(doc.get("id", "")).startswith(short_id)
    ]
    if len(matches) != 1:
        raise PdfDigestError(f"PDFが見つかりません: {short_id}")
    return matches[0]


def source_already_registered(state: dict[str, Any], file_id: str | None, message_ts: str | None) -> bool:
    if not file_id and not message_ts:
        return False
    for doc in state["documents"]:
        source = doc.get("source", {})
        if file_id and source.get("file_id") == file_id:
            return True
        if message_ts and source.get("message_ts") == message_ts and source.get("file_id") == file_id:
            return True
    return False


def build_doc(pdf_path: Path, title: str, source: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    ensure_dirs()
    doc_id = new_document_id(pdf_path, source.get("file_id"), source.get("message_ts"))
    short_id = doc_id[:8]
    stored_pdf = STATE_DIR / "inbox" / f"{doc_id}.pdf"
    text_path = STATE_DIR / "text" / f"{doc_id}.txt"
    chunks_path = STATE_DIR / "chunks" / f"{doc_id}.json"
    history_path = STATE_DIR / "history" / f"{doc_id}.jsonl"
    return (
        {
            "id": doc_id,
            "short_id": short_id,
            "title": title,
            "status": "active",
            "source": source,
            "paths": {
                "pdf": str(stored_pdf),
                "text": str(text_path),
                "chunks": str(chunks_path),
                "history": str(history_path),
            },
            "next_chunk_index": 0,
            "total_chunks": 0,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "last_sent_at": None,
            "last_error": None,
            "pending_delivery": None,
        },
        [],
        doc_id,
    )


def register_downloaded(args: argparse.Namespace) -> int:
    pdf_path = Path(args.pdf_path).expanduser()
    if not pdf_path.exists():
        raise PdfDigestError(f"PDFが見つかりません: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise PdfDigestError("PDFファイルを指定してください。")
    ensure_dirs()
    state = load_state()
    if source_already_registered(state, args.source_file_id, args.source_message_ts):
        raise PdfDigestError("このPDFはすでに登録済みです。")

    title = short_title(pdf_path, args.title)
    source = {
        "type": args.source_type,
        "file_id": args.source_file_id,
        "message_ts": args.source_message_ts,
    }
    doc, _, _ = build_doc(pdf_path, title, source)
    text = extract_pdf_text(pdf_path, dry_run=args.dry_run)
    chunks = chunk_text(text, strategy=getattr(args, "chunk_strategy", None))
    shutil.copy2(pdf_path, doc["paths"]["pdf"])
    Path(doc["paths"]["text"]).write_text(text + "\n", encoding="utf-8")
    Path(doc["paths"]["chunks"]).write_text(json.dumps(chunks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    doc["total_chunks"] = len(chunks)
    state["documents"].append(doc)
    save_state(state)
    append_history(doc, {"event": "registered", "chunk_count": len(chunks), "dry_run": args.dry_run})

    try:
        send_next_chunk(
            state,
            doc,
            chunks,
            resolve_target(),
            args.dry_run,
            export_obsidian=getattr(args, "export_obsidian", False),
            export_dir=Path(args.export_dir) if getattr(args, "export_dir", None) else None,
        )
        save_state(state)
    except Exception as exc:
        doc["last_error"] = str(exc)
        doc["updated_at"] = now_iso()
        append_history(doc, {"event": "initial_send_failed", "error": str(exc), "dry_run": args.dry_run})
        save_state(state)

    print(
        f"登録しました: {doc['short_id']} / {status_label(doc['status']) if doc['status'] != 'done' else '完了'} / "
        f"{doc['next_chunk_index']}/{doc['total_chunks']} / {doc['title']}"
    )
    return 0


def status_label(status: str) -> str:
    return {"active": "配信中", "paused": "停止中"}.get(status, status)


def list_docs(_: argparse.Namespace) -> int:
    state = load_state()
    docs = [doc for doc in state["documents"] if doc.get("status") in {"active", "paused"}]
    if not docs:
        print("登録中のPDFはありません。")
        return 0
    for doc in docs:
        print(
            f"{doc['short_id']} / {status_label(doc['status'])} / "
            f"{doc.get('next_chunk_index', 0)}/{doc.get('total_chunks', 0)} / {doc.get('title', '')}"
        )
    return 0


def transition_doc(args: argparse.Namespace, status: str) -> int:
    state = load_state()
    doc = find_doc(state, args.short_id)
    doc["status"] = status
    doc["updated_at"] = now_iso()
    doc["last_error"] = None
    append_history(doc, {"event": status, "dry_run": args.dry_run})
    save_state(state)
    print(f"{doc['short_id']} / {status_label(status) if status != 'archived' else 'アーカイブ'} / {doc['title']}")
    return 0


def archive_doc(args: argparse.Namespace) -> int:
    return transition_doc(args, "archived")


def load_chunks(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return json.loads(Path(doc["paths"]["chunks"]).read_text(encoding="utf-8"))


def resolve_target() -> str:
    env_target = os.environ.get(DEFAULT_TARGET_ENV)
    if env_target:
        return env_target
    config_path = OPENCLAW_STATE / "openclaw.json"
    data = json.loads(config_path.read_text(encoding="utf-8"))
    target = data.get("agents", {}).get("defaults", {}).get("heartbeat", {}).get("to")
    if not target:
        raise PdfDigestError("Slack通知先を解決できません。PDF_DIGEST_SLACK_TARGET を設定してください。")
    return str(target)


def slack_read_target(target: str) -> str:
    env_target = os.environ.get("PDF_DIGEST_SLACK_READ_TARGET")
    if env_target:
        return env_target
    native_channel_id = resolve_native_dm_channel_id(target)
    if native_channel_id:
        return f"channel:{native_channel_id}"
    value = target.strip()
    user_match = re.match(r"^(?:user:|slack:)?([UW][A-Z0-9]{8,})$", value, flags=re.IGNORECASE)
    if user_match:
        return f"direct:{user_match.group(1)}"
    return value


def resolve_native_dm_channel_id(target: str) -> str | None:
    value = target.strip()
    user_match = re.match(r"^(?:user:|slack:)?([UW][A-Z0-9]{8,})$", value, flags=re.IGNORECASE)
    if not user_match:
        return None
    user_id = user_match.group(1).upper()
    sessions_path = OPENCLAW_STATE / "agents" / "main" / "sessions" / "sessions.json"
    if not sessions_path.exists():
        return None
    try:
        sessions = json.loads(sessions_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for session in sessions.values():
        if not isinstance(session, dict):
            continue
        origin = session.get("origin")
        if not isinstance(origin, dict):
            continue
        if str(origin.get("provider", "")).lower() != "slack":
            continue
        if str(origin.get("from", "")).lower() != f"slack:{user_id.lower()}":
            continue
        native_id = str(origin.get("nativeChannelId") or "").strip()
        if native_id:
            return native_id
    return None


def run_json(command: list[str]) -> Any:
    proc = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        raise PdfDigestError(proc.stderr.strip() or proc.stdout.strip() or f"command failed: {' '.join(command)}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise PdfDigestError(f"JSONとして読めません: {' '.join(command)}") from exc


def extract_text_result(payload: Any) -> str:
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, list):
        values = [extract_text_result(item) for item in payload]
        return "\n".join(value for value in values if value).strip()
    if isinstance(payload, dict):
        path = payload.get("path")
        if isinstance(path, str) and path.strip():
            return path.strip()
        for key in ["result", "payload", "payloads", "data"]:
            value = payload.get(key)
            text = extract_text_result(value)
            if text:
                return text
        for key in ["message", "text", "reply", "content"]:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        summary = payload.get("summary")
        if isinstance(summary, str) and summary.strip() and summary.strip().lower() != "completed":
            return summary.strip()
    return ""


def extract_path_result(payload: Any) -> Path | None:
    text = extract_text_result(payload)
    if not text:
        return None
    for line in reversed(text.splitlines()):
        candidate = line.strip().strip("`")
        if candidate.startswith("{"):
            try:
                nested = json.loads(candidate)
            except json.JSONDecodeError:
                pass
            else:
                nested_path = extract_path_result(nested)
                if nested_path:
                    return nested_path
        if candidate.lower().endswith(".pdf"):
            return Path(candidate)
    return None


def summarize_chunk(title: str, index: int, total: int, chunk_text_value: str, dry_run: bool) -> str:
    if dry_run:
        return f"dry-run要約: {title} の {index + 1}/{total} チャンクを要約した想定です。"
    prompt = textwrap.dedent(
        f"""
        次のPDF本文チャンクを日本語で500〜1000文字程度に要約してください。
        コードサンプルが重要な場合は1200文字程度まで使ってかまいません。
        出力は要約本文だけにしてください。「次回」「要点」「用語・前提」などの見出しは不要です。
        技術書のコードサンプルは無視しないでください。
        重要なコードサンプルがある場合は、最大3件まで短く取り上げてください。
        コードを取り上げる場合だけ、本文要約の後に「コードサンプル:」という見出しを付けてください。
        各コードサンプルは、何を示すコードか、読むべきポイント、必要最小限の短い抜粋を含めてください。
        長いコード全文は載せず、理解に必要な識別子・関数名・設定値・制御フローだけを残してください。
        コードサンプルが本文理解の中心なのに抜粋しきれない場合は、原文参照が必要だと明記してください。

        PDF: {title}
        チャンク: {index + 1}/{total}

        本文:
        {chunk_text_value}
        """
    ).strip()
    result = run_json(
        [
            require_openclaw_bin(),
            "agent",
            "--agent",
            "main",
            "--message",
            prompt,
            "--json",
            "--timeout",
            "600",
        ]
    )
    text = extract_text_result(result)
    if text:
        return text
    raise PdfDigestError("要約結果を読み取れませんでした。")


def looks_japanese(text: str) -> bool:
    sample = re.sub(r"\s+", "", text[:8000])
    if not sample:
        return True
    kana = len(re.findall(r"[\u3040-\u30ff]", sample))
    cjk = len(re.findall(r"[\u4e00-\u9fff]", sample))
    return kana >= 12 or (kana + cjk) / max(1, len(sample)) >= 0.12


def translate_chunk_to_japanese(title: str, index: int, total: int, chunk_text_value: str) -> str:
    prompt = textwrap.dedent(
        f"""
        次のPDF本文チャンクを日本語に翻訳してください。
        コードブロック、コード片、識別子、関数名、設定値は翻訳せず、原文のまま残してください。
        出力は翻訳本文だけにしてください。

        PDF: {title}
        チャンク: {index + 1}/{total}

        本文:
        {chunk_text_value}
        """
    ).strip()
    result = run_json(
        [
            require_openclaw_bin(),
            "agent",
            "--agent",
            "main",
            "--message",
            prompt,
            "--json",
            "--timeout",
            "600",
        ]
    )
    text = extract_text_result(result)
    if text:
        return text
    raise PdfDigestError("翻訳結果を読み取れませんでした。")


def obsidian_doc_dir(base_dir: Path, doc: dict[str, Any]) -> Path:
    return base_dir / f"{slugify(str(doc.get('title', 'pdf')))}-{doc['short_id']}"


def chunk_dir_name(index: int) -> str:
    return f"{index + 1:04d}"


def markdown_frontmatter(data: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in data.items():
        encoded = json.dumps(value, ensure_ascii=False)
        lines.append(f"{key}: {encoded}")
    lines.append("---")
    return "\n".join(lines)


def write_obsidian_index(doc_dir: Path, doc: dict[str, Any], total: int) -> None:
    title = str(doc.get("title", doc.get("short_id", "PDF")))
    lines = [
        markdown_frontmatter(
            {
                "pdf_digest_id": doc.get("id"),
                "short_id": doc.get("short_id"),
                "source_pdf": title,
                "total_chunks": total,
                "updated_at": now_iso(),
            }
        ),
        "",
        f"# {title}",
        "",
        f"- PDF Digest ID: `{doc.get('id')}`",
        f"- Short ID: `{doc.get('short_id')}`",
        f"- Total chunks: `{total}`",
        "",
        "## Chunks",
        "",
    ]
    chunks_dir = doc_dir / "chunks"
    chunk_names = sorted(path.name for path in chunks_dir.iterdir() if path.is_dir()) if chunks_dir.exists() else []
    for name in chunk_names:
        chunk_path = chunks_dir / name
        links = []
        if (chunk_path / "summary.ja.md").exists():
            links.append(f"[[chunks/{name}/summary.ja|要約]]")
        if (chunk_path / "original.md").exists():
            links.append(f"[[chunks/{name}/original|原文]]")
        if (chunk_path / "translation.ja.md").exists():
            links.append(f"[[chunks/{name}/translation.ja|翻訳]]")
        if links:
            lines.append(f"- {name}: {' / '.join(links)}")
    if not chunk_names:
        lines.append("- まだ書き出し済みチャンクはありません。")
    (doc_dir / "index.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def export_obsidian_chunk(
    doc: dict[str, Any],
    chunk_text_value: str,
    summary: str,
    index: int,
    total: int,
    export_dir: Path,
    dry_run: bool = False,
) -> Path:
    doc_dir = obsidian_doc_dir(export_dir.expanduser(), doc)
    chunk_dir = doc_dir / "chunks" / chunk_dir_name(index)
    if dry_run:
        print(f"[dry-run] export obsidian chunk={index + 1}/{total} dir={chunk_dir}")
        return chunk_dir

    chunk_dir.mkdir(parents=True, exist_ok=True)
    title = str(doc.get("title", doc.get("short_id", "PDF")))
    common = {
        "pdf_digest_id": doc.get("id"),
        "short_id": doc.get("short_id"),
        "chunk": index + 1,
        "total_chunks": total,
        "source_pdf": title,
        "updated_at": now_iso(),
    }
    (chunk_dir / "original.md").write_text(
        "\n".join(
            [
                markdown_frontmatter({**common, "kind": "original"}),
                "",
                f"# 原文 chunk {index + 1}/{total}",
                "",
                markdown_fence(chunk_text_value),
                "",
            ]
        ),
        encoding="utf-8",
    )
    (chunk_dir / "summary.ja.md").write_text(
        "\n".join(
            [
                markdown_frontmatter({**common, "kind": "summary", "language": "ja"}),
                "",
                f"# 要約 chunk {index + 1}/{total}",
                "",
                summary.strip(),
                "",
            ]
        ),
        encoding="utf-8",
    )
    if not looks_japanese(chunk_text_value):
        translation = translate_chunk_to_japanese(title, index, total, chunk_text_value)
        (chunk_dir / "translation.ja.md").write_text(
            "\n".join(
                [
                    markdown_frontmatter({**common, "kind": "translation", "language": "ja"}),
                    "",
                    f"# 翻訳 chunk {index + 1}/{total}",
                    "",
                    translation.strip(),
                    "",
                ]
            ),
            encoding="utf-8",
        )
    write_obsidian_index(doc_dir, doc, total)
    manifest = {
        "pdf_digest_id": doc.get("id"),
        "short_id": doc.get("short_id"),
        "title": title,
        "total_chunks": total,
        "source": doc.get("source", {}),
        "paths": doc.get("paths", {}),
        "updated_at": now_iso(),
    }
    (doc_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return chunk_dir


def build_digest_message(title: str, index: int, total: int, summary: str) -> str:
    message = f"[PDF] {title} ({index + 1}/{total})\n\n要約:\n{summary.strip()}"
    if len(message) <= MESSAGE_MAX:
        return message
    header = f"[PDF] {title} ({index + 1}/{total})\n\n要約:\n"
    available = max(500, MESSAGE_MAX - len(header) - 20)
    return f"{header}{summary.strip()[:available]}\n..."


def send_slack_message(target: str, message: str, dry_run: bool) -> None:
    command = [
        require_openclaw_bin(),
        "message",
        "send",
        "--channel",
        "slack",
        "--target",
        target,
        "--message",
        message,
    ]
    if dry_run:
        print(f"[dry-run] send slack target={target} chars={len(message)}")
        return
    proc = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        raise PdfDigestError(proc.stderr.strip() or proc.stdout.strip() or "Slack送信に失敗しました。")


def complete_doc_if_needed(doc: dict[str, Any]) -> None:
    if doc["next_chunk_index"] < doc["total_chunks"]:
        return
    doc["status"] = "done"
    archive_path = STATE_DIR / "archive" / Path(doc["paths"]["pdf"]).name
    if Path(doc["paths"]["pdf"]).exists():
        shutil.move(doc["paths"]["pdf"], archive_path)
        doc["paths"]["pdf"] = str(archive_path)


def mark_chunk_sent(doc: dict[str, Any], index: int) -> None:
    if int(doc.get("next_chunk_index", 0)) != index:
        raise PdfDigestError(f"送信進捗が不正です: next_chunk_index={doc.get('next_chunk_index')}, chunk_index={index}")
    doc["next_chunk_index"] = index + 1
    doc["last_sent_at"] = now_iso()
    doc["updated_at"] = now_iso()
    doc["last_error"] = None
    doc["pending_delivery"] = None
    complete_doc_if_needed(doc)


def pending_delivery_error(doc: dict[str, Any]) -> PdfDigestError | None:
    pending = doc.get("pending_delivery")
    if not isinstance(pending, dict):
        return None
    index = pending.get("chunk_index")
    started_at = pending.get("started_at", "不明")
    return PdfDigestError(
        f"Slack送信結果が未確定です: {doc['short_id']} / チャンク {index + 1 if isinstance(index, int) else index} "
        f"/ 開始 {started_at}。送信済みなら resolve-pending {doc['short_id']} --sent、"
        f"未送信なら resolve-pending {doc['short_id']} --retry を実行してください。"
    )


def send_next_chunk(
    state: dict[str, Any],
    doc: dict[str, Any],
    chunks: list[dict[str, Any]],
    target: str,
    dry_run: bool,
    export_obsidian: bool = False,
    export_dir: Path | None = None,
) -> SendResult:
    pending_error = pending_delivery_error(doc)
    if pending_error:
        raise pending_error
    index = int(doc.get("next_chunk_index", 0))
    total = int(doc.get("total_chunks", len(chunks)))
    if index >= total:
        doc["status"] = "done"
        doc["updated_at"] = now_iso()
        return SendResult("", "")
    chunk = chunks[index]["text"]
    summary = summarize_chunk(doc["title"], index, total, chunk, dry_run)
    message = build_digest_message(doc["title"], index, total, summary)
    if export_obsidian:
        export_obsidian_chunk(doc, chunk, summary, index, total, export_dir or DEFAULT_OBSIDIAN_EXPORT_DIR, dry_run=dry_run)
    if not dry_run:
        doc["pending_delivery"] = {"chunk_index": index, "started_at": now_iso()}
        doc["updated_at"] = now_iso()
        append_history(doc, {"event": "send_started", "chunk_index": index, "dry_run": False})
        save_state(state)
    send_slack_message(target, message, dry_run)
    if dry_run:
        return SendResult(summary, message)
    mark_chunk_sent(doc, index)
    append_history(doc, {"event": "sent", "chunk_index": index, "dry_run": dry_run})
    save_state(state)
    return SendResult(summary, message)


def notify_failure(target: str, title: str, error: str, dry_run: bool) -> None:
    message = f"PDF日次要約に失敗しました: {title}\n{error}"
    try:
        send_slack_message(target, message, dry_run)
    except Exception as notify_error:
        print(f"failure notification failed: {notify_error}", file=sys.stderr)


def daily(args: argparse.Namespace) -> int:
    state = load_state()
    target = resolve_target()
    failures = 0
    for doc in list(state["documents"]):
        if doc.get("status") != "active":
            continue
        try:
            send_next_chunk(
                state,
                doc,
                load_chunks(doc),
                target,
                args.dry_run,
                export_obsidian=args.export_obsidian,
                export_dir=Path(args.export_dir) if args.export_dir else None,
            )
        except Exception as exc:
            failures += 1
            doc["last_error"] = str(exc)
            doc["updated_at"] = now_iso()
            append_history(doc, {"event": "daily_failed", "error": str(exc), "dry_run": args.dry_run})
            notify_failure(target, doc.get("title", doc.get("short_id", "PDF")), str(exc), args.dry_run)
    save_state(state)
    print(f"daily complete: failures={failures}")
    return 1 if failures else 0


def resolve_pending_delivery(args: argparse.Namespace) -> int:
    state = load_state()
    doc = find_doc(state, args.short_id)
    pending = doc.get("pending_delivery")
    if not isinstance(pending, dict):
        raise PdfDigestError(f"未確定のSlack送信はありません: {doc['short_id']}")
    index = pending.get("chunk_index")
    if not isinstance(index, int):
        raise PdfDigestError(f"未確定送信のチャンク番号が不正です: {pending!r}")
    if args.sent:
        mark_chunk_sent(doc, index)
        event = "pending_delivery_confirmed_sent"
        result = "送信済みとして進捗を確定しました"
    else:
        doc["pending_delivery"] = None
        doc["updated_at"] = now_iso()
        doc["last_error"] = None
        event = "pending_delivery_reopened"
        result = "未送信として再送可能に戻しました"
    append_history(doc, {"event": event, "chunk_index": index, "dry_run": False})
    save_state(state)
    print(f"{doc['short_id']} / {result} / {doc['next_chunk_index']}/{doc['total_chunks']} / {doc['title']}")
    return 0


def export_chunk_cmd(args: argparse.Namespace) -> int:
    state = load_state()
    doc = find_doc(state, args.short_id)
    chunks = load_chunks(doc)
    index = args.chunk - 1
    total = int(doc.get("total_chunks", len(chunks)))
    if index < 0 or index >= len(chunks):
        raise PdfDigestError(f"チャンク番号が範囲外です: {args.chunk} / total={total}")
    chunk = chunks[index]["text"]
    summary = summarize_chunk(doc["title"], index, total, chunk, args.dry_run)
    export_path = export_obsidian_chunk(
        doc,
        chunk,
        summary,
        index,
        total,
        Path(args.export_dir) if args.export_dir else DEFAULT_OBSIDIAN_EXPORT_DIR,
        dry_run=args.dry_run,
    )
    print(f"Obsidianに書き出しました: {export_path}")
    return 0


def rechunk_doc(args: argparse.Namespace) -> int:
    state = load_state()
    doc = find_doc(state, args.short_id)
    pending_error = pending_delivery_error(doc)
    if pending_error:
        raise pending_error
    chunks = load_chunks(doc)
    next_index = int(doc.get("next_chunk_index", 0))
    if next_index < 0 or next_index > len(chunks):
        raise PdfDigestError(f"進捗が不正です: next_chunk_index={next_index}")
    if next_index >= len(chunks):
        print(f"再分割対象の未送信チャンクはありません: {doc['short_id']} / {doc['title']}")
        return 0

    sent_chunks = chunks[:next_index]
    remaining_text = normalize_ws("\n\n".join(str(chunk.get("text", "")) for chunk in chunks[next_index:]))
    if not remaining_text:
        raise PdfDigestError("未送信本文が空です。")
    chunk_max = effective_chunk_max(len(remaining_text))
    chunk_strategy = resolve_chunk_strategy(getattr(args, "chunk_strategy", None))
    remaining_chunks = chunk_text(remaining_text, strategy=chunk_strategy, chunk_max=chunk_max)
    new_chunks = [
        {"index": index, "text": chunk["text"]}
        for index, chunk in enumerate([*sent_chunks, *remaining_chunks])
    ]
    new_total = len(new_chunks)
    old_total = int(doc.get("total_chunks", len(chunks)))

    print(
        f"{doc['short_id']} / {doc['title']} / "
        f"strategy={chunk_strategy} / chunk_max={chunk_max} / {next_index}/{old_total} -> {next_index}/{new_total}"
    )
    if args.dry_run:
        return 0

    Path(doc["paths"]["chunks"]).write_text(json.dumps(new_chunks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    doc["total_chunks"] = new_total
    doc["updated_at"] = now_iso()
    doc["last_error"] = None
    append_history(
        doc,
        {
            "event": "rechunked",
            "old_total_chunks": old_total,
            "new_total_chunks": new_total,
            "next_chunk_index": next_index,
            "remaining_chars": len(remaining_text),
            "chunk_max": chunk_max,
            "chunk_strategy": chunk_strategy,
            "dry_run": False,
        },
    )
    save_state(state)
    return 0


def coerce_messages(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        nested_payload = payload.get("payload")
        if isinstance(nested_payload, dict):
            nested_messages = coerce_messages(nested_payload)
            if nested_messages:
                return nested_messages
        for key in ["messages", "items", "results", "data"]:
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def parse_message_time(message: dict[str, Any]) -> datetime | None:
    for key in ["ts", "timestamp", "time", "created_at", "createdAt"]:
        value = message.get(key)
        if value is None:
            continue
        if isinstance(value, (int, float)):
            seconds = float(value) / 1000 if value > 10_000_000_000 else float(value)
            return datetime.fromtimestamp(seconds, timezone.utc)
        if isinstance(value, str):
            try:
                if re.fullmatch(r"\d+(\.\d+)?", value):
                    return datetime.fromtimestamp(float(value), timezone.utc)
                return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
            except ValueError:
                continue
    return None


def candidate_files(message: dict[str, Any]) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for key in ["files", "attachments", "media"]:
        value = message.get(key)
        if isinstance(value, list):
            files.extend([x for x in value if isinstance(x, dict)])
    return [
        file
        for file in files
        if str(file.get("mimetype") or file.get("mime_type") or file.get("filetype") or "").lower() == "pdf"
        or str(file.get("name") or file.get("filename") or file.get("title") or "").lower().endswith(".pdf")
    ]


def slack_download_url(file: dict[str, Any]) -> str:
    for key in ["url_private_download", "url_private", "download_url", "url"]:
        value = file.get(key)
        if isinstance(value, str) and value.startswith("https://"):
            return value
    return ""


def resolve_slack_token() -> str | None:
    for key in ["SLACK_BOT_TOKEN", "SLACK_USER_TOKEN"]:
        value = os.environ.get(key)
        if value:
            return value
    config_path = OPENCLAW_STATE / "openclaw.json"
    if not config_path.exists():
        return None
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    slack = data.get("channels", {}).get("slack", {})
    if not isinstance(slack, dict):
        return None
    for key in ["botToken", "userToken"]:
        value = slack.get(key)
        if isinstance(value, str) and value:
            return value
    accounts = slack.get("accounts")
    if isinstance(accounts, dict):
        for account in accounts.values():
            if not isinstance(account, dict):
                continue
            for key in ["botToken", "userToken"]:
                value = account.get(key)
                if isinstance(value, str) and value:
                    return value
    gateway_token = resolve_slack_token_from_gateway_env()
    if gateway_token:
        return gateway_token
    return None


def resolve_slack_token_from_gateway_env() -> str | None:
    proc_root = Path("/proc")
    if not proc_root.exists():
        return None
    for proc_dir in proc_root.iterdir():
        if not proc_dir.name.isdigit():
            continue
        try:
            cmdline = (proc_dir / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "ignore")
        except OSError:
            continue
        if "openclaw" not in cmdline or "gateway" not in cmdline:
            continue
        try:
            environ = (proc_dir / "environ").read_bytes().split(b"\x00")
        except OSError:
            continue
        env: dict[str, str] = {}
        for item in environ:
            if b"=" not in item:
                continue
            key, value = item.split(b"=", 1)
            env[key.decode("utf-8", "ignore")] = value.decode("utf-8", "ignore")
        for key in ["SLACK_USER_TOKEN", "SLACK_BOT_TOKEN"]:
            value = env.get(key)
            if value:
                return value
    return None


def download_slack_pdf_direct(file: dict[str, Any], file_id: str, title: str) -> Path | None:
    url = slack_download_url(file)
    token = resolve_slack_token()
    if not url or not token:
        return None
    ensure_dirs()
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("._") or file_id or "slack-pdf"
    if not safe_name.lower().endswith(".pdf"):
        safe_name += ".pdf"
    dest = STATE_DIR / "inbox" / f"download-{file_id or hashlib.sha256(url.encode()).hexdigest()[:12]}-{safe_name}"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, dest.open("wb") as fh:
            shutil.copyfileobj(response, fh)
    except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        if dest.exists():
            dest.unlink()
        raise PdfDigestError(f"Slack PDFの直接ダウンロードに失敗しました: {exc}") from exc
    if dest.stat().st_size == 0:
        dest.unlink()
        raise PdfDigestError("Slack PDFの直接ダウンロード結果が空でした。")
    with dest.open("rb") as fh:
        head = fh.read(512).lstrip().lower()
    content_type = ""
    try:
        content_type = response.headers.get("Content-Type", "")
    except Exception:
        content_type = ""
    if head.startswith(b"<!doctype html") or head.startswith(b"<html") or "text/html" in content_type.lower():
        dest.unlink()
        return None
    if not head.startswith(b"%pdf"):
        dest.unlink()
        raise PdfDigestError("Slack PDFの直接ダウンロード結果がPDFではありませんでした。")
    return dest


def download_slack_pdf_via_agent(candidate: dict[str, Any], title: str) -> Path:
    prompt = textwrap.dedent(
        f"""
        Slackの添付PDFをローカルに保存してください。
        message tool の download-file action を使い、JSON結果の path だけを1行で返してください。
        fileId: {candidate['file_id']}
        channelId: {slack_read_target(resolve_target())}
        message ts: {candidate['message_ts']}
        title: {title}
        """
    ).strip()
    result = run_json([require_openclaw_bin(), "agent", "--agent", "main", "--message", prompt, "--json", "--timeout", "600"])
    pdf_path = extract_path_result(result)
    if not pdf_path:
        raise PdfDigestError("Slack PDFのダウンロード結果にローカルPDFパスがありませんでした。")
    return pdf_path


def download_slack_pdf_via_message_action(candidate: dict[str, Any]) -> Path | None:
    payload = {
        "action": "download-file",
        "channel": "slack",
        "params": {
            "channel": "slack",
            "channelId": slack_read_target(resolve_target()).removeprefix("channel:"),
            "fileId": candidate["file_id"],
        },
    }
    proc = subprocess.run(
        ["node", str(MESSAGE_ACTION_BIN), json.dumps(payload)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        if "missing_scope" in detail:
            raise PdfDigestError(
                "Slack PDFのダウンロードに失敗しました: Slack app token に files:read scope がありません。"
                "Slack appの権限を追加して再インストールするか、PDFを手動保存して register-downloaded を使ってください。"
            )
        raise PdfDigestError(detail or "Slack PDFのdownload-file actionに失敗しました。")
    result = json.loads(proc.stdout)
    payload_result = result.get("payload") if isinstance(result, dict) else None
    if isinstance(payload_result, dict) and payload_result.get("ok") is False:
        return None
    return extract_path_result(result)


def read_recent_pdf_candidates(target: str, lookback_minutes: int = 10) -> list[dict[str, Any]]:
    payload = run_json(
        [
            require_openclaw_bin(),
            "message",
            "read",
            "--channel",
            "slack",
            "--target",
            slack_read_target(target),
            "--limit",
            "20",
            "--json",
        ]
    )
    cutoff = utc_now() - timedelta(minutes=lookback_minutes)
    state = load_state()
    candidates: list[dict[str, Any]] = []
    for message in coerce_messages(payload):
        msg_time = parse_message_time(message)
        if msg_time and msg_time < cutoff:
            continue
        for file in candidate_files(message):
            file_id = str(file.get("id") or file.get("file_id") or file.get("url_private") or file.get("url") or "")
            message_ts = str(message.get("ts") or message.get("timestamp") or message.get("id") or "")
            if source_already_registered(state, file_id or None, message_ts or None):
                continue
            candidates.append({"message": message, "file": file, "file_id": file_id, "message_ts": message_ts})
    return candidates


def register_from_slack(args: argparse.Namespace) -> int:
    target = resolve_target()
    candidates = read_recent_pdf_candidates(target, args.lookback_minutes)
    if len(candidates) == 0:
        raise PdfDigestError(f"直近{args.lookback_minutes}分以内の未登録PDF添付が見つかりません。")
    if len(candidates) > 1:
        if not args.latest:
            raise PdfDigestError(
                f"直近{args.lookback_minutes}分以内の未登録PDF添付が複数あります。"
                "`--latest` を付けるか、1件だけにしてください。"
            )
        candidates.sort(key=lambda item: parse_message_time(item["message"]) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    candidate = candidates[0]
    file = candidate["file"]
    title = str(file.get("title") or file.get("name") or file.get("filename") or "slack-pdf")
    if args.dry_run:
        raise PdfDigestError("register の dry-run はSlack添付の実ダウンロードを行いません。register-downloaded を使ってください。")
    pdf_path = download_slack_pdf_via_message_action(candidate)
    if pdf_path is None:
        pdf_path = download_slack_pdf_direct(file, candidate["file_id"], title)
    if pdf_path is None:
        pdf_path = download_slack_pdf_via_agent(candidate, title)
    register_args = argparse.Namespace(
        pdf_path=str(pdf_path),
        title=title,
        source_type="slack",
        source_file_id=candidate["file_id"],
        source_message_ts=candidate["message_ts"],
        chunk_strategy=args.chunk_strategy,
        export_obsidian=args.export_obsidian,
        export_dir=args.export_dir,
        dry_run=False,
    )
    return register_downloaded(register_args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenClaw PDF daily digest")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_export_args(p: argparse.ArgumentParser) -> None:
        export_group = p.add_mutually_exclusive_group()
        export_group.add_argument(
            "--export-obsidian",
            dest="export_obsidian",
            action="store_true",
            help="write Markdown files for Obsidian (default)",
        )
        export_group.add_argument(
            "--no-export-obsidian",
            dest="export_obsidian",
            action="store_false",
            help="do not write Markdown files for Obsidian",
        )
        p.set_defaults(export_obsidian=True)
        p.add_argument("--export-dir", default=None, help="Obsidian export directory")

    register = sub.add_parser("register", help="register one recent Slack PDF attachment")
    register.add_argument("--dry-run", action="store_true")
    register.add_argument("--lookback-minutes", type=int, default=10)
    register.add_argument("--latest", action="store_true", help="when multiple PDFs are found, register the newest one")
    register.add_argument("--chunk-strategy", default=None)
    add_export_args(register)
    register.set_defaults(func=register_from_slack)

    downloaded = sub.add_parser("register-downloaded", help="register a local PDF")
    downloaded.add_argument("pdf_path")
    downloaded.add_argument("--title")
    downloaded.add_argument("--source-type", default="slack")
    downloaded.add_argument("--source-file-id")
    downloaded.add_argument("--source-message-ts")
    downloaded.add_argument("--dry-run", action="store_true")
    downloaded.add_argument("--chunk-strategy", default=None)
    add_export_args(downloaded)
    downloaded.set_defaults(func=register_downloaded)

    list_parser = sub.add_parser("list", help="list active and paused PDFs")
    list_parser.set_defaults(func=list_docs)

    for name, status in [("pause", "paused"), ("resume", "active")]:
        p = sub.add_parser(name)
        p.add_argument("short_id")
        p.add_argument("--dry-run", action="store_true")
        p.set_defaults(func=lambda args, s=status: transition_doc(args, s))

    archive = sub.add_parser("archive")
    archive.add_argument("short_id")
    archive.add_argument("--dry-run", action="store_true")
    archive.set_defaults(func=archive_doc)

    rechunk = sub.add_parser("rechunk", help="re-split unsent chunks with the current chunk sizing policy")
    rechunk.add_argument("short_id")
    rechunk.add_argument("--dry-run", action="store_true")
    rechunk.add_argument("--chunk-strategy", default=None)
    rechunk.set_defaults(func=rechunk_doc)

    daily_parser = sub.add_parser("daily")
    daily_parser.add_argument("--dry-run", action="store_true")
    add_export_args(daily_parser)
    daily_parser.set_defaults(func=daily)

    resolve_pending = sub.add_parser("resolve-pending", help="resolve an uncertain Slack delivery without re-sending it")
    resolve_pending.add_argument("short_id")
    resolve_choice = resolve_pending.add_mutually_exclusive_group(required=True)
    resolve_choice.add_argument("--sent", action="store_true", help="confirm that the pending chunk reached Slack")
    resolve_choice.add_argument("--retry", action="store_true", help="clear the pending marker so the chunk can be sent again")
    resolve_pending.set_defaults(func=resolve_pending_delivery)

    export_chunk = sub.add_parser("export-chunk", help="write one existing chunk to Obsidian without Slack/progress updates")
    export_chunk.add_argument("short_id")
    export_chunk.add_argument("chunk", type=int, help="1-based chunk number")
    export_chunk.add_argument("--dry-run", action="store_true")
    export_chunk.add_argument("--export-dir", default=None, help="Obsidian export directory")
    export_chunk.set_defaults(func=export_chunk_cmd)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except PdfDigestError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
