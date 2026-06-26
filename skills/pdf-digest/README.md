# PDF Digest

Slack DM に添付された PDF を登録し、毎日 8:00 JST に 1 チャンクずつ日本語で要約して Slack に送る。

## Commands

通常は `/openclaw pdf ...` から使う。スクリプトを直接実行する場合は workspace から実行する。

```bash
/home/hiroki-yokouchi/.openclaw/workspace/.venv/bin/python skills/pdf-digest/scripts/pdf_digest.py <command>
```

- `register`: 直近の Slack DM から未登録 PDF を探して登録する。
- `register-downloaded <path>`: ローカル PDF を登録する。
- `list`: 配信中・停止中の PDF を一覧表示する。
- `pause <short_id>`: 日次配信を停止する。
- `resume <short_id>`: 日次配信を再開する。
- `archive <short_id>`: 日次配信対象から外す。
- `rechunk <short_id>`: 未送信分だけを現在の分割方針で再チャンクする。
- `export-chunk <short_id> <chunk>`: Slack送信や進捗更新なしで、指定チャンクをObsidian向けMarkdownとして書き出す。

`register`, `register-downloaded`, `rechunk` は `--chunk-strategy paragraph` を指定できる。未指定時は `PDF_DIGEST_CHUNK_STRATEGY`、それもなければ `paragraph` を使う。
`register`, `register-downloaded`, `daily` は `--export-obsidian` を付けると、送信チャンクをObsidian向けMarkdownにも保存する。
保存先は `PDF_DIGEST_OBSIDIAN_EXPORT_DIR` または `--export-dir` で指定でき、既定値は `/home/hiroki-yokouchi/ドキュメント/openclaw/pdf-digest`。

## Daily Cron

日次実行は `cron/jobs.json` の `pdf-digest-daily-0800` が担当する。

```bash
bash /home/hiroki-yokouchi/.openclaw/workspace/skills/pdf-digest/scripts/run_pdf_digest_daily.sh
```

このラッパーは `skills/pdf-digest/scripts/pdf_digest.py daily` を呼び、成功時は通知なし、失敗時はログに残す。
旧パス `scripts/run_pdf_digest_daily.sh` は互換用 shim としてこのラッパーに転送する。

## Chunking

チャンクサイズは固定ではなく、文書長から自動調整する。

- `PDF_DIGEST_BASE_CHUNK_MAX`: 基本チャンク上限。default `8000`
- `PDF_DIGEST_MAX_CHUNK_MAX`: 最大チャンク上限。default `15000`
- `PDF_DIGEST_TARGET_DAYS`: 目標日数。default `30`

計算ルール:

```text
required = ceil(text_length / PDF_DIGEST_TARGET_DAYS)
effective_chunk_max = min(PDF_DIGEST_MAX_CHUNK_MAX, max(PDF_DIGEST_BASE_CHUNK_MAX, required))
```

短い PDF は早く終わる。長い PDF は 30 日前後に寄せる。最大チャンク上限を超える巨大 PDF は 30 日超過を許容する。

現在の対応戦略:

- `paragraph`: 段落境界を優先して `effective_chunk_max` 以内に詰める。

今後、節や見出し境界を優先する戦略を追加する場合は、既存の `paragraph` を残したまま `--chunk-strategy` で切り替える。

## Slack Message

Slack には要約だけを送る。原文全文は送らない。
技術書のコードサンプルは、全文ではなく短い抜粋と読みどころとして要約に含める。

```text
[PDF] <title> (<current>/<total>)

要約:
<summary>
```

要約入力にはチャンク本文全体を使うが、Slack 表示は短く保つ。
重要なコードサンプルがある場合は、最大3件まで「コードサンプル:」欄に「何を示すか」「読むべきポイント」「短い抜粋」を残す。
コードサンプルが重要なチャンクは、通常より少し長い要約を許容する。

## State

状態は `workspace/pdf-digest/` 以下に保存する。

- `state.json`: 文書一覧と進捗
- `inbox/<id>.pdf`: 登録中 PDF
- `archive/<id>.pdf`: 完了・アーカイブ済み PDF
- `text/<id>.txt`: 抽出済み本文
- `chunks/<id>.json`: チャンク配列
- `history/<id>.jsonl`: 登録、送信、再チャンク、失敗履歴

`next_chunk_index` は 0 始まり。Slack 表示は 1 始まり。

## Obsidian Export

Obsidian向け書き出しはPDFごと、チャンクごとにディレクトリを分ける。

```text
<export-dir>/
  <title-slug>-<short_id>/
    index.md
    manifest.json
    chunks/
      0037/
        original.md
        summary.ja.md
        translation.ja.md
```

- `original.md`: 抽出済み原文チャンク。
- `summary.ja.md`: Slackに送る日本語要約と同じ内容。
- `translation.ja.md`: 原文が日本語ではない場合だけ作る日本語訳。
- `index.md`: PDF全体のチャンク一覧。
- `manifest.json`: 機械処理用メタデータ。

## Verification

```bash
python3 -m py_compile workspace/skills/pdf-digest/scripts/pdf_digest.py
workspace/.venv/bin/python workspace/skills/pdf-digest/scripts/pdf_digest.py list
workspace/.venv/bin/python workspace/skills/pdf-digest/scripts/pdf_digest.py rechunk <short_id> --dry-run
workspace/.venv/bin/python workspace/skills/pdf-digest/scripts/pdf_digest.py rechunk <short_id> --dry-run --chunk-strategy paragraph
workspace/.venv/bin/python workspace/skills/pdf-digest/scripts/pdf_digest.py daily --dry-run
workspace/.venv/bin/python workspace/skills/pdf-digest/scripts/pdf_digest.py export-chunk <short_id> <chunk> --export-dir /tmp/pdf-digest-obsidian-test
```

`daily --dry-run` は Slack 実送信も進捗更新もしない。
