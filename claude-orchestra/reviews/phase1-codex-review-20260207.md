---
date: "2026-02-07"
type: codex-review
target: Phase 1 Library Foundation (12 modules) + Phase 2 Hooks Deploy
result: APPROVED
score: 9/10
status: final-review
re-review-date: "2026-02-07"
re-review-by: claude-opus-4-6
phase2-commit: 26c50f4
---

# Phase 1 + Phase 2 Review - 2026-02-07

## Result: APPROVED (Score: 9/10)

> **Final review (2026-02-07)**: Phase 1 全6件修正 + Phase 2 hooks デプロイ + M-1 enforcement 強化を検証。
> M-1 は `ORCHESTRA_STRICT_ORIGIN=1` デフォルトにより完全 enforcement 済み。

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
- **Status**: [x] FIXED + ENFORCED (v20 Phase1-M1 → bootstrap.py ORCHESTRA_STRICT_ORIGIN=1)

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

## Re-review 結果 (2026-02-07) — 初回

### 検証サマリ

| Issue | 判定 | 備考 |
|-------|------|------|
| H-1 | PASS | multiline DOTALL regex でブロック全体を redact。根本原因解決 |
| M-1 | PASS (条件付き) | audit warning log 追加。Phase 2 での source_files 必須化が前提 |
| M-2 | PASS | 別 .lock ファイル方式で JSON 破損を完全回避 |
| M-3 | PASS | WSL `/mnt/c/` + UNC `\\wsl$\` 両対応。マッチ順序も正しい |
| L-1 | PASS | bool 明示排除 + severity_values 検証追加 |
| L-2 | PASS | returncode チェック + stderr キャプチャ追加 |

---

## Final Review 結果 (2026-02-07) — Phase 2 デプロイ後

### Phase 1 修正 再検証

| Issue | 判定 | 備考 |
|-------|------|------|
| H-1 | PASS | 変更なし。引き続き有効 |
| M-1 | **PASS (強化済み)** | `bootstrap.py:60-61` で `ORCHESTRA_STRICT_ORIGIN=1` デフォルト設定。`source_files` 未提供で `ContextGuardError` |
| M-2 | PASS | 変更なし |
| M-3 | PASS | 変更なし |
| L-1 | PASS | 変更なし |
| L-2 | PASS | 変更なし |

### M-1 Enforcement 検証

- `bootstrap.py:60-61`: `ORCHESTRA_STRICT_ORIGIN` 未設定時にデフォルト `"1"` を設定
- `context_guard.py:265-272`: `strict_origin == "1"` かつ `source_files` なしで `ContextGuardError`
- bootstrap を import する全 hook が自動的に strict モード（漏れなし）
- `os.environ.get()` で既存設定を上書きしない（オプトアウト可能）

**エッジケース:**
- `guard_context("content")` → ContextGuardError (PASS)
- `guard_context("content", source_files=[])` → ContextGuardError (PASS)
- `guard_context("content", source_files=["file.py"])` → 正常通過 (PASS)

### Phase 2 Hooks デプロイ検証

**デプロイ状態:**
- 10 hook scripts → `~/.claude/hooks/` (デプロイ済み)
- settings.json → 7イベントにhook設定完了
- lib → junction リンクで `claude-orchestra/lib/` と同期

**Hook 安全性:**
- 全10 hook が「サジェスト専用」（Codex を直接呼ばない）
- 全 hook に try/except フェイルセーフ
- stdin JSON → stdout JSON のパススルー設計

### 軽微な指摘（修正任意）

1. **Stop hook Python パス**: `settings.json:100` で `python`（PATH依存）。他の hook は絶対パス。統一推奨
2. **到達不能コード**: `context_guard.py:276-280` の `unknown_origin_warning` ログは `ORCHESTRA_STRICT_ORIGIN=1` 環境では line 266-272 で先にブロックされるため到達しない

### リグレッションリスク

- なし。Phase 1 修正は対象モジュール内で完結
- Phase 2 hooks は全てサジェスト専用で副作用なし
- 非 Windows パス（fcntl）は未変更

---

## Codex Phase 3 Review (2026-02-07)

### Result: APPROVED (Score: 8/10) — 2 medium, 1 low

| # | Severity | File | 指摘 | 対応 |
|---|----------|------|------|------|
| CM-1 | medium | `bootstrap.py:56` | env var `"true"/"yes"` 等で enforcement が意図せず無効化 | FIXED: truthy/falsy 正規化 |
| CM-2 | medium | `context_guard.py:266` | bootstrap なしで `guard_context()` 呼出時にバイパス | FIXED: デフォルト `"1"` (fail closed) |
| CL-1 | low | `context_guard.py:274` | audit event 名変更でダッシュボード影響の可能性 | ACCEPTED: ダッシュボード未構築のため影響なし |

### CM-1 修正内容 (bootstrap.py)

```python
# Before: if not os.environ.get("ORCHESTRA_STRICT_ORIGIN"):
# After: truthy/falsy normalization
_strict_raw = os.environ.get("ORCHESTRA_STRICT_ORIGIN", "")
if _strict_raw.lower() in ("", "1", "true", "yes", "on"):
    os.environ["ORCHESTRA_STRICT_ORIGIN"] = "1"
