"""Test bootstrap module - project dir detection and env setup."""
from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest

import bootstrap


class TestDetectProjectDir:
    @patch("bootstrap.subprocess.run")
    def test_git_root_detected(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="/c/Users/skyeu/project\n"
        )
        result = bootstrap._detect_project_dir()
        assert result is not None
        # Should be normalized from MSYS2 path
        assert "C:" in result or "project" in result

    @patch("bootstrap.subprocess.run", side_effect=Exception("no git"))
    def test_fallback_to_cwd(self, mock_run):
        result = bootstrap._detect_project_dir()
        assert result is not None  # Falls back to cwd

    @patch("bootstrap.subprocess.run")
    def test_nonzero_returncode(self, mock_run):
        mock_run.return_value = MagicMock(returncode=128, stdout="", stderr="not a git repo")
        result = bootstrap._detect_project_dir()
        # Should fall back to cwd
        assert result is not None


class TestLoadSettingsProjectDir:
    def test_reads_settings(self, tmp_path, monkeypatch):
        settings = tmp_path / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        import json
        settings.write_text(json.dumps({"projectDir": str(tmp_path / "myproject")}))

        with patch.object(Path, "home", return_value=tmp_path):
            result = bootstrap._load_settings_project_dir()
        assert result is not None

    def test_no_settings_file(self, tmp_path, monkeypatch):
        with patch.object(Path, "home", return_value=tmp_path):
            result = bootstrap._load_settings_project_dir()
        assert result is None
