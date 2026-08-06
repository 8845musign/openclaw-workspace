---
name: pdf-digest
description: Slack添付PDFを登録し、毎日1チャンクずつ日本語で要約通知する。ユーザーが `/openclaw pdf ...` について実行・質問したときに使う。
---

# PDF Digest

`/openclaw pdf ...` は次のスクリプトへ委譲する:

```bash
/home/hiroki-yokouchi/.openclaw/workspace/.venv/bin/python /home/hiroki-yokouchi/.openclaw/workspace/skills/pdf-digest/scripts/pdf_digest.py <command>
```

このワークフローのために Slack plugin や OpenClaw core は変更しない。

## Language

- ユーザーへの返答とSlack通知は日本語で書く。
- 成功・失敗・状態説明は短く、実行結果が分かる表現にする。
- スクリプトが日本語エラーを返した場合は、その文面をそのまま使う。
- 英語の内部エラーやscope名が必要な場合も、説明本文は日本語にする。

## Commands

- `pdf register`
  - `pdf_digest.py register` を実行する。
  - チャンク分割戦略を明示する場合は `--chunk-strategy paragraph` を付ける。
  - Slack通知先は `PDF_DIGEST_SLACK_TARGET`、なければ `openclaw.json` の `agents.defaults.heartbeat.to` から解決する。
  - 直近20件のSlack DMを読み、直近10分以内の未登録PDF添付が1件だけなら、OpenClaw message `download-file` actionで保存して登録する。
  - 古いアップロードを拾う必要がある場合は `pdf_digest.py register --lookback-minutes <minutes>` を実行する。
  - 候補が複数あり、ユーザーが最新アップロードを意図していることが明確なら `--latest` を付ける。
  - Slack が `missing_scope` を返した場合は、Slack app に `files:read` が必要、または手動保存したPDFで `register-downloaded` を使う、と日本語で伝える。
  - 候補が0件または複数件の場合は、ユーザーが古い/最新アップロードを明示していない限り、スクリプトの日本語エラーをそのまま返す。
- `pdf list`
  - `pdf_digest.py list` を実行する。
  - `active` と `paused` のPDFだけを表示する。
- `pdf pause <short_id>`
  - `pdf_digest.py pause <short_id>` を実行する。
- `pdf resume <short_id>`
  - `pdf_digest.py resume <short_id>` を実行する。
- `pdf archive <short_id>`
  - `pdf_digest.py archive <short_id>` を実行する。
- `pdf rechunk <short_id>`
  - `pdf_digest.py rechunk <short_id>` を実行する。
  - 未送信分だけを現在のチャンクサイズ方針で再分割する。
  - チャンク分割戦略を明示する場合は `--chunk-strategy paragraph` を付ける。
- `pdf resolve-pending <short_id> --sent | --retry`
  - Slack送信直後にプロセスが落ち、送信結果が未確定になったチャンクを解決する。
  - Slackに届いたことを確認できた場合は `--sent`、届いていない場合だけ `--retry` を使う。
- `pdf export-chunk <short_id> <chunk>`
  - `pdf_digest.py export-chunk <short_id> <chunk>` を実行する。
  - Slack送信や進捗更新なしで、指定チャンクをObsidian向けMarkdownとして書き出す。
  - 保存先を変える場合は `--export-dir <path>` を付ける。

## Output

スクリプト出力をそのまま返す。返答は短く、日本語にする。

## Notes

- 状態は `/home/hiroki-yokouchi/.openclaw/workspace/pdf-digest/` に保存される。
- 送信中は状態に未確定マーカーを保存する。マーカーが残ったPDFは自動再送せず、`resolve-pending` で明示的に解決する。
- PDF本文抽出は `/home/hiroki-yokouchi/.openclaw/workspace/.venv` の PyMuPDF (`fitz`) を使う。
- Slack/LLM送信なしでローカル検証する場合は `register-downloaded <path> --dry-run` を使う。
- チャンクサイズは `PDF_DIGEST_BASE_CHUNK_MAX` (default: 8000), `PDF_DIGEST_MAX_CHUNK_MAX` (default: 15000), `PDF_DIGEST_TARGET_DAYS` (default: 30) で自動調整する。
- チャンク分割戦略は `PDF_DIGEST_CHUNK_STRATEGY` または `--chunk-strategy` で指定する。現時点の対応値は `paragraph`。
- Slack通知には原文を載せず、要約だけを送る。
- Obsidian書き出しは `register`, `register-downloaded`, `daily` で既定で有効。必要な1回だけ無効化するときは `--no-export-obsidian` を付ける。`export-chunk` は常に書き出す。
- Obsidian保存先は `PDF_DIGEST_OBSIDIAN_EXPORT_DIR`、または `--export-dir` で指定する。既定値は `/home/hiroki-yokouchi/ドキュメント/openclaw/pdf-digest`。
