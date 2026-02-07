"""Test 5.12: gemini_wrapper module - Gemini CLI with graceful degradation."""
import json
from unittest.mock import patch, MagicMock

import pytest

import gemini_wrapper


class TestFindGemini:
    @patch("gemini_wrapper.shutil.which", return_value="C:\\bin\\gemini.exe")
    def test_found(self, mock_which):
        assert gemini_wrapper.find_gemini() == "C:\\bin\\gemini.exe"

    @patch("gemini_wrapper.shutil.which", return_value=None)
    def test_not_found(self, mock_which):
        assert gemini_wrapper.find_gemini() is None


class TestCallGemini:
    @patch("gemini_wrapper.find_gemini", return_value=None)
    def test_not_installed_graceful(self, mock_find):
        result = gemini_wrapper.call_gemini("research Python")
        assert result["success"] is False
        assert result["error"] == "not_installed"

    @patch("gemini_wrapper.subprocess.run")
    @patch("gemini_wrapper.guard_context", side_effect=lambda c, **kw: c)
    @patch("gemini_wrapper.find_gemini", return_value="gemini.exe")
    def test_json_response(self, mock_find, mock_guard, mock_run):
        response = {"result": "Python 3.13 is latest", "sources": ["python.org"]}
        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps(response), stderr=""
        )
        result = gemini_wrapper.call_gemini("latest Python version")
        assert result["success"] is True
        assert result["method"] == "json"
        assert result["result"] == "Python 3.13 is latest"

    @patch("gemini_wrapper.subprocess.run")
    @patch("gemini_wrapper.guard_context", side_effect=lambda c, **kw: c)
    @patch("gemini_wrapper.find_gemini", return_value="gemini.exe")
    def test_raw_text_response(self, mock_find, mock_guard, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="Some plain text research result", stderr=""
        )
        result = gemini_wrapper.call_gemini("research something")
        assert result["success"] is True
        assert result["method"] == "raw"
        assert "plain text" in result["raw_output"]

    @patch("gemini_wrapper.subprocess.run")
    @patch("gemini_wrapper.guard_context", side_effect=lambda c, **kw: c)
    @patch("gemini_wrapper.find_gemini", return_value="gemini.exe")
    def test_empty_output(self, mock_find, mock_guard, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = gemini_wrapper.call_gemini("query")
        assert result["success"] is False
        assert result["error"] == "empty_output"

    @patch("gemini_wrapper.subprocess.run", side_effect=__import__("subprocess").TimeoutExpired(cmd="", timeout=5))
    @patch("gemini_wrapper.guard_context", side_effect=lambda c, **kw: c)
    @patch("gemini_wrapper.find_gemini", return_value="gemini.exe")
    def test_timeout(self, mock_find, mock_guard, mock_run):
        result = gemini_wrapper.call_gemini("query", timeout=1)
        assert result["success"] is False
        assert result["error"] == "timeout"

    @patch("gemini_wrapper.guard_context")
    @patch("gemini_wrapper.find_gemini", return_value="gemini.exe")
    def test_context_guard_blocks(self, mock_find, mock_guard):
        from context_guard import ContextGuardError
        mock_guard.side_effect = ContextGuardError("blocked")
        result = gemini_wrapper.call_gemini("secret query")
        assert result["success"] is False
        assert result["error"] == "context_blocked"


class TestCallGeminiSafe:
    @patch("gemini_wrapper.release_slot")
    @patch("gemini_wrapper.record_call")
    @patch("gemini_wrapper.acquire_slot", return_value=True)
    @patch("gemini_wrapper.check_budget", return_value={"allowed": True, "remaining": 500000})
    @patch("gemini_wrapper.call_gemini")
    def test_success_flow(self, mock_call, mock_budget, mock_acquire, mock_record, mock_release):
        mock_call.return_value = {"success": True, "result": "findings"}
        result = gemini_wrapper.call_gemini_safe("query")
        assert result["success"] is True
        mock_release.assert_called_once()

    @patch("gemini_wrapper.check_budget", return_value={"allowed": False, "remaining": 0})
    def test_budget_exceeded(self, mock_budget):
        result = gemini_wrapper.call_gemini_safe("query")
        assert result["success"] is False
        assert result["error"] == "budget_exceeded"
