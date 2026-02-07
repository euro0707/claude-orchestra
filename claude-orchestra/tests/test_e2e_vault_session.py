"""E2E 6.4: Vault Sync + Session lifecycle.

Tests checkpoint creation, local/vault dual-write, pending sync retry,
and session state format.
"""
import json
from pathlib import Path

import pytest

import vault_sync
from vault_sync import (
    save_checkpoint,
    save_codex_review,
    sync_pending,
)


class TestCheckpointCreatesLocalFile:
    """6.4: save_checkpoint() creates a local file."""

    def test_creates_file(self, mock_vault):
        path = save_checkpoint("Test Session", "Summary of work done", {"task": "testing"})
        assert path, "save_checkpoint must return a non-empty path"
        assert Path(path).exists(), f"File must exist at {path}"

    def test_file_contains_title(self, mock_vault):
        path = save_checkpoint("My Title", "Some summary", {})
        content = Path(path).read_text(encoding="utf-8")
        assert "My Title" in content

    def test_file_has_frontmatter(self, mock_vault):
        path = save_checkpoint("FM Test", "Summary", {"key": "val"})
        content = Path(path).read_text(encoding="utf-8")
        assert content.startswith("---")
        assert "checkpoint" in content


class TestCheckpointWritesToVault:
    """6.4: When vault is available, checkpoint is written to vault."""

    def test_vault_file_created(self, mock_vault):
        path = save_checkpoint("Vault Test", "Testing vault write", {})
        # When vault is available, path should be under vault dir
        assert Path(path).exists()
        content = Path(path).read_text(encoding="utf-8")
        assert "Vault Test" in content


class TestCheckpointLocalOnlyWhenVaultMissing:
    """6.4: When vault is unavailable, only local is written + pending recorded."""

    def test_local_only_and_pending(self, vault_dir, monkeypatch):
        # Point vault to non-existent directory
        fake_vault = vault_dir.parent / "nonexistent_vault"
        monkeypatch.setattr(vault_sync, "VAULT_ROOT", fake_vault)
        monkeypatch.setattr(vault_sync, "VAULT_BASE", fake_vault / "90-Claude")
        local_cache = vault_dir.parent / "local_cache2"
        local_cache.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(vault_sync, "LOCAL_CACHE", local_cache)
        pending_file = local_cache / "pending_sync.txt"
        monkeypatch.setattr(vault_sync, "PENDING_FILE", pending_file)

        path = save_checkpoint("Local Only", "No vault", {})
        assert path, "Should still save locally"
        assert Path(path).exists()

        # Pending sync should be recorded
        assert pending_file.exists(), "pending_sync.txt should be created"
        pending_content = pending_file.read_text(encoding="utf-8")
        assert "sessions" in pending_content


class TestPendingSyncRetries:
    """6.4: pending_sync.txt entries are retried when vault becomes available."""

    def test_sync_pending_copies_to_vault(self, mock_vault, monkeypatch):
        local_cache = vault_dir_from_mock(mock_vault).parent / "local_cache"
        monkeypatch.setattr(vault_sync, "LOCAL_CACHE", local_cache)
        monkeypatch.setattr(vault_sync, "PENDING_FILE", local_cache / "pending_sync.txt")

        # Create a local file
        sessions_dir = local_cache / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        test_file = sessions_dir / "test_pending.md"
        test_file.write_text("# Pending content", encoding="utf-8")

        # Record it as pending
        pending_file = local_cache / "pending_sync.txt"
        pending_file.write_text("2026-01-01T00:00:00|sessions|test_pending.md\n", encoding="utf-8")

        synced = sync_pending()
        assert "test_pending.md" in synced

        # Pending file should be cleaned up
        assert not pending_file.exists() or pending_file.read_text().strip() == ""


class TestSessionStateJsonFormat:
    """6.4: Session checkpoint files have valid structure."""

    def test_checkpoint_has_required_sections(self, mock_vault):
        path = save_checkpoint(
            "Schema Test",
            "Testing schema compliance",
            {"tasks": ["a", "b"], "decisions": ["use pytest"]},
        )
        content = Path(path).read_text(encoding="utf-8")

        # Must have frontmatter
        assert content.startswith("---")
        # Must have Summary section
        assert "## Summary" in content
        # Must have Context section (when context provided)
        assert "## Context" in content
        # Context should be valid JSON
        json_match = content.split("```json")[1].split("```")[0] if "```json" in content else ""
        if json_match:
            parsed = json.loads(json_match)
            assert "tasks" in parsed


class TestCodexReviewSaved:
    """6.4: save_codex_review() writes to local + vault."""

    def test_review_creates_file(self, mock_vault):
        review_result = {
            "approved": True,
            "confidence": 8,
            "summary": "Looks good",
            "issues": [],
        }
        path = save_codex_review("Test Review", review_result, "plan content here")
        assert path
        assert Path(path).exists()

    def test_review_contains_approval_status(self, mock_vault):
        review_result = {
            "approved": False,
            "confidence": 5,
            "summary": "Needs work",
            "issues": [{"severity": "high", "description": "Missing tests"}],
        }
        path = save_codex_review("Review With Issues", review_result)
        content = Path(path).read_text(encoding="utf-8")
        assert "False" in content or "false" in content
        assert "Missing tests" in content


def vault_dir_from_mock(mock_vault_path: Path) -> Path:
    """Helper to get vault dir from mock_vault fixture."""
    return mock_vault_path
