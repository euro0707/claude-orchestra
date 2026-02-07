"""Shared test configuration and fixtures for Orchestra lib tests."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

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
