#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo


JST = ZoneInfo("Asia/Tokyo")
ROOT = Path("/home/hiroki-yokouchi/.openclaw/workspace")
ARTIFACT_DIR = Path(os.environ.get("JS_TS_TREND_ARTIFACT_DIR", ROOT / "memory" / "js-ts-trend")).expanduser()
VALID_STATUSES = {"ok", "partial", "fallback"}
VALID_BUCKETS = {"design", "library", "signal"}
DUPLICATE_LOOKBACK_DAYS = 7
TITLE_STOPWORDS = {
    "and",
    "for",
    "from",
    "into",
    "new",
    "the",
    "with",
    "vs",
    "in",
    "of",
    "a",
    "an",
    "to",
    "roadmap",
    "release",
    "update",
    "major",
    "state",
}


def today_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


def fail(message: str) -> int:
    print(f"collect failed: {message}", file=sys.stderr)
    return 1


def parse_date(date_str: str) -> date:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"date must be YYYY-MM-DD: {date_str}") from exc


def normalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


def title_terms(title: str) -> set[str]:
    terms = set()
    for term in re.findall(r"[a-z]+|\d+(?:\.\d+)?", title.lower()):
        if term in TITLE_STOPWORDS:
            continue
        if term.isalpha() and len(term) < 2:
            continue
        terms.add(term)
    return terms


def normalized_title(title: str) -> str:
    return " ".join(sorted(title_terms(title)))


def item_novelty_key(item: dict[str, Any]) -> str:
    value = item.get("novelty_key")
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def load_json_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"artifact root must be an object: {path}")
    return data


def require_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"artifact {key} must be a non-empty string")
    return value


def require_string_list(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list):
        raise ValueError(f"artifact {key} must be a list")
    if not all(isinstance(item, str) for item in value):
        raise ValueError(f"artifact {key} must contain only strings")
    return value


def validate_item(raw: Any, index: int) -> None:
    if not isinstance(raw, dict):
        raise ValueError(f"item {index} must be an object")

    for key in ["bucket", "title", "url", "source_kind", "why_new", "why_important"]:
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"item {index} missing required field: {key}")

    if raw["bucket"] not in VALID_BUCKETS:
        raise ValueError(f"item {index} has invalid bucket: {raw['bucket']}")

    novelty_key = raw.get("novelty_key")
    if novelty_key is not None and (not isinstance(novelty_key, str) or not novelty_key.strip()):
        raise ValueError(f"item {index} novelty_key must be a non-empty string when present")


def previous_artifact_paths(date_str: str) -> list[Path]:
    current_date = parse_date(date_str)
    paths = []
    for offset in range(1, DUPLICATE_LOOKBACK_DAYS + 1):
        previous = current_date - timedelta(days=offset)
        path = ARTIFACT_DIR / f"{previous:%Y-%m-%d}.json"
        if path.exists():
            paths.append(path)
    return paths


def is_similar_title(current_title: str, previous_title: str) -> bool:
    current_terms = title_terms(current_title)
    previous_terms = title_terms(previous_title)
    if not current_terms or not previous_terms:
        return normalized_title(current_title) == normalized_title(previous_title)

    overlap = current_terms & previous_terms
    return len(overlap) >= 2 and len(overlap) >= min(len(current_terms), len(previous_terms)) / 2


def validate_no_recent_duplicates(date_str: str, items: list[Any]) -> None:
    seen_urls: dict[str, str] = {}
    seen_titles: dict[str, str] = {}
    seen_novelty_keys: dict[str, str] = {}

    for path in previous_artifact_paths(date_str):
        try:
            data = load_json_object(path)
        except (OSError, json.JSONDecodeError, ValueError):
            continue

        previous_date = str(data.get("date") or path.stem)
        previous_items = data.get("items")
        if not isinstance(previous_items, list):
            continue

        for item in previous_items:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            title = item.get("title")
            novelty_key = item_novelty_key(item)
            if isinstance(url, str) and url.strip():
                seen_urls[normalize_url(url)] = previous_date
            if isinstance(title, str) and title.strip():
                seen_titles[title] = previous_date
            if novelty_key:
                seen_novelty_keys[novelty_key] = previous_date

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue

        novelty_key = item_novelty_key(item)
        if novelty_key and novelty_key in seen_novelty_keys:
            raise ValueError(
                f"item {index} repeats novelty_key from {seen_novelty_keys[novelty_key]}: {novelty_key}"
            )

        url = normalize_url(str(item["url"]))
        if url in seen_urls:
            raise ValueError(f"item {index} repeats URL from {seen_urls[url]}: {item['url']}")

        title = str(item["title"])
        for previous_title, previous_date in seen_titles.items():
            if is_similar_title(title, previous_title):
                raise ValueError(
                    f"item {index} repeats recent topic from {previous_date}: {title} ~= {previous_title}"
                )


def validate_artifact(date_str: str) -> tuple[str, int]:
    path = ARTIFACT_DIR / f"{date_str}.json"
    if not path.exists():
        raise FileNotFoundError(f"artifact not found: {path}")

    try:
        data = load_json_object(path)
    except json.JSONDecodeError as exc:
        raise ValueError(f"artifact is invalid JSON: {exc}") from exc

    artifact_date = require_string(data, "date")
    if artifact_date != date_str:
        raise ValueError(f"artifact date mismatch: expected {date_str}, got {artifact_date}")

    require_string(data, "generated_at")
    status = require_string(data, "status")
    if status not in VALID_STATUSES:
        raise ValueError(f"artifact status must be one of {sorted(VALID_STATUSES)}")

    require_string_list(data, "coverage_notes")
    tl_dr = require_string_list(data, "tl_dr")
    if len(tl_dr) > 3:
        raise ValueError("artifact tl_dr must contain at most 3 items")

    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError("artifact items must be a list")
    for index, item in enumerate(items):
        validate_item(item, index)
    validate_no_recent_duplicates(date_str, items)

    deep_dive = data.get("deep_dive")
    if deep_dive is not None and not isinstance(deep_dive, dict):
        raise ValueError("artifact deep_dive must be an object or null")

    return status, len(items)


def main() -> int:
    date_str = sys.argv[1] if len(sys.argv) > 1 else today_jst()
    try:
        status, item_count = validate_artifact(date_str)
    except Exception as exc:
        return fail(str(exc))

    print(f"collect {status}: {item_count} items saved to memory/js-ts-trend/{date_str}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
