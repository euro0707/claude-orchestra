---
date: "2026-02-07"
type: codex-review
target: Phase 1 Library Foundation (12 modules)
result: APPROVED
score: 8/10
status: re-reviewed
re-review-date: "2026-02-07"
re-review-by: claude-opus-4-6
---

# Phase 1 Codex Review - 2026-02-07

## Result: APPROVED (Score: 8/10)

> **Re-review (2026-02-07)**: 6件の修正を検証し APPROVED に更新。
> M-1 は Phase 2 での source_files 必須化を前提とした暫定対策として承認。

## Issues (6件)

### HIGH (1件) - 必須修正

#### H-1: context_guard.py - 秘密鍵 redaction が不完全
- **File**: `lib/context_guard.py`
- **Problem**: BEGIN PRIVATE KEY の header 行のみマッチし、鍵本体と END 行が漏洩する
- **Fix**: multiline regex で BEGIN...END ブロック全体を redact (DOTALL)
- **Status**: [x] FIXED (v20 Phase1-H1: multiline DOTALL regex)

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
- **Status**: [x] FIXED (v20 Phase1-M1: audit warning log追加、Phase 2でsource_files必須化予定)

#### M-2: budget.py - Windows ファイルロックによる JSON 破損
- **File**: `lib/budget.py`
- **Problem**: `msvcrt.locking` の 1024 バイト範囲ロックが短いファイルを NUL 拡張 → JSON 破損 → budget バイパス
- **Fix**: 別の `.lock` ファイルを使うか、ファイル長確認後に 1 バイトロック
- **Status**: [x] FIXED (v20 Phase1-M2: 別.lockファイル方式に変更)

#### M-3: path_utils.py - WSL/UNC パス未対応
- **File**: `lib/path_utils.py`
- **Problem**: WSL パス (`/mnt/c/...`) や UNC パス (`\\wsl$\...`) が正規化されない
- **Fix**: `/mnt/<drive>/` と UNC wsl パスの正規化を追加
- **Status**: [x] FIXED (v20 Phase1-M3: WSL/UNCパス正規化追加)

### LOW (2件) - 改善推奨

#### L-1: output_schemas.py - severity_values 未チェック / bool→int 許容
- **File**: `lib/output_schemas.py`
- **Problem**: `severity_values` 未チェック、`bool` が `int` として通る
- **Fix**: 明示的な severity 値チェックと bool 除外
- **Status**: [x] FIXED (v20 Phase1-L1: bool除外ロジック追加)

#### L-2: codex_wrapper.py - Stage 2 returncode 未チェック
- **File**: `lib/codex_wrapper.py`
- **Problem**: Stage 2 `-o` フォールバックで returncode/stderr 未チェック
- **Fix**: returncode チェックと stderr キャプチャ追加
- **Status**: [x] FIXED (v20 Phase1-L2: capture_output+returncodeチェック追加)

## 修正優先度

1. **H-1** (必須) → セキュリティ: 秘密鍵漏洩リスク
2. **M-2** (高) → 安定性: budget バイパスリスク
3. **M-1** (高) → セキュリティ: allowlist バイパス
4. **M-3** (中) → 互換性: WSL ユーザー向け
5. **L-1, L-2** (低) → 品質改善

## Re-review 結果 (2026-02-07)

### 検証サマリ

| Issue | 判定 | 備考 |
|-------|------|------|
| H-1 | PASS | multiline DOTALL regex でブロック全体を redact。根本原因解決 |
| M-1 | PASS (条件付き) | audit warning log 追加。Phase 2 での source_files 必須化が前提 |
| M-2 | PASS | 別 .lock ファイル方式で JSON 破損を完全回避 |
| M-3 | PASS | WSL `/mnt/c/` + UNC `\\wsl$\` 両対応。マッチ順序も正しい |
| L-1 | PASS | bool 明示排除 + severity_values 検証追加 |
| L-2 | PASS | returncode チェック + stderr キャプチャ追加 |

### 軽微な指摘（修正不要）

1. **M-1 重複ログ**: `context_guard.py:276-280` で `unknown_origin_warning` と `unknown_origin` の2エントリが記録される。1つに統合推奨（Phase 2 で整理可）
2. **M-1 暫定対策**: audit log のみで実際の enforce はしていない。Phase 2 で `source_files` 必須化されるまでのリスクを認識した上で承認

### リグレッションリスク

- なし。各修正は対象モジュール内で完結し、既存の動作を壊さない
- 非 Windows パス（fcntl）は未変更

## 次のステップ

1. ~~上記6件を修正~~  (完了)
2. ~~Codex re-review で APPROVED 取得~~  (完了: 2026-02-07)
3. Phase 2 (Hooks デプロイ) に進む
