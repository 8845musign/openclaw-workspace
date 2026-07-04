#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


JST = ZoneInfo("Asia/Tokyo")
ROOT = Path("/home/hiroki-yokouchi/.openclaw/workspace")
OPENCLAW_BIN = os.environ.get(
    "OPENCLAW_BIN",
    "/home/hiroki-yokouchi/.local/share/mise/installs/node/24.13.1/bin/openclaw",
)
MAX_RETRIES = int(os.environ.get("JS_TS_TREND_COLLECT_RETRIES", "2"))
AGENT_TIMEOUT_SECONDS = int(os.environ.get("JS_TS_TREND_COLLECT_AGENT_TIMEOUT", "300"))


def today_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


def validator_cmd(date_str: str) -> list[str]:
    return ["python3", "scripts/validate_js_ts_trend_artifact.py", date_str]


def run_validator(date_str: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        validator_cmd(date_str),
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def build_message(date_str: str, attempt: int, validator_stderr: str) -> str:
    retry_note = ""
    if validator_stderr.strip():
        retry_note = (
            "\nPrevious validator failure. Treat every URL/title/topic/novelty_key "
            "mentioned below as a hard ban list and overwrite the artifact with a "
            "fresh replacement:\n"
            f"{validator_stderr.strip()}\n"
        )

    return f"""Run the js-ts-trend-radar skill in collection-only mode.
Read /home/hiroki-yokouchi/.openclaw/workspace/skills/js-ts-trend-radar/SKILL.md and follow it strictly.
Create or overwrite /home/hiroki-yokouchi/.openclaw/workspace/memory/js-ts-trend/{date_str}.json.
Do not publish, do not send Slack, do not compose a prose digest, and do not ask the user what to do.
This is attempt {attempt + 1} of {MAX_RETRIES + 1}.
If web_search fails with "SearXNG base URL is not configured", stop immediately and report that collection failed because web search is not configured. Do not retry the same query.
After writing the artifact, run python3 scripts/validate_js_ts_trend_artifact.py {date_str} from /home/hiroki-yokouchi/.openclaw/workspace.
Return exactly the validator stdout line on success, or exactly the validator stderr on failure.
{retry_note}"""


def run_agent(date_str: str, attempt: int, validator_stderr: str) -> subprocess.CompletedProcess[str]:
    session_key = f"agent:main:js-ts-trend-collect:{date_str}"
    return subprocess.run(
        [
            OPENCLAW_BIN,
            "agent",
            "--agent",
            "main",
            "--session-key",
            session_key,
            "--message",
            build_message(date_str, attempt, validator_stderr),
            "--timeout",
            str(AGENT_TIMEOUT_SECONDS),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=AGENT_TIMEOUT_SECONDS + 30,
    )


def main() -> int:
    date_str = sys.argv[1] if len(sys.argv) > 1 else today_jst()
    last_validator_stderr = ""
    artifact_path = ROOT / "memory" / "js-ts-trend" / f"{date_str}.json"

    for attempt in range(MAX_RETRIES + 1):
        try:
            result = run_agent(date_str, attempt, last_validator_stderr)
        except subprocess.TimeoutExpired:
            print(
                f"collect failed: agent timed out after {AGENT_TIMEOUT_SECONDS}s before producing a valid artifact",
                file=sys.stderr,
            )
            return 1

        if result.stdout.strip():
            print(result.stdout.rstrip(), file=sys.stderr)
        if result.stderr.strip():
            print(result.stderr.rstrip(), file=sys.stderr)

        if result.returncode != 0 and not artifact_path.exists():
            print(
                "collect failed: collection agent failed before creating an artifact; "
                "not retrying validator without input",
                file=sys.stderr,
            )
            return 1

        validation = run_validator(date_str)
        if validation.returncode == 0:
            print(validation.stdout.strip())
            return 0

        last_validator_stderr = validation.stderr.strip() or validation.stdout.strip()
        print(last_validator_stderr, file=sys.stderr)

    print(last_validator_stderr or "collect failed: validator did not pass", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
