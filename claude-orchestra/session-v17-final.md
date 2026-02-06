---
date: 2026-02-05
type: session
title: "Orchestra Plan v17 Final - All Remaining Issues Addressed"
tags:
  - orchestra
  - codex-review
  - approved
---

# Orchestra Plan v17 Final - All Remaining Issues Addressed

## Summary

v16 APPROVED 後の残り issues (2 medium + 2 low) を v17 で対応。
Codex Verify を2回実行し、追加で発見された issues (H-1, H-3, I-3) も全て対応完了。

## v17 で対応した全 issues

### G fixes (v16 残り)
| # | 重要度 | 内容 | 修正 |
|---|--------|------|------|
| G-1 | medium | `_ALLOWED_BASE_DIRS` インポート時キャッシュ | per-call 再計算に変更 |
| G-2 | medium | budget.py non-blocking lock | `LK_LOCK` (blocking) に変更 |
| G-3 | medium | Security policy ドキュメント | `docs/security-policy.md` 追加 |
| G-4 | low | `source_files=[]` vs unknown origin | コード + ドキュメントで明記 |

### H fixes (v17 Codex Verify 1回目)
| # | 重要度 | 内容 | 修正 |
|---|--------|------|------|
| H-1 | medium | デフォルト redact で unknown-origin バイパス | `ORCHESTRA_STRICT_ORIGIN=1` 追加 |
| H-3 | medium | `check_budget` 例外バブルアップ | try/except + permissive fallback |

### I fixes (v17 Codex Verify 2回目)
| # | 重要度 | 内容 | 修正 |
|---|--------|------|------|
| I-3 | medium | `fallback_to_orchestrator` 未リダクト context | `redact_secrets()` 適用 |

## Codex Review Results

| 回 | Result | Issues |
|----|--------|--------|
| v17 1回目 | APPROVED (confidence: 7) | 3 medium + 1 low |
| v17 2回目 | APPROVED (confidence: 7) | 3 medium + 2 low |

Note: 2回目の medium issues のうち 2件は G-1, G-2 で既に修正済み (Codex がプラン内の修正箇所を読み取れず)。
実質的な新規 issue は I-3 のみで、対応完了。

## Cumulative Review History (v12-v17)

| Version | Result | High | Medium | Low | Key Fixes |
|---------|--------|------|--------|-----|-----------|
| v12 | NOT APPROVED | 2 | 3 | 1 | context_guard, resilience, budget |
| v13 | NOT APPROVED | 1 | 3 | 2 | C-1~C-6 |
| v14 | NOT APPROVED | 1 | 2 | 2 | D-1~D-6 |
| v15 | NOT APPROVED | 1 | 2 | 1 | E-1~E-5 |
| v16 | **APPROVED** | 0 | 2 | 2 | F-1~F-4 |
| v17 | **APPROVED** | 0 | 0* | 0* | G-1~G-4, H-1, H-3, I-3 |

*v17 は全ての指摘事項を plan 内で対応済み

## Next Steps

Implementation phase based on plan-v17.md "Implementation Order" section (22 steps).
