"""Test 5.9: env_check module - environment validation."""
from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest

import env_check


class TestCheckNode:
    @patch("env_check.subprocess.run")
    @patch("env_check.shutil.which", return_value="C:\\nodejs\\node.exe")
    def test_node_available(self, mock_which, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="v20.0.0\n", stderr=""
        )
        result = env_check.check_node()
        assert result["available"] is True
        assert result["version"] == "v20.0.0"

    @patch("env_check.shutil.which", return_value=None)
    def test_node_not_found(self, mock_which):
        result = env_check.check_node()
        assert result["available"] is False

    @patch("env_check.subprocess.run")
    @patch("env_check.shutil.which", return_value="C:\\nodejs\\node.exe")
    def test_node_nonzero_exit(self, mock_which, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="error"
        )
        result = env_check.check_node()
        assert result["available"] is False


class TestCheckCodex:
    @patch("env_check.subprocess.run")
    @patch("cli_finder.find_node", return_value="node.exe")
    @patch("cli_finder.find_codex_js", return_value="codex.js")
    def test_codex_available(self, mock_codex, mock_node, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="0.92.0\n", stderr=""
        )
        result = env_check.check_codex()
        assert result["available"] is True
        assert result["version"] == "0.92.0"

    @patch("cli_finder.find_node", side_effect=FileNotFoundError("no node"))
    def test_codex_no_node(self, mock_node):
        result = env_check.check_codex()
        assert result["available"] is False


class TestCheckGemini:
    @patch("env_check.subprocess.run")
    @patch("env_check.shutil.which", return_value="C:\\bin\\gemini.exe")
    def test_gemini_available(self, mock_which, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="1.0.0\n", stderr=""
        )
        result = env_check.check_gemini()
        assert result["available"] is True

    @patch("env_check.shutil.which", return_value=None)
    def test_gemini_not_found_graceful(self, mock_which):
        result = env_check.check_gemini()
        assert result["available"] is False
        assert "degradation" in result


class TestCheckPythonTools:
    @patch("env_check.subprocess.run")
    @patch("env_check.shutil.which")
    def test_ruff_available(self, mock_which, mock_run):
        def which_side(tool):
            return "ruff.exe" if tool == "ruff" else None

        mock_which.side_effect = which_side
        mock_run.return_value = MagicMock(
            returncode=0, stdout="ruff 0.8.0\n", stderr=""
        )
        result = env_check.check_python_tools()
        assert result["ruff"]["available"] is True
        assert result["ty"]["available"] is False
        assert result["uv"]["available"] is False


class TestCheckVault:
    @patch("env_check.Path.exists", return_value=True)
    def test_vault_available(self, mock_exists):
        result = env_check.check_vault()
        assert result["available"] is True

    @patch("env_check.Path.exists", return_value=False)
    def test_vault_not_available(self, mock_exists):
        result = env_check.check_vault()
        assert result["available"] is False
        assert "degradation" in result


class TestFullCheck:
    @patch("env_check.check_vault", return_value={"available": False})
    @patch("env_check.check_python_tools", return_value={
        "ruff": {"available": True}, "ty": {"available": False}, "uv": {"available": False}
    })
    @patch("env_check.check_gemini", return_value={"available": False})
    @patch("env_check.check_codex", return_value={"available": True})
    @patch("env_check.check_node", return_value={"available": True})
    def test_capabilities_matrix(self, *mocks):
        result = env_check.full_check()
        caps = result["capabilities"]
        assert caps["codex_delegation"] is True
        assert caps["gemini_delegation"] is False
        assert caps["lint_on_save"] is True
        assert caps["vault_sync"] is False
