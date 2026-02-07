"""
Common bootstrap for all hooks/scripts.

Sets up:
1. sys.path to include lib directory
2. CLAUDE_PROJECT_DIR environment variable (for context_guard allowlist)

Usage (2 lines at top of each hook/script):
    import sys; sys.path.insert(0, str(__import__('pathlib').Path.home() / ".claude" / "lib"))
    import bootstrap  # noqa: F401
"""
import json
import os
import subprocess
import sys
from pathlib import Path

# Step 1: Add lib directory to path
_lib_dir = str(Path(__file__).parent)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from path_utils import normalize_path  # v19 L-1: normalize Git Bash paths


# Step 2: Set CLAUDE_PROJECT_DIR if not already set
def _detect_project_dir() -> str | None:
    """Auto-detect project directory from git root or cwd."""
    # Try git root
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5, shell=False
        )
        if result.returncode == 0 and result.stdout.strip():
            # v19 L-1: Normalize MSYS2/Git Bash path to Windows path
            return normalize_path(result.stdout.strip())
    except Exception:
        pass
    # Fall back to cwd
    return str(Path.cwd())


def _load_settings_project_dir() -> str | None:
    """Try to read project dir from settings.json."""
    settings_path = Path.home() / ".claude" / "settings.json"
    try:
        if settings_path.exists():
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            raw = data.get("projectDir") or data.get("project_dir")
            # v19 L-1: Normalize path from settings
            return normalize_path(raw) if raw else None
    except Exception:
        pass
    return None


if not os.environ.get("CLAUDE_PROJECT_DIR"):
    project_dir = _load_settings_project_dir() or _detect_project_dir()
    if project_dir:
        os.environ["CLAUDE_PROJECT_DIR"] = project_dir
