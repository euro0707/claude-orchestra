"""Test 5.10: vault_sync module - Obsidian vault integration."""
import json
from unittest.mock import patch, MagicMock
from pathlib import Path
from datetime import datetime

import pytest

import vault_sync


class TestSanitizeFilename:
    def test_basic(self):
        assert vault_sync._sanitize_filename("Hello World") == "hello-world"

    def test_removes_forbidden_chars(self):
        result = vault_sync._sanitize_filename('file<>:"/\\|?*name')
        assert all(c not in result for c in '<>:"/\\|?*')

    def test_unicode_normalization(self):
        # Fullwidth A -> standard A
        result = vault_sync._sanitize_filename("\uff21\uff22\uff23")
        assert result == "abc"

    def test_control_chars_removed(self):
        result = vault_sync._sanitize_filename("hello\x00\x01world")
        assert "\x00" not in result
        assert "\x01" not in result

    def test_max_length(self):
        long_name = "a" * 200
        result = vault_sync._sanitize_filename(long_name)
        assert len(result) <= 80

    def test_reserved_names_prefixed(self):
        result = vault_sync._sanitize_filename("CON")
        assert result.startswith("_")

    def test_com1_reserved(self):
        result = vault_sync._sanitize_filename("COM1")
        assert result.startswith("_")

    def test_empty_fallback(self):
        result = vault_sync._sanitize_filename("...")
        assert result == "untitled"

    def test_leading_trailing_dots_stripped(self):
        result = vault_sync._sanitize_filename("..hello..")
        assert not result.startswith(".")
        assert not result.endswith(".")

    def test_whitespace_to_hyphens(self):
        result = vault_sync._sanitize_filename("hello   world\ttab")
        assert " " not in result
        assert "\t" not in result


class TestGenerateFilename:
    def test_format(self):
        result = vault_sync._generate_filename("My Title")
        # YYYY-MM-DD_HHMMSS_xxxx_slug.md
        assert result.endswith(".md")
        parts = result.split("_")
        assert len(parts) >= 4  # date, time, uuid, slug...

    def test_with_suffix(self):
        result = vault_sync._generate_filename("Title", suffix="checkpoint")
        assert "checkpoint" in result
        assert result.endswith(".md")


class TestBuildFrontmatter:
    def test_basic(self):
        meta = {"date": "2026-02-07", "type": "test"}
        result = vault_sync._build_frontmatter(meta)
        assert result.startswith("---")
        assert result.endswith("---")
        assert '"2026-02-07"' in result

    def test_list_values(self):
        meta = {"tags": ["a", "b", "c"]}
        result = vault_sync._build_frontmatter(meta)
        assert '["a", "b", "c"]' in result

    def test_bool_values(self):
        meta = {"approved": True}
        result = vault_sync._build_frontmatter(meta)
        assert "approved: true" in result

    def test_backslash_escaping(self):
        meta = {"path": "C:\\Users\\skyeu"}
        result = vault_sync._build_frontmatter(meta)
        assert "C:\\\\Users\\\\skyeu" in result

    def test_quote_escaping(self):
        meta = {"title": 'He said "hello"'}
        result = vault_sync._build_frontmatter(meta)
        assert '\\"hello\\"' in result


class TestYamlEscape:
    def test_backslash(self):
        assert vault_sync._yaml_escape("C:\\Users") == "C:\\\\Users"

    def test_quotes(self):
        assert vault_sync._yaml_escape('"hello"') == '\\"hello\\"'

    def test_order_matters(self):
        # Backslashes first, then quotes
        result = vault_sync._yaml_escape('C:\\"path"')
        assert result == 'C:\\\\\\"path\\"'


class TestWriteWithFallback:
    def test_local_and_vault(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vault_sync, "LOCAL_CACHE", tmp_path / "cache")
        monkeypatch.setattr(vault_sync, "VAULT_BASE", tmp_path / "vault" / "90-Claude")
        monkeypatch.setattr(vault_sync, "VAULT_ROOT", tmp_path / "vault")
        (tmp_path / "vault").mkdir()

        result = vault_sync._write_with_fallback("sessions", "test.md", "# Test")
        assert result  # non-empty path
        assert Path(result).exists()

    def test_local_only_when_vault_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vault_sync, "LOCAL_CACHE", tmp_path / "cache")
        monkeypatch.setattr(vault_sync, "VAULT_ROOT", tmp_path / "nonexistent")
        monkeypatch.setattr(vault_sync, "PENDING_FILE", tmp_path / "cache" / "pending_sync.txt")

        result = vault_sync._write_with_fallback("sessions", "test.md", "# Test")
        assert result
        assert (tmp_path / "cache" / "sessions" / "test.md").exists()


