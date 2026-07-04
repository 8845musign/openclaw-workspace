# OpenClaw PDF日次要約 v1

## Summary

Slack DMにPDFを添付し、その後 `/openclaw pdf register` を実行すると、直近10分以内の未登録PDFを1件だけ登録する。登録時に初回チャンクを即要約送信し、以後は毎日8:00 JSTに配信中PDFすべてを1チャンクずつ要約する。Slackプラグインへのパッチは行わず、OpenClawの既存slash command、message tool、CLI、workspace scriptsで構成する。

## Key Changes

- `workspace/skills/pdf-digest/SKILL.md` を追加し、`/openclaw pdf ...` で渡る `pdf ...` コマンドを専用スクリプトへ委譲する契約を定義する。
- `workspace/scripts/pdf_digest.py` を追加する。
  - コマンド: `register-downloaded`, `list`, `pause`, `resume`, `archive`, `daily`
  - PDF抽出は `pymupdf` を使う。
  - 要約生成は `openclaw agent --agent main --message ... --json` を同期呼び出しする。
  - Slack送信は `openclaw message send --channel slack --target <resolved-target>` を使う。
  - `--dry-run` でLLM/Slack送信をスキップまたはモックできるようにする。
- `workspace/scripts/run_pdf_digest_daily.sh` を追加し、8:00 JST cronから `pdf_digest.py daily` を呼ぶ。成功時は通知なし、失敗時はログを返す既存cron運用に合わせる。
- `cron/jobs.json` に 8:00 JST の日次ジョブを追加する。

## Behavior

- `/openclaw pdf register`
  - 既存通知先からSlack targetを動的解決する。優先順は `PDF_DIGEST_SLACK_TARGET`、次に `openclaw.json` の `agents.defaults.heartbeat.to`。
  - `openclaw message read --channel slack --target <target> --limit 20 --json` で直近DM履歴を読み、10分以内の未登録PDF添付を探す。
  - 候補が0件または複数件なら日本語エラーを返す。
  - 候補が1件なら、エージェントの `message` tool `download-file` actionでローカル保存し、`pdf_digest.py register-downloaded` に渡す。
  - PDF保存・抽出・チャンク化が成功したら登録を維持する。初回要約/送信に失敗しても `active` のまま残し、次回再試行する。
- `/openclaw pdf list`
  - `active` と `paused` のみ表示する。`done` と `archived` は通常一覧に出さない。
  - 表示形式: `short_id / 状態 / 進捗 / title`。状態表示は `配信中`, `停止中`。
- `/openclaw pdf pause <short_id>`, `resume`, `archive`
  - `pause` は配信停止、`resume` は再開、`archive` は通常一覧と日次配信から除外する。
  - 物理削除はしない。タイトル変更コマンドはv1では作らない。
- 日次配信
  - `active` な全PDFを対象にし、ツール側で件数制限はしない。
  - 各PDFから1チャンクずつ処理する。あるPDFで失敗しても他PDFは続ける。
  - 失敗は常に次回再試行し、失敗ごとに通知する。

## Data Model

- 保存先は `workspace/pdf-digest/`。
  - `state.json`: 文書一覧と最新状態
  - `inbox/<id>.pdf`: 登録中PDF
  - `archive/<id>.pdf`: 完了/アーカイブPDF
  - `text/<id>.txt`: 抽出済み本文
  - `chunks/<id>.json`: チャンク境界
  - `history/<id>.jsonl`: 送信/失敗履歴
- `state.json` は概ね以下を持つ。
  - `id`, `short_id`, `title`, `status`
  - `source.type=slack`, `source.file_id`, `source.message_ts`
  - `paths.pdf`, `paths.text`, `paths.chunks`, `paths.history`
  - `next_chunk_index`, `total_chunks`
  - `created_at`, `updated_at`, `last_sent_at`, `last_error`
- チャンクは `chunks/<id>.json` に分離し、内部indexは0始まり。Slack表示は1始まり。
- JSON保存は `state.json.tmp` へ書いて `os.replace()` する。明示ロックはv1では入れない。

## Message Format

```text
[PDF] <title> (<current>/<total>)

要約:
<500〜1000文字程度の文章要約>

原文:
<該当チャンクの抽出テキスト>
```

- 「次回」「要点」「用語・前提」は出さない。
- 原文はLLM生成ではなく、抽出済みテキストからそのまま入れる。
- 原文チャンクは日本語換算で約2,000〜3,000文字を目標にし、段落境界を優先して切る。
- Slackプラグイン側は通常テキストを最大8,000文字単位で分割できるため、要約+原文は原則この範囲に収める。

## Test Plan

- `pdf_digest.py register-downloaded --dry-run` でローカルPDFから `state/text/chunks/history` が作られる。
- `pdf_digest.py list/pause/resume/archive --dry-run` で状態遷移と日本語表示を確認する。
- `pdf_digest.py daily --dry-run` で active PDFごとに1チャンク処理され、paused/archived/done は除外される。
- 初回要約失敗をモックし、登録が維持され `next_chunk_index` が進まないことを確認する。
- 最終チャンク送信成功後に `status: done` になり、PDFが `archive/` に移ることを確認する。
- Slack実機確認では、PDF添付後10分以内の `/openclaw pdf register` だけが登録に成功し、0件/複数件は日本語エラーになることを確認する。

## Assumptions

- v1ではSlackプラグインやOpenClaw本体にパッチしない。
- PDF添付と `/openclaw pdf register` は2手操作にする。slash commandにPDFを同時添付する設計は採らない。
- `pdf register` なしのPDF添付は何もしない。
- OCRはv1対象外。ただし抽出失敗も `active` のまま再試行し、失敗ごとに通知する。
- 通知量の自動抑制はしない。登録数と停止/アーカイブ操作でユーザーが制御する。
