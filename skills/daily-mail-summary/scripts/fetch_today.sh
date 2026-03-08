#!/usr/bin/env bash
# Fetch today's emails using imap-inbox-reader
set -euo pipefail

WORKSPACE="${WORKSPACE:-$(cd "$(dirname "$0")/../../.." && pwd)}"
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Load IMAP credentials
if [ -f "$WORKSPACE/.env.imap" ]; then
  set -a
  source "$WORKSPACE/.env.imap"
  set +a
fi

# Today's date in DD-Mon-YYYY format for IMAP SINCE
TODAY=$(LC_ALL=C date +"%d-%b-%Y")

python3 "$WORKSPACE/skills/imap-inbox-reader/scripts/imap_reader.py" \
  search --criteria "(SINCE \"$TODAY\")" --limit 50
