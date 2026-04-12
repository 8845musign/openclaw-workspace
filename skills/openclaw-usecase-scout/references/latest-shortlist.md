# OpenClaw Use Case Shortlist

Date: 2026-02-24 (Asia/Tokyo)

## 1) 並列リサーチ班（Sub-agent分業）
- Why: 1つの依頼を複数エージェントに同時分割して、調査時間を短縮できる。
- Minimal implementation:
  - 親セッションから `sessions_spawn` で複数調査タスクを同時実行
  - 完了後に親セッションで比較・統合
  - 再現用にプロンプトテンプレート化
- Risk/guardrail: サブエージェントに渡すツールを最小化し、書き込み権限を絞る。
- Evidence URLs:
  - https://docs.openclaw.ai/tools/subagents
  - https://docs.openclaw.ai/concepts/session-tool

## 2) 承認付き定期オペ（Cron + 手動実行併用）
- Why: 毎日/毎週の運用タスクを自動化しつつ、危険操作は手動確認に寄せられる。
- Minimal implementation:
  - `openclaw cron add` で点検ジョブを登録
  - 失敗時は通知のみ（自動修復しない）
  - 必要時に `openclaw cron run <job-id>` で手動再実行
- Risk/guardrail: 破壊的操作をcronジョブに入れない。
- Evidence URLs:
  - https://docs.openclaw.ai/automation/cron-jobs
  - https://docs.openclaw.ai/gateway/configuration-reference

## 3) モバイル現地確認フロー（Nodesで一次状況把握）
- Why: 端末の位置・カメラ・画面情報で遠隔の一次確認を短時間で実施できる。
- Minimal implementation:
  - `nodes status/describe` で接続確認
  - 必要時のみ `camera_snap` / `location_get` 実行
  - 結果要約をDM通知
- Risk/guardrail: 時間帯・対象ノード・取得種別を明示的に限定。
- Evidence URLs:
  - https://docs.openclaw.ai/nodes
  - https://www.npmjs.com/package/openclaw
