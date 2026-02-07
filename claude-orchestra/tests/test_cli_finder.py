"""Test 5.8: cli_finder module - CLI path resolution."""
from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest

import cli_finder


class TestFindNode:
    @patch("cli_finder.shutil.which", return_value="C:\\Program Files\\nodejs\\node.exe")
    def test_found_in_path(self, mock_which):
        result = cli_finder.find_node()
        assert result == "C:\\Program Files\\nodejs\\node.exe"

    @patch("cli_finder.shutil.which", return_value=None)
    def test_found_in_programfiles(self, mock_which, tmp_path, monkeypatch):
        # Create a fake node.exe in a known location
        fake_node = tmp_path / "nodejs" / "node.exe"
        fake_node.parent.mkdir(parents=True)
        fake_node.touch()
        monkeypatch.setenv("PROGRAMFILES", str(tmp_path))
        result = cli_finder.find_node()
        assert result == str(fake_node)

    @patch("cli_finder.shutil.which", return_value=None)
    @patch("cli_finder.Path.exists", return_value=False)
    def test_not_found_raises(self, mock_exists, mock_which):
        with pytest.raises(FileNotFoundError, match="Node.js not found"):
            cli_finder.find_node()


class TestFindCodexJs:
    @patch.dict("os.environ", {"CODEX_JS": "C:\\custom\\codex.js"})
    @patch("cli_finder.Path.exists", return_value=True)
    def test_env_override(self, mock_exists):
        result = cli_finder.find_codex_js()
        assert result == "C:\\custom\\codex.js"

    def test_npm_global_path(self, tmp_path, monkeypatch):
        # P5-4: Use real filesystem instead of overly permissive mock
        monkeypatch.setenv("CODEX_JS", "")
        # Create the expected npm global path structure
        npm_codex = tmp_path / "npm" / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
        npm_codex.parent.mkdir(parents=True)
        npm_codex.touch()
        # Override Path.home() to use tmp_path so npm global path resolves
        with patch.object(Path, "home", return_value=tmp_path / "fake_home"):
            # npm global won't match, fall through to npm root -g
            with patch("cli_finder.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout=str(tmp_path / "npm" / "node_modules") + "\n",
                )
                result = cli_finder.find_codex_js()
                assert result == str(npm_codex)

    @patch.dict("os.environ", {"CODEX_JS": ""})
    @patch("cli_finder.Path.exists", return_value=False)
    @patch("cli_finder.subprocess.run")
    def test_npm_root_fallback(self, mock_run, mock_exists):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="C:\\Users\\test\\AppData\\Roaming\\npm\\node_modules\n",
        )
        # exists() returns False for all paths
        with pytest.raises(FileNotFoundError, match="Codex CLI not found"):
            cli_finder.find_codex_js()

    @patch.dict("os.environ", {"CODEX_JS": ""})
    @patch("cli_finder.Path.exists", return_value=False)
    @patch("cli_finder.subprocess.run", side_effect=Exception("npm not found"))
    def test_not_found_raises(self, mock_run, mock_exists):
        with pytest.raises(FileNotFoundError, match="Codex CLI not found"):
            cli_finder.find_codex_js()
