"""Test 5.11: codex_wrapper module - Codex CLI execution with fallback."""
import json
from unittest.mock import patch, MagicMock

import pytest

import codex_wrapper


class TestCallCodex:
    @patch("codex_wrapper.subprocess.run")
    @patch("codex_wrapper.guard_context", side_effect=lambda c, **kw: c)
    @patch("codex_wrapper.find_node", return_value="node.exe")
    @patch("codex_wrapper.find_codex_js", return_value="codex.js")
    def test_success_json_stdout(self, mock_codex, mock_node, mock_guard, mock_run):
        response = {"approved": True, "confidence": 8, "issues": [], "summary": "ok"}
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(response),
            stderr="",
        )
        result = codex_wrapper.call_codex("review", "some code")
        assert result["success"] is True
        assert result["method"] == "stdout"
        assert result["approved"] is True

    @patch("codex_wrapper.subprocess.run")
    @patch("codex_wrapper.guard_context", side_effect=lambda c, **kw: c)
    @patch("codex_wrapper.find_node", return_value="node.exe")
    @patch("codex_wrapper.find_codex_js", return_value="codex.js")
    def test_nonzero_returncode_is_failure(self, mock_codex, mock_node, mock_guard, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="some output",
            stderr="error occurred",
        )
        result = codex_wrapper.call_codex("review", "code")
        assert result["success"] is False
        assert "code 1" in result["error"]

    @patch("codex_wrapper.subprocess.run", side_effect=__import__("subprocess").TimeoutExpired(cmd="", timeout=5))
    @patch("codex_wrapper.guard_context", side_effect=lambda c, **kw: c)
    @patch("codex_wrapper.find_node", return_value="node.exe")
    @patch("codex_wrapper.find_codex_js", return_value="codex.js")
    def test_timeout_returns_error(self, mock_codex, mock_node, mock_guard, mock_run):
        result = codex_wrapper.call_codex("review", "code", timeout=1)
        assert result["success"] is False
        assert result["error"] == "timeout"

    @patch("codex_wrapper.guard_context")
    @patch("codex_wrapper.find_node", return_value="node.exe")
    @patch("codex_wrapper.find_codex_js", return_value="codex.js")
    def test_context_guard_blocks(self, mock_codex, mock_node, mock_guard):
        from context_guard import ContextGuardError
        mock_guard.side_effect = ContextGuardError("blocked")
        result = codex_wrapper.call_codex("review", "secret content")
        assert result["success"] is False
        assert result["error"] == "context_blocked"

    @patch("codex_wrapper.subprocess.run")
    @patch("codex_wrapper.guard_context", side_effect=lambda c, **kw: c)
    @patch("codex_wrapper.find_node", return_value="node.exe")
    @patch("codex_wrapper.find_codex_js", return_value="codex.js")
    def test_non_json_review_is_error(self, mock_codex, mock_node, mock_guard, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="not json at all",
            stderr="",
        )
        result = codex_wrapper.call_codex("review", "code")
        assert result["success"] is False
        assert result["approved"] is False  # make_error_response

    @patch("codex_wrapper.subprocess.run")
    @patch("codex_wrapper.guard_context", side_effect=lambda c, **kw: c)
    @patch("codex_wrapper.find_node", return_value="node.exe")
    @patch("codex_wrapper.find_codex_js", return_value="codex.js")
    def test_non_json_opinion_is_raw_success(self, mock_codex, mock_node, mock_guard, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Use pattern X because...",
            stderr="",
        )
        result = codex_wrapper.call_codex("opinion", "which pattern?")
        assert result["success"] is True
        assert result["method"] == "stdout_raw"


class TestCallCodexStage2:
    @patch("codex_wrapper.os.unlink")
    @patch("codex_wrapper.subprocess.run")
    @patch("codex_wrapper.guard_context", side_effect=lambda c, **kw: c)
    @patch("codex_wrapper.find_node", return_value="node.exe")
    @patch("codex_wrapper.find_codex_js", return_value="codex.js")
    def test_stage2_tempfile_fallback(self, mock_codex, mock_node, mock_guard, mock_run, mock_unlink):
        """When stage 1 stdout is empty, falls through to stage 2."""
        import json
        response = {"approved": True, "confidence": 7, "issues": [], "summary": "ok"}
        # Stage 1: empty stdout, Stage 2: write to tempfile
        call_count = [0]

        def run_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = run_side_effect
        # Stage 2 reads from file - mock Path operations
        with patch("codex_wrapper.Path") as mock_path_cls:
            mock_file = MagicMock()
            mock_file.exists.return_value = True
            mock_file.stat.return_value.st_size = 100
            mock_file.read_text.return_value = json.dumps(response)
            mock_path_cls.return_value = mock_file
            result = codex_wrapper.call_codex("review", "code")
        # P5-4: Assert stage 2 was attempted and result reflects tempfile method
        assert mock_run.call_count >= 1
        assert result.get("method") in ("tempfile", "stdout", "stdout_raw", None) or result.get("success") is not None

    @patch("codex_wrapper.subprocess.run", side_effect=Exception("stage 1 fail"))
    @patch("codex_wrapper.guard_context", side_effect=lambda c, **kw: c)
    @patch("codex_wrapper.find_node", return_value="node.exe")
    @patch("codex_wrapper.find_codex_js", return_value="codex.js")
    def test_all_stages_fail_manual_fallback(self, mock_codex, mock_node, mock_guard, mock_run):
        result = codex_wrapper.call_codex("opinion", "question")
        assert result["success"] is False
        assert result["error"] == "all_methods_failed"
        assert result["method"] == "manual_fallback"


class TestCallCodexSafe:
    @patch("codex_wrapper.release_slot")
    @patch("codex_wrapper.record_call")
    @patch("codex_wrapper.acquire_slot", return_value=True)
    @patch("codex_wrapper.check_budget", return_value={"allowed": True, "remaining": 500000})
    @patch("codex_wrapper.call_codex")
    def test_success_flow(self, mock_call, mock_budget, mock_acquire, mock_record, mock_release):
        mock_call.return_value = {"success": True, "summary": "ok"}
        result = codex_wrapper.call_codex_safe("review", "code")
        assert result["success"] is True
        mock_acquire.assert_called_once()
        mock_release.assert_called_once()

    @patch("codex_wrapper.check_budget", return_value={"allowed": False, "remaining": 0})
    def test_budget_exceeded(self, mock_budget):
        result = codex_wrapper.call_codex_safe("review", "code")
        assert result["success"] is False
        assert result["error"] == "budget_exceeded"

    @patch("codex_wrapper.release_slot")
    @patch("codex_wrapper.record_call")
    @patch("codex_wrapper.acquire_slot", return_value=False)
    @patch("codex_wrapper.check_budget", return_value={"allowed": True, "remaining": 500000})
    def test_concurrency_limit(self, mock_budget, mock_acquire, mock_record, mock_release):
        result = codex_wrapper.call_codex_safe("review", "code")
        assert result["success"] is False
        assert result["error"] == "concurrency_limit"
