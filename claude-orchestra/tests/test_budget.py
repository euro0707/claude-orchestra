"""Test 5.6: budget module - token tracking and concurrency control."""
import json

import pytest

import budget


class TestCheckBudget:
    def test_allowed_within_budget(self, mock_budget_file):
        budget.reset_session()
        result = budget.check_budget(estimated_tokens=1000)
        assert result["allowed"] is True
        assert result["remaining"] == 500000

    def test_not_allowed_over_budget(self, mock_budget_file):
        budget.reset_session()
        budget.record_call("codex", 499000)
        result = budget.check_budget(estimated_tokens=10000)
        assert result["allowed"] is False

    def test_fallback_on_error(self, tmp_path, monkeypatch):
        """On file I/O error, returns permissive fallback."""
        bad_path = tmp_path / "nonexistent" / "deep" / "budget.json"
        # Make the parent unwritable to force an error
        monkeypatch.setattr(budget, "_BUDGET_FILE", bad_path)
        # Force parent creation to fail
        import pathlib
        original_mkdir = pathlib.Path.mkdir

        def fail_mkdir(self, *a, **kw):
            raise PermissionError("denied")

        monkeypatch.setattr(pathlib.Path, "mkdir", fail_mkdir)
        result = budget.check_budget()
        assert result["allowed"] is True
        assert result.get("fallback") is True


class TestRecordCall:
    def test_records_tokens(self, mock_budget_file):
        budget.reset_session()
        budget.record_call("codex", 5000, duration_ms=200)
        summary = budget.get_summary()
        assert summary["total_tokens"] == 5000
        assert summary["total_calls"] == 1
        assert summary["by_agent"]["codex"]["tokens"] == 5000

    def test_multiple_agents(self, mock_budget_file):
        budget.reset_session()
        budget.record_call("codex", 3000)
        budget.record_call("gemini", 2000)
        summary = budget.get_summary()
        assert summary["total_tokens"] == 5000
        assert summary["total_calls"] == 2
        assert "codex" in summary["by_agent"]
        assert "gemini" in summary["by_agent"]


class TestConcurrencySlots:
    def test_acquire_and_release(self, mock_budget_file, monkeypatch):
        monkeypatch.setattr(budget, "DEFAULT_MAX_CONCURRENT", 2)
        budget.reset_session()
        assert budget.acquire_slot("codex") is True
        assert budget.acquire_slot("gemini") is True
        # Max concurrent = 2
        assert budget.acquire_slot("extra") is False
        budget.release_slot()
        assert budget.acquire_slot("extra") is True

    def test_release_never_goes_negative(self, mock_budget_file):
        budget.reset_session()
        budget.release_slot()  # release without acquire
        result = budget.check_budget()
        assert result["active_calls"] == 0


class TestResetSession:
    def test_resets_all_state(self, mock_budget_file):
        budget.reset_session()
        budget.record_call("codex", 10000)
        budget.acquire_slot("codex")
        budget.reset_session()
        summary = budget.get_summary()
        assert summary["total_tokens"] == 0
        assert summary["total_calls"] == 0
        result = budget.check_budget()
        assert result["active_calls"] == 0


class TestGetSummary:
    def test_empty_session(self, mock_budget_file):
        budget.reset_session()
        summary = budget.get_summary()
        assert summary["total_tokens"] == 0
        assert summary["total_calls"] == 0
        assert summary["remaining_tokens"] == 500000
        assert summary["by_agent"] == {}

    def test_by_agent_aggregation(self, mock_budget_file):
        budget.reset_session()
        budget.record_call("codex", 1000)
        budget.record_call("codex", 2000)
        budget.record_call("gemini", 500)
        summary = budget.get_summary()
        assert summary["by_agent"]["codex"]["calls"] == 2
        assert summary["by_agent"]["codex"]["tokens"] == 3000
        assert summary["by_agent"]["gemini"]["calls"] == 1
