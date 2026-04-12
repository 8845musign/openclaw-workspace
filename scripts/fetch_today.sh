#!/bin/bash
TODAY=$(date +%Y-%m-%d)
python3 scripts/imap_reader.py search --since "$TODAY" --limit 100