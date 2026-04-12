#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


JST = ZoneInfo("Asia/Tokyo")
ROOT = Path("/home/hiroki-yokouchi/.openclaw/workspace")
ARTIFACT_DIR = ROOT / "memory" / "js-ts-trend"
VAULT_ROOT = Path(os.environ.get("JS_TS_TREND_VAULT_ROOT", "~/ドキュメント/openclaw")).expanduser()
NOTE_DIR = VAULT_ROOT / "tech-digest"
OPENCLAW_BIN = os.environ.get(
    "OPENCLAW_BIN",
    "/home/hiroki-yokouchi/.local/share/mise/installs/node/24.13.1/bin/openclaw",
)
NOTIFY_CHANNEL = os.environ.get("JS_TS_TREND_NOTIFY_CHANNEL", "slack")
NOTIFY_TARGET = os.environ.get("JS_TS_TREND_NOTIFY_TARGET", "U08T8S3BBFX")
SKIP_SEND = os.environ.get("JS_TS_TREND_SKIP_SEND", "").lower() in {"1", "true", "yes"}


@dataclass
class TrendItem:
    bucket: str
    title: str
    url: str
    source_kind: str
    why_new: str
    why_important: str


def today_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


def artifact_path_for(date_str: str) -> Path:
    return ARTIFACT_DIR / f"{date_str}.json"


def note_path_for(date_str: str) -> Path:
    return NOTE_DIR / f"{date_str}-js-ts.md"


def send_message(message: str) -> None:
    if SKIP_SEND:
        return
    subprocess.run(
        [
            OPENCLAW_BIN,
            "message",
            "send",
            "--channel",
            NOTIFY_CHANNEL,
            "--target",
            NOTIFY_TARGET,
            "--message",
            message,
        ],
        check=True,
    )


def parse_item(raw: dict[str, Any]) -> TrendItem:
    required = ["bucket", "title", "url", "source_kind", "why_new", "why_important"]
    missing = [key for key in required if not raw.get(key)]
    if missing:
        raise ValueError(f"item missing required fields: {', '.join(missing)}")
    return TrendItem(
        bucket=str(raw["bucket"]),
        title=str(raw["title"]),
        url=str(raw["url"]),
        source_kind=str(raw["source_kind"]),
        why_new=str(raw["why_new"]),
        why_important=str(raw["why_important"]),
    )


def load_artifact(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"artifact not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ["date", "generated_at", "status", "coverage_notes", "tl_dr", "items"]:
        if key not in data:
            raise ValueError(f"artifact missing top-level key: {key}")
    if not isinstance(data["coverage_notes"], list) or not isinstance(data["tl_dr"], list) or not isinstance(data["items"], list):
        raise ValueError("artifact has invalid list fields")
    data["items"] = [parse_item(item).__dict__ for item in data["items"]]
    deep_dive = data.get("deep_dive")
    if deep_dive is not None and not isinstance(deep_dive, dict):
        raise ValueError("deep_dive must be an object or null")
    return data


def bucket_label(bucket: str) -> str:
    return {
        "design": "設計論",
        "library": "ライブラリ",
        "signal": "現場",
    }.get(bucket, bucket)


def build_note(data: dict[str, Any]) -> str:
    date_str = data["date"]
    coverage_notes = [str(x).strip() for x in data.get("coverage_notes", []) if str(x).strip()]
    tl_dr = [str(x).strip() for x in data.get("tl_dr", []) if str(x).strip()][:3]
    items = [TrendItem(**item) for item in data["items"]]
    deep_dive = data.get("deep_dive") or {}

    lines = [
        "---",
        f'source_date: "{date_str}"',
        f'captured_at: "{data["generated_at"]}"',
        'type: "trend-digest"',
        'tags: ["javascript", "typescript", "trend"]',
        f'status: "{data["status"]}"',
        "---",
        "",
        f"# JS/TS Trend Digest ({date_str})",
        "",
        "## TL;DR",
    ]
    if tl_dr:
        lines.extend([f"- {bullet}" for bullet in tl_dr])
    else:
        lines.append("- 今日は強いシグナルが少なかった。")

    lines.extend(["", "## 注目トピック"])
    if items:
        for item in items:
            lines.extend(
                [
                    "",
                    f"### {bucket_label(item.bucket)}: {item.title}",
                    f"- 何が新しいか: {item.why_new}",
                    f"- なぜ重要か: {item.why_important}",
                    f"- URL: {item.url}",
                    f"- ソース種別: {item.source_kind}",
                ]
            )
    else:
        lines.extend(["", "- 採用できる強いトピックは見つからなかった。"])

    lines.extend(["", "## 今日の深掘り1本"])
    if deep_dive.get("title") and deep_dive.get("url"):
        lines.extend(
            [
                f"- タイトル: {deep_dive['title']}",
                f"- URL: {deep_dive['url']}",
                f"- 理由: {deep_dive.get('reason', '今日の代表トピック')}",
            ]
        )
    else:
        lines.append("- 深掘り対象なし")

    lines.extend(["", "## Coverage Notes"])
    if coverage_notes:
        lines.extend([f"- {note}" for note in coverage_notes])
    else:
        lines.append("- 主要ソースを概ね確認した。")

    return "\n".join(lines) + "\n"


def build_message(note_content: str) -> str:
    return note_content.rstrip()


def publish_for(date_str: str) -> tuple[Path, dict[str, Any]]:
    artifact_path = artifact_path_for(date_str)
    data = load_artifact(artifact_path)
    NOTE_DIR.mkdir(parents=True, exist_ok=True)
    note_path = note_path_for(data["date"])
    note_content = build_note(data)
    note_path.write_text(note_content, encoding="utf-8")
    send_message(build_message(note_content))
    return note_path, data


def fail_and_notify(message: str) -> int:
    try:
        send_message(f"JS/TSトレンド要約の配信に失敗した: {message}")
    except Exception as notify_error:  # pragma: no cover - best effort
        print(f"notify_error={notify_error}", file=sys.stderr)
    print(message, file=sys.stderr)
    return 1


def main() -> int:
    date_str = sys.argv[1] if len(sys.argv) > 1 else today_jst()
    try:
        note_path, data = publish_for(date_str)
    except Exception as exc:
        return fail_and_notify(str(exc))

    result = {
        "ok": True,
        "date": data["date"],
        "status": data["status"],
        "notePath": str(note_path),
        "itemCount": len(data.get("items", [])),
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
