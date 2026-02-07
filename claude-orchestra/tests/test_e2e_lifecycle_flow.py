"""E2E 6.1 (supplement): Cross-module lifecycle flow.

Tests the full agent call lifecycle:
  budget acquire → context_guard → (mock) codex call → vault checkpoint → budget release

This test does NOT execute real hook scripts (no @pytest.mark.e2e needed).
It verifies that library modules integrate correctly across a session.
"""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import budget
from budget import (
    acquire_slot,
    check_budget,
    get_summary,
    record_call,
    release_slot,
    reset_session,
)
from context_guard import guard_context, ContextGuardError
from vault_sync import save_checkpoint, save_codex_review


class TestAgentCallLifecycle:
    """6.1: Full lifecycle — acquire slot → guard → call → save → release."""

    def test_full_agent_call_flow(self, mock_budget_file, mock_vault, monkeypatch):
        """Simulate a complete agent call through all layers."""
        monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "0")
        monkeypatch.setenv("ORCHESTRA_CONSENT_POLICY", "redact")

        # Step 1: Acquire slot
        assert acquire_slot("codex") is True
        assert check_budget(estimated_tokens=10000)["allowed"] is True

        # Step 2: Guard context (should pass clean content)
        code_content = "def hello():\n    return 'world'"
        guarded = guard_context(code_content, source_files=None)
        assert guarded == code_content  # clean content passes through

        # Step 3: Simulate codex call (mock) and record usage
        record_call("codex", 8000, duration_ms=250)

        # Step 4: Save review result to vault
        review_result = {
            "approved": True,
            "confidence": 8,
            "summary": "Code looks good",
            "issues": [],
        }
        path = save_codex_review("Lifecycle Test", review_result, code_content)
        assert path
        assert Path(path).exists()
        content = Path(path).read_text(encoding="utf-8")
        assert "Lifecycle Test" in content

        # Step 5: Release slot
        release_slot()

        # Step 6: Verify final state
        summary = get_summary()
        assert summary["total_tokens"] == 8000
        assert summary["total_calls"] == 1
        assert summary["by_agent"]["codex"]["tokens"] == 8000

        result = check_budget(estimated_tokens=0)
        assert result["active_calls"] == 0

    def test_secret_blocked_before_codex_call(self, mock_budget_file, monkeypatch):
        """Secret content is caught by guard before reaching codex."""
        monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "0")
        monkeypatch.setenv("ORCHESTRA_CONSENT_POLICY", "block")

        # Acquire slot
        assert acquire_slot("codex") is True

        # Guard blocks secret content
        secret_content = 'api_key = "sk-1234567890abcdefghijklmnop"'
        with pytest.raises(ContextGuardError, match="secrets detected"):
            guard_context(secret_content, source_files=None)

        # Slot should still be released cleanly
        release_slot()
        assert check_budget(estimated_tokens=0)["active_calls"] == 0


class TestSessionCheckpointLifecycle:
    """6.1/6.4: Session with multiple operations → checkpoint → verify state."""

    def test_multi_operation_then_checkpoint(self, mock_budget_file, mock_vault):
        # Simulate multiple agent calls in a session
        acquire_slot("codex")
        record_call("codex", 50000, 1000)
        release_slot()

        acquire_slot("gemini")
        record_call("gemini", 30000, 800)
        release_slot()

        # Save session checkpoint
        summary = get_summary()
        path = save_checkpoint(
            "Multi-Op Session",
            "Ran codex review and gemini research",
            {
                "total_tokens": summary["total_tokens"],
                "total_calls": summary["total_calls"],
                "agents_used": list(summary["by_agent"].keys()),
            },
        )

        # Verify checkpoint
        assert Path(path).exists()
        content = Path(path).read_text(encoding="utf-8")
        assert "Multi-Op Session" in content
        assert "## Summary" in content

        # Verify budget summary is consistent
        assert summary["total_tokens"] == 80000
        assert summary["total_calls"] == 2
        assert "codex" in summary["by_agent"]
        assert "gemini" in summary["by_agent"]

    def test_checkpoint_after_reset_has_clean_state(self, mock_budget_file, mock_vault):
        """After reset, checkpoint reflects zero state."""
        record_call("codex", 100000)
        reset_session()

        summary = get_summary()
        path = save_checkpoint(
            "Post-Reset Session",
            "Session after reset",
            {"total_tokens": summary["total_tokens"]},
        )

        content = Path(path).read_text(encoding="utf-8")
        assert "Post-Reset Session" in content

        # Budget is clean
        assert summary["total_tokens"] == 0
        assert summary["remaining_tokens"] == 500000


class TestGuardRedactThenSaveFlow:
    """6.3/6.4: Secret redacted by guard → redacted content saved to vault."""

    def test_redacted_content_saved_to_checkpoint(self, mock_budget_file, mock_vault, monkeypatch):
        monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "0")
        monkeypatch.setenv("ORCHESTRA_CONSENT_POLICY", "redact")

        # Content with secret (Python assignment format matches _SECRET_PATTERNS)
        raw_content = 'api_key = "sk-abcdefghij1234567890abcdef"'
        guarded = guard_context(raw_content, source_files=None)

        # Secret should be redacted
        assert "sk-abcdefghij" not in guarded
        assert "[REDACTED]" in guarded

        # Save redacted content as checkpoint context
        path = save_checkpoint(
            "Redacted Session",
            "Session with redacted secrets",
            {"redacted_content": guarded},
        )

        # Verify saved file has redacted content, not original
        file_content = Path(path).read_text(encoding="utf-8")
        assert "sk-abcdefghij" not in file_content
        assert "REDACTED" in file_content
