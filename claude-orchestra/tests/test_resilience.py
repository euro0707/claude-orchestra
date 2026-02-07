"""Test 5.7: resilience module - retry, failure classification, fallback."""
from unittest.mock import patch, MagicMock

import pytest

import resilience
from resilience import FailureType, classify_failure, retry_with_backoff, fallback_to_orchestrator


class TestClassifyFailure:
    def test_not_installed(self):
        assert classify_failure("not_installed") == FailureType.PERMANENT

    def test_not_found(self):
        assert classify_failure("command not found") == FailureType.PERMANENT

    def test_auth_error(self):
        assert classify_failure("auth error occurred") == FailureType.PERMANENT

    def test_unauthorized(self):
        assert classify_failure("401 Unauthorized") == FailureType.PERMANENT

    def test_forbidden(self):
        assert classify_failure("403 Forbidden") == FailureType.PERMANENT

    def test_timeout(self):
        assert classify_failure("timeout expired") == FailureType.TIMEOUT

    def test_rate_limit(self):
        assert classify_failure("rate limit exceeded") == FailureType.RATE_LIMIT

    def test_429(self):
        assert classify_failure("HTTP 429") == FailureType.RATE_LIMIT

    def test_quota(self):
        assert classify_failure("quota exhausted") == FailureType.RATE_LIMIT

    def test_signal_killed(self):
        assert classify_failure("unknown", returncode=137) == FailureType.PERMANENT

    def test_default_transient(self):
        assert classify_failure("something weird") == FailureType.TRANSIENT

    def test_empty_error(self):
        assert classify_failure("") == FailureType.TRANSIENT

    def test_none_error(self):
        assert classify_failure(None) == FailureType.TRANSIENT


class TestRetryWithBackoff:
    @patch("resilience.time.sleep")
    def test_success_first_try(self, mock_sleep):
        fn = MagicMock(return_value={"success": True, "data": "ok"})
        result = retry_with_backoff(fn, max_retries=2)
        assert result["success"] is True
        assert result["attempts"] == 1
        mock_sleep.assert_not_called()

    @patch("resilience.time.sleep")
    def test_retry_then_success(self, mock_sleep):
        fn = MagicMock(side_effect=[
            {"success": False, "error": "transient error"},
            {"success": True, "data": "ok"},
        ])
        result = retry_with_backoff(fn, max_retries=2)
        assert result["success"] is True
        assert result["attempts"] == 2

    @patch("resilience.time.sleep")
    def test_permanent_no_retry(self, mock_sleep):
        fn = MagicMock(return_value={"success": False, "error": "not_installed"})
        result = retry_with_backoff(fn, max_retries=3)
        assert result["success"] is False
        assert result["failure_type"] == FailureType.PERMANENT
        assert result["attempts"] == 1
        mock_sleep.assert_not_called()

    @patch("resilience.time.sleep")
    def test_max_retries_exhausted(self, mock_sleep):
        fn = MagicMock(return_value={"success": False, "error": "transient"})
        result = retry_with_backoff(fn, max_retries=2)
        assert result["success"] is False
        assert result["attempts"] == 3  # 1 initial + 2 retries

    @patch("resilience.time.sleep")
    def test_timeout_factor_increases(self, mock_sleep):
        calls = []

        def fn(timeout_factor=1.0):
            calls.append(timeout_factor)
            return {"success": False, "error": "timeout"}

        retry_with_backoff(fn, max_retries=2, timeout_multiplier=2.0)
        assert calls[0] == 1.0
        assert calls[1] == 2.0  # 1.0 * 2.0
        assert calls[2] == 4.0  # 2.0 * 2.0


class TestFallbackToOrchestrator:
    def test_basic_fallback(self):
        result = fallback_to_orchestrator(
            "codex", "review some code", {"error": "not_installed"}
        )
        assert result["success"] is False
        assert result["fallback"] is True
        assert result["agent"] == "codex"
        assert "not_installed" in result["recommendation"]

    def test_task_truncated(self):
        long_task = "x" * 300
        result = fallback_to_orchestrator("gemini", long_task, {"error": "timeout"})
        assert result["fallback"] is True
        # original_task should be present (possibly redacted)
        assert "original_task" in result

    @patch("context_guard.redact_secrets", side_effect=Exception("redact fail"))
    def test_redact_fallback_on_error(self, mock_redact):
        """When redact_secrets fails, truncation fallback is used."""
        result = fallback_to_orchestrator("codex", "short task", {"error": "err"})
        assert "original_task" in result
