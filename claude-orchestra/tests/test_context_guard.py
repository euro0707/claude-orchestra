"""Test 5.4: context_guard module - secret scanning, redaction, guard pipeline."""
import os
from unittest.mock import patch

import pytest

import context_guard
from context_guard import (
    ContextGuardError,
    scan_secrets,
    redact_secrets,
    check_file_allowed,
    enforce_allowed_dirs,
    guard_context,
    MAX_CONTEXT_SIZE,
)


class TestScanSecrets:
    def test_generic_api_key(self):
        content = 'api_key = "abcdefghijklmnopqrstuvwxyz1234"'
        findings = scan_secrets(content)
        assert len(findings) >= 1

    def test_aws_access_key(self):
        content = "AKIAIOSFODNN7EXAMPLE1"
        findings = scan_secrets(content)
        assert len(findings) >= 1

    def test_aws_secret_key(self):
        content = 'aws_secret_access_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY123"'
        findings = scan_secrets(content)
        assert len(findings) >= 1

    def test_github_token(self):
        content = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnop"
        findings = scan_secrets(content)
        assert len(findings) >= 1

    def test_gitlab_token(self):
        content = "glpat-ABCDEFGHIJKLMNOPQRSTu"
        findings = scan_secrets(content)
        assert len(findings) >= 1

    def test_private_key(self):
        # H-1: Full BEGIN...END block required (DOTALL regex)
        content = "-----BEGIN RSA PRIVATE KEY-----\nMIIE...base64...\n-----END RSA PRIVATE KEY-----"
        findings = scan_secrets(content)
        assert len(findings) >= 1

    def test_generic_password(self):
        content = 'password = "supersecretvalue"'
        findings = scan_secrets(content)
        assert len(findings) >= 1

    def test_jwt_token(self):
        content = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature123"
        findings = scan_secrets(content)
        assert len(findings) >= 1

    def test_connection_string(self):
        content = "postgres://admin:secretpass@localhost:5432/mydb"
        findings = scan_secrets(content)
        assert len(findings) >= 1

    def test_env_var_pattern(self):
        content = "DATABASE_URL=postgresql://host/db?password=12345678"
        findings = scan_secrets(content)
        assert len(findings) >= 1

    def test_safe_content_no_findings(self):
        content = "def hello():\n    return 'world'"
        findings = scan_secrets(content)
        assert len(findings) == 0

    def test_match_truncated_for_safety(self):
        content = 'api_key = "abcdefghijklmnopqrstuvwxyz1234"'
        findings = scan_secrets(content)
        for f in findings:
            assert f["match"].endswith("***")
            assert len(f["match"]) <= 11  # 8 chars + "***"

    def test_line_number_reported(self):
        content = "line1\nline2\napi_key = abcdefghijklmnopqrstuvwxyz1234"
        findings = scan_secrets(content)
        assert findings[0]["line"] == 3


class TestRedactSecrets:
    def test_replaces_api_key(self):
        content = 'api_key = "abcdefghijklmnopqrstuvwxyz1234"'
        redacted = redact_secrets(content)
        assert "[REDACTED]" in redacted
        assert "abcdefghijklmnopqrstuvwxyz1234" not in redacted

    def test_safe_content_unchanged(self):
        content = "def hello():\n    return 42"
        assert redact_secrets(content) == content


class TestCheckFileAllowed:
    def test_env_blocked(self):
        assert check_file_allowed(".env") is False

    def test_env_production_blocked(self):
        assert check_file_allowed(".env.production") is False

    def test_pem_blocked(self):
        assert check_file_allowed("server.pem") is False

    def test_key_blocked(self):
        assert check_file_allowed("private.key") is False

    def test_credentials_json_blocked(self):
        assert check_file_allowed("credentials.json") is False

    def test_serviceaccount_blocked(self):
        assert check_file_allowed("serviceaccount-prod.json") is False

    def test_rsa_key_blocked(self):
        assert check_file_allowed("deploy_rsa") is False

    def test_ed25519_blocked(self):
        assert check_file_allowed("id_ed25519") is False

    def test_python_allowed(self):
        assert check_file_allowed("main.py") is True

    def test_markdown_allowed(self):
        assert check_file_allowed("README.md") is True


