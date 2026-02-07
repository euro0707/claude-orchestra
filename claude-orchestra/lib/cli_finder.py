"""
Side-effect-free CLI path resolution utilities.

v13 C-5: Extracted from codex_wrapper to avoid circular imports.
Used by both codex_wrapper and env_check.
"""
import os
import shutil
import subprocess
from pathlib import Path


def find_node() -> str:
    """Find Node.js executable path."""
    path = shutil.which("node")
    if path:
        return path
    # Windows common locations
    for candidate in [
        Path(os.environ.get("PROGRAMFILES", "")) / "nodejs" / "node.exe",
        Path.home() / "AppData" / "Roaming" / "nvm" / "current" / "node.exe",
    ]:
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError("Node.js not found. Install from https://nodejs.org/")


def find_codex_js() -> str:
    """Find Codex CLI entry point (codex.js)."""
    # Check env override
    env_path = os.environ.get("CODEX_JS")
    if env_path and Path(env_path).exists():
        return env_path

    # npm global
    codex_js = (
        Path.home() / "AppData" / "Roaming" / "npm" / "node_modules"
        / "@openai" / "codex" / "bin" / "codex.js"
    )
    if codex_js.exists():
        return str(codex_js)

    # Try npm root -g
    try:
        r = subprocess.run(
            ["npm", "root", "-g"], capture_output=True, text=True, timeout=10, shell=False
        )
        # v19 L-2: Require returncode == 0 and non-empty stdout
        if r.returncode == 0 and r.stdout.strip():
            npm_global = Path(r.stdout.strip()) / "@openai" / "codex" / "bin" / "codex.js"
            if npm_global.exists():
                return str(npm_global)
    except Exception:
        pass

    raise FileNotFoundError(
        "Codex CLI not found. Install with: npm install -g @openai/codex"
    )
