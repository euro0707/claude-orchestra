"""Shared test configuration and fixtures for Orchestra lib tests."""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


def pytest_collection_modifyitems(config, items):
    """Auto-skip E2E tests unless ORCHESTRA_E2E=1 is set."""
    if os.environ.get("ORCHESTRA_E2E") == "1":
        return
    skip_e2e = pytest.mark.skip(reason="Set ORCHESTRA_E2E=1 to run E2E tests")
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip_e2e)

# Add repo lib directory to sys.path for imports (NOT ~/.claude/lib)
_LIB_DIR = str(Path(__file__).resolve().parent.parent / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)


@pytest.fixture(autouse=True)
def isolate_env(tmp_path, monkeypatch):
    """Isolate environment variables and file paths for each test."""
    # Prevent bootstrap side effects
    monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "0")
    monkeypatch.setenv("ORCHESTRA_CONSENT_POLICY", "redact")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    # Use tmp_path for budget file to avoid touching real state
    monkeypatch.setenv("ORCHESTRA_TOKEN_BUDGET", "500000")
    monkeypatch.setenv("ORCHESTRA_MAX_CONCURRENT", "2")
    # Redirect _audit_log to tmp_path so no test writes to real Path.home()
    import context_guard
    log_dir = tmp_path / ".claude" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(context_guard, "_audit_log", _write_audit_log(log_dir))


@pytest.fixture
def mock_budget_file(tmp_path, monkeypatch):
    """Redirect budget state file to tmp_path and fix module-level defaults."""
    import budget
    budget_file = tmp_path / "budget_session.json"
    monkeypatch.setattr(budget, "_BUDGET_FILE", budget_file)
    # P5-3: Override module-level constants that were read at import time
    monkeypatch.setattr(budget, "DEFAULT_TOKEN_BUDGET", 500000)
    monkeypatch.setattr(budget, "DEFAULT_MAX_CONCURRENT", 2)
    budget_file.parent.mkdir(parents=True, exist_ok=True)
    return budget_file


# --- E2E Fixtures ---


@pytest.fixture
def session_dir(tmp_path):
    """Create a tmp directory with notes/, .claude/hooks/, .claude/logs/ structure."""
    (tmp_path / "notes").mkdir()
    (tmp_path / ".claude" / "hooks").mkdir(parents=True)
    (tmp_path / ".claude" / "logs").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def vault_dir(tmp_path):
    """Create a fake Obsidian vault directory under tmp_path."""
    vault = tmp_path / "vault" / "TetsuyaSynapse"
    (vault / "90-Claude" / "sessions").mkdir(parents=True)
    (vault / "90-Claude" / "decisions").mkdir(parents=True)
    (vault / "90-Claude" / "learnings").mkdir(parents=True)
    return vault


@pytest.fixture
def mock_vault(vault_dir, monkeypatch):
    """Redirect vault_sync paths to tmp vault_dir."""
    import vault_sync
    monkeypatch.setattr(vault_sync, "VAULT_ROOT", vault_dir)
    monkeypatch.setattr(vault_sync, "VAULT_BASE", vault_dir / "90-Claude")
    local_cache = vault_dir.parent / "local_cache"
    local_cache.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(vault_sync, "LOCAL_CACHE", local_cache)
    monkeypatch.setattr(vault_sync, "PENDING_FILE", local_cache / "pending_sync.txt")
    return vault_dir


def _write_audit_log(log_dir: Path):
    """Create a safe audit log writer that properly closes file handles."""
    def _writer(event, details):
        log_file = log_dir / "context_guard_audit.jsonl"
        with log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"event": event, "details": details}) + "\n")
    return _writer


@pytest.fixture
def guard_env(tmp_path, monkeypatch):
    """Set up context_guard environment for E2E tests."""
    monkeypatch.setenv("ORCHESTRA_STRICT_ORIGIN", "1")
    monkeypatch.setenv("ORCHESTRA_CONSENT_POLICY", "redact")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    log_dir = tmp_path / ".claude" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    import context_guard
    monkeypatch.setattr(context_guard, "_audit_log", _write_audit_log(log_dir))
    return tmp_path