class TestEnforceAllowedDirs:
    def test_files_in_project_dir_allowed(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        test_file = tmp_path / "src" / "main.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.touch()
        violations = enforce_allowed_dirs([str(test_file)])
        assert len(violations) == 0

    def test_files_outside_project_blocked(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        monkeypatch.delenv("ORCHESTRA_ALLOWED_DIRS", raising=False)
        violations = enforce_allowed_dirs(["C:\\totally\\other\\path.py"])
        assert len(violations) >= 1


class TestGuardContext:
    def test_safe_content_passes(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "0")
        result = guard_context("safe code here")
        assert result == "safe code here"

    def test_size_limit_truncates(self, monkeypatch):
        monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "0")
        big_content = "x" * (MAX_CONTEXT_SIZE + 1000)
        result = guard_context(big_content)
        assert "[TRUNCATED" in result
        assert len(result) < len(big_content)

    def test_secrets_redacted_under_redact_policy(self, monkeypatch):
        monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "0")
        monkeypatch.setenv("ORCHESTRA_CONSENT_POLICY", "redact")
        content = 'token = "mysupersecrettoken123"'
        result = guard_context(content)
        assert "[REDACTED]" in result

    def test_secrets_blocked_under_block_policy(self, monkeypatch):
        monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "0")
        monkeypatch.setenv("ORCHESTRA_CONSENT_POLICY", "block")
        content = 'token = "mysupersecrettoken123"'
        with pytest.raises(ContextGuardError, match="secrets detected"):
            guard_context(content)

    def test_strict_origin_blocks_no_source_files(self, monkeypatch):
        monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "1")
        with pytest.raises(ContextGuardError, match="ORCHESTRA_STRICT_ORIGIN"):
            guard_context("some content")

    def test_strict_origin_blocks_empty_source_files(self, monkeypatch):
        monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "1")
        with pytest.raises(ContextGuardError, match="ORCHESTRA_STRICT_ORIGIN"):
            guard_context("some content", source_files=[])

    def test_require_allowlist_blocks_no_source(self, monkeypatch):
        monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "0")
        monkeypatch.setenv("ORCHESTRA_CONSENT_POLICY", "require_allowlist")
        with pytest.raises(ContextGuardError, match="source_files is required"):
            guard_context("content")

    def test_blocked_file_extension(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "0")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        env_file = tmp_path / ".env"
        env_file.touch()
        with pytest.raises(ContextGuardError, match="Blocked files"):
            guard_context("content", source_files=[str(env_file)])

    def test_source_files_outside_allowed_dirs(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "0")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        monkeypatch.delenv("ORCHESTRA_ALLOWED_DIRS", raising=False)
        with pytest.raises(ContextGuardError, match="outside allowed"):
            guard_context("content", source_files=["C:\\totally\\other\\file.py"])

    def test_valid_source_files_pass(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "0")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        test_file = tmp_path / "src" / "main.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.touch()
        result = guard_context("safe code", source_files=[str(test_file)])
        assert result == "safe code"


class TestAllowedDirsParsing:
    """P5-5: Tests for ORCHESTRA_ALLOWED_DIRS comma-separated parsing."""

    def test_single_extra_dir(self, tmp_path, monkeypatch):
        extra_dir = tmp_path / "extra"
        extra_dir.mkdir()
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "project"))
        monkeypatch.setenv("ORCHESTRA_ALLOWED_DIRS", str(extra_dir))
        test_file = extra_dir / "file.py"
        test_file.touch()
        violations = enforce_allowed_dirs([str(test_file)])
        assert len(violations) == 0

    def test_multiple_extra_dirs(self, tmp_path, monkeypatch):
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "project"))
        monkeypatch.setenv("ORCHESTRA_ALLOWED_DIRS", f"{dir1},{dir2}")
        file1 = dir1 / "a.py"
        file2 = dir2 / "b.py"
        file1.touch()
        file2.touch()
        violations = enforce_allowed_dirs([str(file1), str(file2)])
        assert len(violations) == 0

    def test_extra_dirs_with_whitespace(self, tmp_path, monkeypatch):
        dir1 = tmp_path / "dir1"
        dir1.mkdir()
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "project"))
        monkeypatch.setenv("ORCHESTRA_ALLOWED_DIRS", f"  {dir1}  ,  ")
        file1 = dir1 / "file.py"
        file1.touch()
        violations = enforce_allowed_dirs([str(file1)])
        assert len(violations) == 0

    def test_empty_allowed_dirs_ignored(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        monkeypatch.setenv("ORCHESTRA_ALLOWED_DIRS", "")
        # File in project dir should still pass
        test_file = tmp_path / "file.py"
        test_file.touch()
        violations = enforce_allowed_dirs([str(test_file)])
        assert len(violations) == 0


class TestInvalidConsentPolicy:
    """P5-5: Tests for invalid ORCHESTRA_CONSENT_POLICY fallback."""

    def test_invalid_policy_defaults_to_redact(self, monkeypatch):
        monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "0")
        monkeypatch.setenv("ORCHESTRA_CONSENT_POLICY", "typo_invalid")
        # Should default to "redact" — secrets redacted, not blocked
        content = 'token = "mysupersecrettoken123"'
        result = guard_context(content)
        assert "[REDACTED]" in result

    def test_empty_policy_defaults_to_redact(self, monkeypatch):
        monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "0")
        monkeypatch.setenv("ORCHESTRA_CONSENT_POLICY", "")
        # Empty string is not in _VALID_POLICIES, should default to "redact"
        content = 'token = "mysupersecrettoken123"'
        result = guard_context(content)
        assert "[REDACTED]" in result


class TestPathTraversal:
    """P5-5: Tests for path traversal attempts in enforce_allowed_dirs."""

    def test_dotdot_traversal_blocked(self, tmp_path, monkeypatch):
        project = tmp_path / "project"
        project.mkdir()
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
        monkeypatch.delenv("ORCHESTRA_ALLOWED_DIRS", raising=False)
        # Try to escape project dir with ..
        traversal = str(project / ".." / "secret" / "data.txt")
        violations = enforce_allowed_dirs([traversal])
        # After resolve(), path should be outside project dir
        assert len(violations) >= 1

    def test_env_multi_suffix_blocked(self):
        """P4-1 regression: .env.production.local should be blocked."""
        assert check_file_allowed(".env.production.local") is False
        assert check_file_allowed(".env.staging") is False
        assert check_file_allowed(".env.development.local") is False
