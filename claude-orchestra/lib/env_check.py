"""
Environment prerequisites validation.

Checks CLI tools, model availability, and runtime requirements
before Orchestra operations. Provides graceful degradation info.
"""
import shutil
import subprocess
import json
from pathlib import Path


def check_node() -> dict:
    """Check Node.js availability."""
    path = shutil.which("node")
    if not path:
        return {"available": False, "error": "Node.js not found"}
    try:
        r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5, shell=False)
        # v19 L-4: Verify returncode before reporting available
        if r.returncode != 0:
            return {"available": False, "path": path, "error": f"exit code {r.returncode}: {r.stderr.strip()[:200]}"}
        return {"available": True, "path": path, "version": r.stdout.strip()}
    except Exception as e:
        return {"available": False, "error": str(e)}


def check_codex() -> dict:
    """Check Codex CLI availability."""
    try:
        from cli_finder import find_codex_js, find_node  # v13 C-5: no circular import
        node = find_node()
        codex_js = find_codex_js()
        r = subprocess.run(
            [node, codex_js, "--version"],
            capture_output=True, text=True, timeout=10, shell=False
        )
        # v19 L-4: Verify returncode
        if r.returncode != 0:
            return {"available": False, "path": codex_js, "error": f"exit code {r.returncode}: {r.stderr.strip()[:200]}"}
        return {"available": True, "path": codex_js, "version": r.stdout.strip()}
    except FileNotFoundError as e:
        return {"available": False, "error": str(e)}
    except Exception as e:
        return {"available": False, "error": str(e)}


def check_gemini() -> dict:
    """Check Gemini CLI availability."""
    path = shutil.which("gemini")
    if not path:
        return {"available": False, "error": "Gemini CLI not found", "degradation": "Research tasks handled by Claude Code WebSearch"}
    try:
        r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5, shell=False)
        # v19 L-4: Verify returncode
        if r.returncode != 0:
            return {"available": False, "path": path, "error": f"exit code {r.returncode}: {r.stderr.strip()[:200]}"}
        return {"available": True, "path": path, "version": r.stdout.strip()}
    except Exception as e:
        return {"available": False, "error": str(e)}


def check_python_tools() -> dict:
    """Check optional Python tools (ruff, ty, uv)."""
    tools = {}
    for tool in ["ruff", "ty", "uv"]:
        path = shutil.which(tool)
        if path:
            try:
                r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5, shell=False)
                tools[tool] = {"available": True, "path": path, "version": r.stdout.strip()}
            except Exception:
                tools[tool] = {"available": True, "path": path, "version": "unknown"}
        else:
            tools[tool] = {"available": False}
    return tools


def check_vault() -> dict:
    """Check TetsuyaSynapse vault accessibility."""
    import os
    vault_root = Path(os.environ.get("VAULT_PATH", "G:/My Drive/obsidian/TetsuyaSynapse"))
    if vault_root.exists():
        return {"available": True, "path": str(vault_root)}
    return {"available": False, "path": str(vault_root), "degradation": "Local cache at ~/.claude/obsidian-sessions/"}


def full_check() -> dict:
    """
    Run all environment checks and return capability matrix.

    Returns:
        {
            "node": {...},
            "codex": {...},
            "gemini": {...},
            "python_tools": {...},
            "vault": {...},
            "capabilities": {
                "codex_delegation": bool,
                "gemini_delegation": bool,
                "lint_on_save": bool,
                "vault_sync": bool,
            }
        }
    """
    node = check_node()
    codex = check_codex()
    gemini = check_gemini()
    python_tools = check_python_tools()
    vault = check_vault()

    capabilities = {
        "codex_delegation": node.get("available", False) and codex.get("available", False),
        "gemini_delegation": gemini.get("available", False),
        "lint_on_save": python_tools.get("ruff", {}).get("available", False),
        "vault_sync": vault.get("available", False),
    }

    return {
        "node": node,
        "codex": codex,
        "gemini": gemini,
        "python_tools": python_tools,
        "vault": vault,
        "capabilities": capabilities,
    }


def save_env_report(output_path: Path = None) -> str:
    """Run full check and save to JSON file."""
    if output_path is None:
        output_path = Path.home() / ".claude" / "lib" / "env_report.json"
    report = full_check()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(output_path)
