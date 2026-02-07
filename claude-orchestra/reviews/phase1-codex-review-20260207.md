---
date: "2026-02-07"
type: codex-review
target: Phase 1 Library Foundation (12 modules)
result: NOT APPROVED
score: 6/10
status: pending-fixes
---

# Phase 1 Codex Review - 2026-02-07

## Result: NOT APPROVED (Score: 6/10)

## Issues (6件)

### HIGH (1件) - 必須修正

#### H-1: context_guard.py - 秘密鍵 redaction が不完全
- **File**: `lib/context_guard.py`
- **Problem**: BEGIN PRIVATE KEY の header 行のみマッチし、鍵本体と END 行が漏洩する
- **Fix**: multiline regex で BEGIN...END ブロック全体を redact (DOTALL)
- **Status**: [ ] TODO

```python
# 現状（header のみ）
re.compile(r'-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----')

# 修正案（ブロック全体）
re.compile(r'-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----', re.DOTALL)
```

### MEDIUM (3件) - 推奨修正

#### M-1: context_guard.py - source_files 未指定時の allowlist バイパス
- **File**: `lib/context_guard.py`
- **Problem**: `source_files` 未指定時にデフォルト `redact` ポリシーで allowlist/blocked file チェックがスキップ
- **Fix**: `require_allowlist` をデフォルトにするか、Phase 2 Hooks で必ず `source_files` を渡す
- **Status**: [ ] TODO

#### M-2: budget.py - Windows ファイルロックによる JSON 破損
- **File**: `lib/budget.py`
- **Problem**: `msvcrt.locking` の 1024 バイト範囲ロックが短いファイルを NUL 拡張 → JSON 破損 → budget バイパス
- **Fix**: 別の `.lock` ファイルを使うか、ファイル長確認後に 1 バイトロック
- **Status**: [ ] TODO

#### M-3: path_utils.py - WSL/UNC パス未対応
- **File**: `lib/path_utils.py`
- **Problem**: WSL パス (`/mnt/c/...`) や UNC パス (`\\wsl$\...`) が正規化されない
- **Fix**: `/mnt/<drive>/` と UNC wsl パスの正規化を追加
- **Status**: [ ] TODO

### LOW (2件) - 改善推奨

#### L-1: output_schemas.py - severity_values 未チェック / bool→int 許容
- **File**: `lib/output_schemas.py`
- **Problem**: `severity_values` 未チェック、`bool` が `int` として通る
- **Fix**: 明示的な severity 値チェックと bool 除外
- **Status**: [ ] TODO

#### L-2: codex_wrapper.py - Stage 2 returncode 未チェック
- **File**: `lib/codex_wrapper.py`
- **Problem**: Stage 2 `-o` フォールバックで returncode/stderr 未チェック
- **Fix**: returncode チェックと stderr キャプチャ追加
- **Status**: [ ] TODO

## 修正優先度

1. **H-1** (必須) → セキュリティ: 秘密鍵漏洩リスク
2. **M-2** (高) → 安定性: budget バイパスリスク
3. **M-1** (高) → セキュリティ: allowlist バイパス
4. **M-3** (中) → 互換性: WSL ユーザー向け
5. **L-1, L-2** (低) → 品質改善

## 次のステップ

1. 上記6件を修正
2. Codex re-review で APPROVED 取得
3. Phase 2 (Hooks デプロイ) に進む