class TestSaveCheckpoint:
    def test_creates_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vault_sync, "LOCAL_CACHE", tmp_path / "cache")
        monkeypatch.setattr(vault_sync, "VAULT_ROOT", tmp_path / "nonexistent")
        monkeypatch.setattr(vault_sync, "PENDING_FILE", tmp_path / "cache" / "pending_sync.txt")

        result = vault_sync.save_checkpoint(
            title="Test Session",
            summary="Did some testing",
            context={"task": "test"},
        )
        assert result
        content = Path(result).read_text(encoding="utf-8")
        assert "Test Session" in content
        assert "Did some testing" in content


class TestSaveCodexReview:
    def test_creates_review_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vault_sync, "LOCAL_CACHE", tmp_path / "cache")
        monkeypatch.setattr(vault_sync, "VAULT_ROOT", tmp_path / "nonexistent")
        monkeypatch.setattr(vault_sync, "PENDING_FILE", tmp_path / "cache" / "pending_sync.txt")

        review = {
            "approved": True,
            "confidence": 8,
            "issues": [{"severity": "low", "description": "minor issue"}],
            "summary": "Looks good",
        }
        result = vault_sync.save_codex_review("Plan Review", review)
        assert result
        content = Path(result).read_text(encoding="utf-8")
        assert "Plan Review" in content
        assert "Approved" in content


class TestSaveGeminiResearch:
    def test_creates_research_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vault_sync, "LOCAL_CACHE", tmp_path / "cache")
        monkeypatch.setattr(vault_sync, "VAULT_ROOT", tmp_path / "nonexistent")
        monkeypatch.setattr(vault_sync, "PENDING_FILE", tmp_path / "cache" / "pending_sync.txt")

        result = vault_sync.save_gemini_research(
            title="Python Research",
            query="latest Python features",
            result="Python 3.13 adds...",
            sources=["python.org", "docs.python.org"],
        )
        assert result
        content = Path(result).read_text(encoding="utf-8")
        assert "Python Research" in content
        assert "latest Python features" in content
        assert "python.org" in content

    def test_without_sources(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vault_sync, "LOCAL_CACHE", tmp_path / "cache")
        monkeypatch.setattr(vault_sync, "VAULT_ROOT", tmp_path / "nonexistent")
        monkeypatch.setattr(vault_sync, "PENDING_FILE", tmp_path / "cache" / "pending_sync.txt")

        result = vault_sync.save_gemini_research(
            title="Quick Research", query="question", result="answer"
        )
        assert result


class TestSyncPending:
    def test_no_pending_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vault_sync, "PENDING_FILE", tmp_path / "nonexistent.txt")
        result = vault_sync.sync_pending()
        assert result == []

    def test_vault_unavailable(self, tmp_path, monkeypatch):
        pending = tmp_path / "pending_sync.txt"
        pending.write_text("2026-01-01T00:00:00|sessions|test.md\n")
        monkeypatch.setattr(vault_sync, "PENDING_FILE", pending)
        monkeypatch.setattr(vault_sync, "VAULT_ROOT", tmp_path / "nonexistent")
        result = vault_sync.sync_pending()
        assert result == []

    def test_successful_sync(self, tmp_path, monkeypatch):
        # Setup local cache with a pending file
        cache = tmp_path / "cache"
        (cache / "sessions").mkdir(parents=True)
        (cache / "sessions" / "test.md").write_text("# Test")
        pending = cache / "pending_sync.txt"
        pending.write_text("2026-01-01T00:00:00|sessions|test.md\n")

        vault = tmp_path / "vault"
        vault.mkdir()

        monkeypatch.setattr(vault_sync, "LOCAL_CACHE", cache)
        monkeypatch.setattr(vault_sync, "VAULT_ROOT", vault)
        monkeypatch.setattr(vault_sync, "VAULT_BASE", vault / "90-Claude")
        monkeypatch.setattr(vault_sync, "PENDING_FILE", pending)

        result = vault_sync.sync_pending()
        assert "test.md" in result
        assert not pending.exists()  # Pending file deleted after sync


class TestRecordReviewIssues:
    def test_records_moderate_issues(self, tmp_path):
        issues = [
            {"severity": "medium", "description": "Missing validation", "suggestion": "Add check"},
            {"severity": "low", "description": "Minor style issue"},
        ]
        vault_sync.record_review_issues(str(tmp_path), "Test Review", issues)
        mistakes = (tmp_path / "notes" / "mistakes.md").read_text(encoding="utf-8")
        rules = (tmp_path / "notes" / "rules-local.md").read_text(encoding="utf-8")
        # medium -> moderate, recorded
        assert "Missing validation" in mistakes
        assert "RL-" in rules
        # low -> minor, skipped
        assert "Minor style issue" not in mistakes

    def test_empty_issues_noop(self, tmp_path):
        vault_sync.record_review_issues(str(tmp_path), "Review", [])
        assert not (tmp_path / "notes").exists()

    def test_severity_mapping(self, tmp_path):
        issues = [
            {"severity": "critical", "description": "Security hole"},
            {"severity": "high", "description": "Data loss risk"},
        ]
        vault_sync.record_review_issues(str(tmp_path), "Review", issues)
        content = (tmp_path / "notes" / "mistakes.md").read_text(encoding="utf-8")
        assert "major" in content
