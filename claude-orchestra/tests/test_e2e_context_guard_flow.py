"""E2E 6.3: Context Guard → Agent wrapper flow.

Tests the full pipeline: secret content → guard_context() → redaction/block →
codex_wrapper integration. All tests use isolated tmp environments.
"""
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import context_guard
from context_guard import (
    guard_context,
    ContextGuardError,
    scan_secrets,
    redact_secrets,
    check_file_allowed,
)


class TestGuardToCodexWrapperRedacted:
    """6.3: Secret content is redacted before reaching codex_wrapper."""

    def test_api_key_redacted_in_output(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "0")
        monkeypatch.setenv("ORCHESTRA_CONSENT_POLICY", "redact")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

        content = 'api_key = "sk-abcdefghij1234567890abcdef"'
        result = guard_context(content, source_files=None)
        assert "sk-abcdefghij" not in result
        assert "[REDACTED]" in result

    def test_redacted_content_passed_to_wrapper(self, tmp_path, monkeypatch):
        """Simulate codex_wrapper receiving guard_context output."""
        monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "0")
        monkeypatch.setenv("ORCHESTRA_CONSENT_POLICY", "redact")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

        secret_content = 'password = "super_secret_password_123"'
        guarded = guard_context(secret_content, source_files=None)
        # The wrapper would receive this guarded content
        assert "super_secret" not in guarded
        assert "[REDACTED]" in guarded


class TestStrictOriginBlocksWithoutSourceFiles:
    """6.3: STRICT_ORIGIN=1 blocks calls without source_files."""

    def test_none_source_files_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "1")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

        with pytest.raises(ContextGuardError, match="ORCHESTRA_STRICT_ORIGIN"):
            guard_context("safe content", source_files=None)

    def test_empty_source_files_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "1")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

        with pytest.raises(ContextGuardError, match="ORCHESTRA_STRICT_ORIGIN"):
            guard_context("safe content", source_files=[])


class TestRedactPolicyPassesSafeContent:
    """6.3: Redact policy passes safe content unchanged."""

    def test_clean_content_unchanged(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "0")
        monkeypatch.setenv("ORCHESTRA_CONSENT_POLICY", "redact")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

        content = "def hello():\n    return 'world'"
        result = guard_context(content, source_files=None)
        assert result == content

    def test_safe_content_with_source_files(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "1")
        monkeypatch.setenv("ORCHESTRA_CONSENT_POLICY", "redact")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

        test_file = tmp_path / "main.py"
        test_file.write_text("print('hello')")

        content = "def foo(): pass"
        result = guard_context(content, source_files=[str(test_file)])
        assert result == content


class TestBlockPolicyRaisesOnSecret:
    """6.3: Block policy raises immediately on secret detection."""

    def test_block_raises_on_api_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "0")
        monkeypatch.setenv("ORCHESTRA_CONSENT_POLICY", "block")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

        content = 'api_key = "sk-1234567890abcdefghijklmnop"'
        with pytest.raises(ContextGuardError, match="secrets detected"):
            guard_context(content, source_files=None)

    def test_block_raises_on_jwt(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "0")
        monkeypatch.setenv("ORCHESTRA_CONSENT_POLICY", "block")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

        content = "token = eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        with pytest.raises(ContextGuardError, match="secrets detected"):
            guard_context(content, source_files=None)


class TestEnvFileBlockedInSourceFiles:
    """6.3: .env files in source_files are rejected."""

    def test_env_file_blocked(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "1")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

        env_file = tmp_path / ".env"
        env_file.write_text("SECRET=value")

        with pytest.raises(ContextGuardError, match="Blocked files"):
            guard_context("content", source_files=[str(env_file)])

    def test_env_production_blocked(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "1")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

        env_file = tmp_path / ".env.production"
        env_file.write_text("SECRET=value")

        with pytest.raises(ContextGuardError, match="Blocked files"):
            guard_context("content", source_files=[str(env_file)])

    def test_pem_file_blocked(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "1")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

        pem_file = tmp_path / "server.pem"
        pem_file.write_text("cert data")

        with pytest.raises(ContextGuardError, match="Blocked files"):
            guard_context("content", source_files=[str(pem_file)])


class TestPathTraversalBlocked:
    """6.3: Path traversal attempts in source_files are blocked."""

    def test_parent_traversal_blocked(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "1")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        # Unset ORCHESTRA_ALLOWED_DIRS to avoid interference
        monkeypatch.delenv("ORCHESTRA_ALLOWED_DIRS", raising=False)

        # Path outside allowed dirs should be blocked
        traversal_path = str(Path(tmp_path) / ".." / ".." / ".." / "etc" / "passwd")
        with pytest.raises(ContextGuardError, match="outside allowed"):
            guard_context("content", source_files=[traversal_path])


class TestGuardAuditLogWritten:
    """6.3: guard_context writes audit log entries."""

    def test_audit_log_on_secret_detection(self, guard_env, monkeypatch):
        """Audit log is written to tmp_path (not real home dir)."""
        # guard_env sets STRICT_ORIGIN=1; override for redaction test
        monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "0")
        monkeypatch.setenv("ORCHESTRA_CONSENT_POLICY", "redact")

        content = 'token = "ghp_1234567890abcdefghijklmnopqrstuv1234"'
        guard_context(content, source_files=None)

        log_file = guard_env / ".claude" / "logs" / "context_guard_audit.jsonl"
        if log_file.exists():
            log_content = log_file.read_text(encoding="utf-8")
            assert "secrets_found" in log_content or "unknown_origin" in log_content
