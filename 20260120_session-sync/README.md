# Session Sync Script

Claude Code のセッションを自動的に Obsidian のマークダウンに変換するスクリプト。

## 参考記事
https://zenn.dev/pepabo/articles/ffb79b5279f6ee

## ファイル構成
- `sync-sessions.ps1` - メインスクリプト

## 動作概要
1. `C:\Users\skyeu\.claude\projects\` 内の `.jsonl` ファイルを監視
2. 新しいメッセージを検出したらマークダウンに変換
3. `C:\Users\skyeu\.claude\obsidian-sessions\` に出力
4. 日付ごとにファイルを分割（`YYYY-MM-DD_auto.md`）

## 使い方
```powershell
powershell -ExecutionPolicy Bypass -File "G:\マイドライブ\TetsuyaSynapse\90-Claude\scripts\sync-sessions.ps1"
```

## 状態ファイル
- `C:\Users\skyeu\.claude\sync-state.json` - 同期済み行数を記録

## 既知の制限
- 日本語パス（Google Drive）への直接出力は文字化けするため、ローカルパスに出力
- 出力後、手動で TetsuyaSynapse Vault にコピーが必要

## 次回の改善候補
- [ ] タスクスケジューラでの自動起動
- [ ] ローカル → Vault への定期コピー
- [ ] iPhone 同期との連携
