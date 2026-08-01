# PDF Digest — 設計ドキュメント

## 目的

Slack DM に添付された PDF を登録し、毎日 8:00 JST に 1 チャンクずつ Claude で日本語要約して Slack に返送するスキル。長い技術書・レポートを毎日少しずつ消化することを目的とする。

---

## ファイル構成

```
skills/pdf-digest/
├── SKILL.md                        # OpenClaw スキル定義（コマンドルール・言語ルール）
├── README.md                       # 仕様サマリ
├── docs/
│   └── architecture.md             # 本ドキュメント
└── scripts/
    ├── pdf_digest.py               # メインロジック（全コマンド実装）
    └── run_pdf_digest_daily.sh     # cron ラッパー（ロック管理・ログ）
```

---

## システム構成図

```
┌─────────────────────────────────────────────────────────────┐
│  ユーザー                                                    │
│  /openclaw pdf register                                      │
│  /openclaw pdf list / pause / resume / archive / rechunk    │
└────────────────────┬────────────────────────────────────────┘
                     │ SKILL.md で pdf_digest.py へ委譲
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  pdf_digest.py                                              │
│                                                             │
│  register ──→ Slack読み取り → PDF ダウンロード              │
│              → テキスト抽出 → チャンク分割                  │
│              → 初回チャンク要約 → Slack 送信                │
│                                                             │
│  daily ─────→ active な全 PDF を順番に                      │
│              → 次チャンク要約 → Slack 送信                  │
│              → 完了時 inbox/ → archive/ 移動                │
└───────┬─────────────────────┬───────────────────────────────┘
        │                     │
        ▼                     ▼
  openclaw CLI          PyMuPDF (fitz)
  ・message read        テキスト抽出
  ・message send
  ・agent (Claude)
  ・download-file action

                     ┌───────────────┐
                     │  Obsidian     │  --export-obsidian 時のみ
                     │  export dir   │
                     └───────────────┘
```

---

## 処理フロー

### 1. 登録 (`register` / `register-downloaded`)

```
[Slack DM に PDF 添付]
        │
        ▼
openclaw message read  (直近 20 件取得、lookback-minutes 以内でフィルタ)
        │
        ▼
PDF 候補の抽出と重複チェック
  候補 0 件 → エラー
  候補 複数 → --latest なければエラー
  候補 1 件 → ダウンロードへ
        │
        ▼
PDF ダウンロード (3 段フォールバック)
  1. openclaw_message_action.mjs の download-file action
  2. Slack API 直接 HTTP ダウンロード (Bearer token)
  3. openclaw agent 経由 (最終手段)
        │
        ▼
PyMuPDF でテキスト抽出 (ページごとに [page N] プレフィックス付与)
        │
        ▼
チャンク分割 (paragraph 戦略、effective_chunk_max で自動サイズ決定)
        │
        ▼
state.json / inbox/<id>.pdf / text/<id>.txt / chunks/<id>.json を保存
        │
        ▼
初回チャンク送信 (summarize_chunk → send_slack_message)
```

### 2. 日次配信 (`daily`)

```
[cron: 毎日 08:00 JST]
run_pdf_digest_daily.sh
        │ flock でロック (二重起動防止)
        ▼
pdf_digest.py daily
        │
        ▼ state.json の documents を舐める
  status == active な文書ごとに:
        │
        ▼
  chunks[next_chunk_index] を取得
        │
        ▼
  openclaw agent --message <要約プロンプト> --json
        │
        ▼
  state.json に pending_delivery を保存
        │
        ▼
  Slack 送信 (openclaw message send)
        │
        ▼
  pending_delivery を消去し、next_chunk_index += 1、state.json 更新
        │
  next_chunk_index >= total_chunks なら:
        ▼
  status = "done"、inbox/ → archive/ に移動
```

---

## チャンクサイズ自動調整

長い文書も短い文書も「30 日前後で読み終わる」チャンクサイズに自動調整する。

```
required         = ceil(text_length / TARGET_DAYS)
effective_max    = min(MAX_CHUNK_MAX, max(BASE_CHUNK_MAX, required))
```

| 環境変数 | デフォルト | 意味 |
|---|---|---|
| `PDF_DIGEST_BASE_CHUNK_MAX` | 8000 | チャンク下限（短い文書でもこの大きさ） |
| `PDF_DIGEST_MAX_CHUNK_MAX` | 15000 | チャンク上限（巨大文書でも超えない） |
| `PDF_DIGEST_TARGET_DAYS` | 30 | 目標読了日数 |

- 短い PDF: チャンク数が少なく、30 日より早く終わる
- 長い PDF: MAX_CHUNK_MAX に達した場合のみ 30 日を超える

### チャンク分割戦略

現在の実装: `paragraph`（段落境界を優先して effective_max 以内に詰める）

`--chunk-strategy paragraph` または `PDF_DIGEST_CHUNK_STRATEGY` で指定する。未指定時も `paragraph` を使う。将来的に節・見出し境界を優先する戦略を追加する場合は既存戦略を残したまま追加する。

---

## 状態管理

`workspace/pdf-digest/` 以下にファイルベースで永続化する。

```
pdf-digest/
├── state.json            # 全文書の一覧と進捗
├── inbox/<id>.pdf        # 配信中 PDF
├── archive/<id>.pdf      # 完了・アーカイブ済み PDF
├── text/<id>.txt         # 抽出済みテキスト
├── chunks/<id>.json      # チャンク配列 [{index, text}, ...]
├── history/<id>.jsonl    # イベント履歴（登録・送信・失敗等）
└── downloads/            # 一時ダウンロード置き場
```