elif _strict_raw.lower() in ("0", "false", "no", "off"):
    os.environ["ORCHESTRA_STRICT_ORIGIN"] = "0"
else:
    os.environ["ORCHESTRA_STRICT_ORIGIN"] = "1"  # fail closed
```

### CM-2 修正内容 (context_guard.py)

```python
# Before: os.environ.get("ORCHESTRA_STRICT_ORIGIN", "0") == "1"
# After:  os.environ.get("ORCHESTRA_STRICT_ORIGIN", "1") == "1"  # fail closed
```

---

## Codex Phase 4 Review (2026-02-07)

### Result: APPROVED (Score: 6/10) — 4 medium, 1 low

| # | Severity | File | 指摘 | 対応 |
|---|----------|------|------|------|
| P4-1 | medium | `context_guard.py:47` | `.env.production.local` がブロックされない | FIXED: regex `(\.\w+)?` → `(\.\w+)*` |
| P4-2 | medium | `codex_wrapper.py:50` | `find_node()`/`find_codex_js()` が try/except 外 | FIXED: try/except で構造化エラー返却 |
| P4-3 | medium | `gemini_wrapper.py:68` | returncode 未チェック | FIXED: 非ゼロで failure 返却 |
| P4-4 | medium | lib 全体 | テストゼロ | ACCEPTED: Phase 5 以降で対応 |
| P4-5 | low | `__init__.py:10` | import 時の bootstrap 副作用 | ACCEPTED: hooks は直接 import bootstrap するため影響限定的 |

---

## Codex Phase 5 Review (2026-02-07)

### Result: NOT APPROVED → FIXED → 226 tests pass (Score: 7/10) — 1 high, 4 medium

| # | Severity | File | 指摘 | 対応 |
|---|----------|------|------|------|
| P5-1 | high | `conftest.py:10` | テストが `~/.claude/lib/` から import → 非hermetic | FIXED: `Path(__file__).parent.parent / "lib"` に変更 |
| P5-2 | medium | `test_hooks.py:9` | Hook テストが `~/.claude/hooks/` の実スクリプト依存 | FIXED: `pytestmark = pytest.mark.skipif` で hooks 不在時スキップ |
| P5-3 | medium | `conftest.py:28` | `budget.py` の module-level env var timing | FIXED: `mock_budget_file` fixture で `DEFAULT_TOKEN_BUDGET/DEFAULT_MAX_CONCURRENT` を monkeypatch |
| P5-4 | medium | `test_cli_finder.py`, `test_codex_wrapper.py` | モック戦略が過度に寛容 | FIXED: 実ファイルシステム使用、アサーション強化 |
| P5-5 | medium | `test_context_guard.py` | セキュリティテスト不足 | FIXED: ALLOWED_DIRS パース、無効ポリシー、パストラバーサル、.env multi-suffix テスト追加 (8 tests) |

### P5-1 修正で発見された既存テストの問題

import パスを `~/.claude/lib/` からリポジトリ `lib/` に修正したことで、リポジトリの最新コードが正しくテストされ、4件の既存テスト不整合が発見された:

1. `test_private_key`: H-1 修正で BEGIN...END ブロック全体が必要 → テストデータ更新
2. `test_json_response`, `test_raw_text_response`, `test_empty_output`: P4-3 の returncode チェック追加で MagicMock に `returncode=0` が必要 → テスト修正

**P5-1 の指摘が正しかったことの証拠** — `~/.claude/lib/` の古いコードでは通っていたが、リポジトリコードでは失敗していた。

### テスト結果

- 修正前: 218 tests (non-hermetic)
- 修正後: **226 tests, all pass (2.72s)** (+8 new security tests)

## 次のステップ

1. ~~上記6件を修正~~  (完了)
2. ~~Codex re-review で APPROVED 取得~~  (完了: 8/10)
3. ~~Phase 2 (Hooks デプロイ)~~  (完了: 26c50f4)
4. ~~M-1 enforcement 強化~~  (完了: ORCHESTRA_STRICT_ORIGIN=1)
5. ~~Final review APPROVED~~  (完了: 9/10)
6. ~~Codex Phase 3 review~~  (完了: APPROVED 8/10, CM-1/CM-2 修正済み)
7. ~~Codex Phase 4 review~~  (完了: APPROVED 6/10, P4-1/P4-2/P4-3 修正済み)
8. ~~Codex Phase 5 review~~  (完了: 7/10, P5-1~P5-5 全修正, 226 tests pass)
9. 運用開始 — hooks の動作確認とパフォーマンスモニタリング