### state.json スキーマ（文書エントリ）

| フィールド | 型 | 説明 |
|---|---|---|
| `id` | string | SHA-256 の先頭 16 文字 |
| `short_id` | string | `id` の先頭 8 文字（ユーザー向け識別子） |
| `title` | string | PDF タイトル（最大 120 文字） |
| `status` | string | `active` / `paused` / `done` / `archived` |
| `source` | object | `{type, file_id, message_ts}` |
| `paths` | object | pdf / text / chunks / history の絶対パス |
| `next_chunk_index` | int | 次に送信するチャンクの 0 始まりインデックス |
| `total_chunks` | int | チャンク総数 |
| `last_sent_at` | string | 最終送信日時（JST ISO 8601） |
| `last_error` | string\|null | 最後に発生したエラー文字列 |
| `pending_delivery` | object\|null | Slack送信結果が未確定なチャンク。存在する間は自動再送しない。 |

state.json の書き込みは `tmp → os.replace` のアトミック書き換えで行う。

---

## Slack 通知フォーマット

```
[PDF] <title> (<current>/<total>)

要約:
<summary>
```

- 要約は日本語 500〜1000 文字程度（コードサンプルがある場合は 1200 文字程度まで許容）
- 原文全文は Slack に送らない
- 重要なコードサンプルは最大 3 件まで「コードサンプル:」欄に要約して含める
- 全体が `MESSAGE_MAX`（デフォルト 7800 文字）を超える場合は要約を打ち切り `...` を付ける

---

## Obsidian エクスポート

`--export-obsidian` を付けた `register` / `register-downloaded` / `daily` または `export-chunk` コマンドで出力する。

```
<export-dir>/
  <title-slug>-<short_id>/
    index.md              # チャンク一覧（Obsidian リンク付き）
    manifest.json         # 機械処理用メタデータ
    chunks/
      0001/
        original.md       # 抽出済み原文チャンク
        summary.ja.md     # Slack 送信と同じ日本語要約
        translation.ja.md # 原文が日本語でない場合のみ
      0002/
        ...
```

日本語判定は先頭 8000 文字のかな文字比率で行う（かな 12 文字以上、または (かな＋CJK) / 全文字 ≥ 12%）。

---

## OpenClaw 連携ポイント

| 処理 | 使用する API / コマンド |
|---|---|
| Slack メッセージ読み取り | `openclaw message read --channel slack --json` |
| Slack メッセージ送信 | `openclaw message send --channel slack` |
| PDF ダウンロード (1st try) | `openclaw_message_action.mjs` の `download-file` action |
| PDF ダウンロード (2nd try) | Slack API 直接 HTTP ダウンロード（Bearer token） |
| PDF ダウンロード (3rd try) | `openclaw agent --agent main` 経由 |
| LLM 要約・翻訳 | `openclaw agent --agent main --message <prompt> --json` |
| Slack target 解決 | 環境変数 `PDF_DIGEST_SLACK_TARGET` → `openclaw.json` の `heartbeat.to` |

---

## cron 設定

OpenClaw cron の `pdf-digest-daily-0800` command job：

| 項目 | 値 |
|---|---|
| スケジュール | `0 8 * * *` (Asia/Tokyo) |
| 実行対象 | `run_pdf_digest_daily.sh` を command payload として bash で直接実行 |
| 二重起動防止 | `flock` によるロックファイル |
| ログ | `workspace/logs/pdf-digest-daily.log` / `.error.log` |
| 失敗通知 | 1回目の実行エラーからSlack failure alert |

ジョブ定義の実体はOpenClawの現行ストレージで管理される。`cron/*.migrated` の旧JSONは編集しない。

---

## コマンド一覧

| コマンド | 説明 |
|---|---|
| `register` | 直近の Slack DM から未登録 PDF を検索して登録 |
| `register-downloaded <path>` | ローカル PDF を登録 |
| `list` | active / paused な PDF を一覧表示 |
| `pause <short_id>` | 日次配信を停止 |
| `resume <short_id>` | 日次配信を再開 |
| `archive <short_id>` | 配信対象から除外 |
| `rechunk <short_id>` | 未送信分を現在のチャンク方針で再分割 |
| `export-chunk <short_id> <chunk>` | 指定チャンクを Obsidian 向け Markdown に書き出す（Slack 送信・進捗更新なし） |
| `daily` | 全 active PDF の次チャンクを送信（cron から呼ばれる） |

共通オプション: `--dry-run`（Slack 送信・進捗更新なし）、`--export-obsidian`、`--export-dir`

---

## 検証コマンド

```bash
# 構文チェック
python3 -m py_compile skills/pdf-digest/scripts/pdf_digest.py

# 登録済み一覧
.venv/bin/python skills/pdf-digest/scripts/pdf_digest.py list

# 再チャンク dry-run
.venv/bin/python skills/pdf-digest/scripts/pdf_digest.py rechunk <short_id> --dry-run

# 日次送信 dry-run（Slack 実送信・進捗更新なし）
.venv/bin/python skills/pdf-digest/scripts/pdf_digest.py daily --dry-run

# Obsidian 書き出し検証
.venv/bin/python skills/pdf-digest/scripts/pdf_digest.py export-chunk <short_id> <chunk> --export-dir /tmp/pdf-digest-test
```
