---
type: implementation
version: 18
timestamp: 2026-02-06
purpose: Complete hook scripts and settings.json for Claude Code Orchestra
encoding: utf-8
base: plan-v10.md
---

# Claude Code Orchestra Hooks - Complete Implementation (v18)

## Overview

This document provides complete, production-ready hook scripts for the Claude Code Orchestra integration. All scripts follow the patterns established in plan-v10.md.

## Environment

- OS: Windows 11
- Python: 3.13 (absolute path: `C:\Users\skyeu\AppData\Local\Programs\Python\Python313\python.exe`)
- Claude Code hooks directory: `C:\Users\skyeu\.claude\hooks\`
- Shared library: `C:\Users\skyeu\.claude\lib\`
- Codex CLI: via node.js direct execution (see plan-v10.md)
- Gemini CLI: optional, graceful skip if not installed

## Import Template (2-line bootstrap)

All hooks start with this exact 2-line template:

```python
import sys; sys.path.insert(0, str(__import__('pathlib').Path.home() / ".claude" / "lib"))
import bootstrap  # noqa: F401
```

After these lines, imports from the shared library work:
```python
from codex_wrapper import call_codex
from gemini_wrapper import call_gemini
from vault_sync import save_codex_review
```

---

## Hook Scripts (10 files)

### 1. agent-router.py (UserPromptSubmit)

**Purpose**: Route prompts to appropriate agent, validate skill prefixes

**Hook event**: UserPromptSubmit

**Triggers**:
- Dynamic skill validation (scans ~/.claude/skills/)
- Delegation suggestions for "codex", "review", "verify" keywords
- Gemini suggestions for "research", "investigate" keywords
- Early return for short prompts (<20 chars)

```python
#!/usr/bin/env python3
"""
Agent router hook for Claude Code.

Analyzes user prompts and suggests appropriate delegation:
- Codex for reviews, verification, architecture analysis
- Gemini for research, investigation tasks
- Validates sc: skill prefix usage

Hook event: UserPromptSubmit
"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path.home() / ".claude" / "lib"))
import bootstrap  # noqa: F401

import json
from pathlib import Path


def validate_skill_prefix(user_input: str) -> str | None:
    """
    Validate skill namespace. Dynamically scans ~/.claude/skills/ directory.
    Returns suggestion message if invalid prefix detected, None otherwise.
    """
    skills_dir = Path.home() / ".claude" / "skills"
    if not skills_dir.exists():
        return None

    # Dynamically discover skill names from directory listing
    skill_names = {d.name for d in skills_dir.iterdir() if d.is_dir()}

    if user_input.startswith("/") and not user_input.startswith("/sc:"):
        cmd_name = user_input[1:].split()[0]
        if cmd_name in skill_names:
            return f"Suggestion: use /sc:{cmd_name} (from skills/ directory)"
    return None


def suggest_delegation(prompt: str) -> str | None:
    """
    Analyze prompt and suggest delegation to Codex or Gemini if appropriate.
    Returns suggestion message or None.
    """
    # Early return for short prompts to avoid overhead
    if len(prompt) < 20:
        return None

    prompt_lower = prompt.lower()

    # Codex delegation triggers
    codex_keywords = ["codex", "review", "verify", "check", "architecture", "design review"]
    if any(kw in prompt_lower for kw in codex_keywords):
        return "Suggestion: Consider delegating to Codex for technical review (use /sc:codex-system)"

    # Gemini delegation triggers (only if Gemini CLI available)
    research_keywords = ["research", "investigate", "analyze", "compare", "benchmark"]
    if any(kw in prompt_lower for kw in research_keywords):
        try:
            import shutil
            if shutil.which("gemini"):
                return "Suggestion: Consider using Gemini for research tasks (use /sc:gemini-system)"
        except Exception:
            pass

    return None


def main():
    try:
        # Read hook event data from stdin
        stdin_data = sys.stdin.read()
        if not stdin_data:
            # No input, pass through
            print(json.dumps({}))
            return

        event_data = json.loads(stdin_data)
        user_prompt = event_data.get("prompt", "")

        suggestions = []

        # Validate skill prefix
        skill_suggestion = validate_skill_prefix(user_prompt)
        if skill_suggestion:
            suggestions.append(skill_suggestion)

        # Suggest delegation
        delegation_suggestion = suggest_delegation(user_prompt)
        if delegation_suggestion:
            suggestions.append(delegation_suggestion)

        # Return suggestions
        if suggestions:
            print(json.dumps({"message": "\n".join(suggestions)}))
        else:
            print(json.dumps({}))

    except Exception as e:
        # Fail gracefully, don't block prompt submission
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
```

---

### 2. check-codex-before-write.py (PreToolUse Write|Edit)

**Purpose**: Suggest Codex review before large file modifications

**Hook event**: PreToolUse (Write|Edit)

**Triggers**:
- File is Python (.py)
- Change looks large (heuristic: >100 lines or significant structural change)
- Codex CLI is available

```python
#!/usr/bin/env python3
"""
Pre-write hook: Suggest Codex review before large modifications.

Hook event: PreToolUse (Write|Edit)
"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path.home() / ".claude" / "lib"))
import bootstrap  # noqa: F401

import json
import shutil
from pathlib import Path


def should_suggest_review(file_path: str, content: str = "") -> bool:
    """
    Heuristic: suggest review for large Python files.
    Returns True if Codex review is recommended.
    """
    path = Path(file_path)

    # Only suggest for Python files
    if path.suffix != ".py":
        return False

    # Check if Codex is available
    try:
        from codex_wrapper import find_codex_js, find_node
        find_node()
        find_codex_js()
    except Exception:
        return False  # Codex not available

    # Heuristic: suggest for large changes (>100 lines)
    if content and len(content.splitlines()) > 100:
        return True

    # Heuristic: suggest for files with "class" or "def" (structural changes)
    if content and ("class " in content or "def " in content):
        return True

    return False


def main():
    try:
        stdin_data = sys.stdin.read()
        if not stdin_data:
            print(json.dumps({}))
            return

        event_data = json.loads(stdin_data)
        tool_name = event_data.get("tool_name", "")
        file_path = event_data.get("file_path", "")
        content = event_data.get("content", "")

        if tool_name in ("Write", "Edit") and file_path:
            if should_suggest_review(file_path, content):
                msg = f"Suggestion: Consider Codex review before modifying {Path(file_path).name} (use /sc:codex-system)"
                print(json.dumps({"message": msg}))
            else:
                print(json.dumps({}))
        else:
            print(json.dumps({}))

    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
```

---

### 3. check-codex-after-plan.py (PostToolUse Task)

**Purpose**: Suggest Codex review after task planning completes

**Hook event**: PostToolUse (Task)

**Triggers**:
- Task result looks like a plan (contains "plan", "step", "phase" keywords)
- Codex CLI is available

```python
#!/usr/bin/env python3
"""
Post-task hook: Suggest Codex review after planning.

Hook event: PostToolUse (Task)
"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path.home() / ".claude" / "lib"))
import bootstrap  # noqa: F401

import json
import shutil


def is_plan(task_result: str) -> bool:
    """
    Heuristic: detect if task result is a plan.
    Returns True if result contains planning keywords.
    """
    if not task_result:
        return False

    result_lower = task_result.lower()
    plan_keywords = ["plan", "step", "phase", "milestone", "roadmap", "architecture"]

    return any(kw in result_lower for kw in plan_keywords)


def codex_available() -> bool:
    """Check if Codex CLI is available."""
    try:
        from codex_wrapper import find_codex_js, find_node
        find_node()
        find_codex_js()
        return True
    except Exception:
        return False


def main():
    try:
        stdin_data = sys.stdin.read()
        if not stdin_data:
            print(json.dumps({}))
            return

        event_data = json.loads(stdin_data)
        tool_name = event_data.get("tool_name", "")
        result = event_data.get("result", "")

        if tool_name == "Task" and is_plan(result) and codex_available():
            msg = "Suggestion: Plan detected. Consider Codex verification (use /sc:codex-system verify)"
            print(json.dumps({"message": msg}))
        else:
            print(json.dumps({}))

    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
```

---

### 4. lint-on-save.py (called by post-write-orchestrator)

**Purpose**: Auto-lint Python files with ruff on save

**Called by**: post-write-orchestrator.py

**Actions**:
- If file is .py and ruff is available, run `ruff check --fix`
- Returns lint results as JSON

```python
#!/usr/bin/env python3
"""
Lint-on-save hook: Auto-lint Python files with ruff.

Called by: post-write-orchestrator.py
"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path.home() / ".claude" / "lib"))
import bootstrap  # noqa: F401

import json
import shutil
import subprocess
from pathlib import Path


def lint_file(file_path: str) -> dict:
    """
    Lint a Python file with ruff.
    Returns dict with lint results.
    """
    path = Path(file_path)

    # Only lint Python files
    if path.suffix != ".py":
        return {"skipped": True, "reason": "not a Python file"}

    # Check if ruff is available
    ruff_path = shutil.which("ruff")
    if not ruff_path:
        return {"skipped": True, "reason": "ruff not installed"}

    try:
        # Run ruff check --fix
        result = subprocess.run(
            [ruff_path, "check", "--fix", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            shell=False,
        )

        # v19 H-5: Notify user when --fix applies changes
        fixed = result.returncode == 0 and result.stdout.strip()
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[:500],  # Truncate long output
            "stderr": result.stderr[:500],
            "message": f"ruff auto-fixed issues in {Path(file_path).name}" if fixed else None,
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "timeout"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def main():
    try:
        stdin_data = sys.stdin.read()
        if not stdin_data:
            print(json.dumps({"skipped": True, "reason": "no input"}))
            return

        event_data = json.loads(stdin_data)
        file_path = event_data.get("file_path", "")

        if file_path:
            result = lint_file(file_path)
            print(json.dumps(result))
        else:
            print(json.dumps({"skipped": True, "reason": "no file_path"}))

    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
```

---

### 5. log-cli-tools.py (called by post-bash-orchestrator)

**Purpose**: Log Codex/Gemini CLI invocations to JSONL (never log secrets)

**Called by**: post-bash-orchestrator.py

**Actions**:
- If command involves codex or gemini CLI, log to `~/.claude/logs/cli_tools.jsonl`
- Never log environment variables or secrets

```python
#!/usr/bin/env python3
"""
CLI tool logger: Log Codex/Gemini CLI invocations.

Called by: post-bash-orchestrator.py
Security: Never logs env vars or secrets.
"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path.home() / ".claude" / "lib"))
import bootstrap  # noqa: F401

import json
from datetime import datetime
from pathlib import Path


LOG_DIR = Path.home() / ".claude" / "logs"
LOG_FILE = LOG_DIR / "cli_tools.jsonl"


def should_log_command(command: str) -> bool:
    """Check if command involves Codex or Gemini CLI."""
    if not command:
        return False

    cmd_lower = command.lower()
    return "codex" in cmd_lower or "gemini" in cmd_lower


def sanitize_command(command: str) -> str:
    """
    Remove potential secrets from command.

    v19 H-1: Comprehensive redaction strategy:
    1. Strip env var assignments (VAR=value, both upper and lower case)
    2. Redact values after sensitive flags (--api-key, --token, etc.)
    3. Redact token-like strings (long alphanumeric sequences)
    """
    import re
    # Step 1: Remove env var assignments (upper and lowercase)
    sanitized = re.sub(r'\b[A-Za-z_]+=[^\s]+', '[ENV_VAR]', command)
    # Step 2: Redact values after sensitive flags
    sensitive_flags = r'(?:--?(?:api[_-]?key|token|password|passwd|secret|auth|credentials|key))'
    sanitized = re.sub(
        sensitive_flags + r'[\s=]+[^\s]+',
        lambda m: m.group().split()[0] + ' [REDACTED]' if ' ' in m.group()
        else m.group().split('=')[0] + '=[REDACTED]',
        sanitized, flags=re.IGNORECASE
    )
    # Step 3: Redact token-like strings (32+ char alphanumeric, likely API keys)
    sanitized = re.sub(r'\b[A-Za-z0-9_\-]{32,}\b', '[TOKEN_REDACTED]', sanitized)
    return sanitized


def log_cli_call(command: str, exit_code: int = 0) -> None:
    """Log CLI tool invocation to JSONL."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        entry = {
            "timestamp": datetime.now().isoformat(),
            "command": sanitize_command(command),
            "exit_code": exit_code,
            "type": "codex" if "codex" in command.lower() else "gemini",
        }

        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    except Exception:
        pass  # Best-effort logging, never block


def main():
    try:
        stdin_data = sys.stdin.read()
        if not stdin_data:
            print(json.dumps({}))
            return

        event_data = json.loads(stdin_data)
        command = event_data.get("command", "")
        exit_code = event_data.get("exit_code", 0)

        if should_log_command(command):
            log_cli_call(command, exit_code)
            print(json.dumps({"logged": True}))
        else:
            print(json.dumps({"logged": False, "reason": "not a CLI tool command"}))

    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
```

---

### 6. post-implementation-review.py (called by post-write-orchestrator)

**Purpose**: Suggest Codex review after significant implementation changes

**Called by**: post-write-orchestrator.py

**Triggers**:
- Tracks files modified in session
- If 3+ files modified OR 100+ total lines changed, suggest Codex review

```python
#!/usr/bin/env python3
"""
Post-implementation review hook: Track changes and suggest Codex review.

Called by: post-write-orchestrator.py
"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path.home() / ".claude" / "lib"))
import bootstrap  # noqa: F401

import json
from pathlib import Path


# Session state file (tracks files modified in current session)
STATE_FILE = Path.home() / ".claude" / "logs" / "session_state.json"


def load_session_state() -> dict:
    """Load session state from disk."""
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"files_modified": [], "total_lines_changed": 0}


def save_session_state(state: dict) -> None:
    """Save session state to disk."""
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
    except Exception:
        pass


def update_state(file_path: str, lines_changed: int) -> dict:
    """Update session state with new file modification."""
    state = load_session_state()

    if file_path not in state["files_modified"]:
        state["files_modified"].append(file_path)

    state["total_lines_changed"] += lines_changed

    save_session_state(state)
    return state


def should_suggest_review(state: dict) -> bool:
    """
    Check if Codex review should be suggested.
    Criteria: 3+ files modified OR 100+ total lines changed.
    """
    if len(state["files_modified"]) >= 3:
        return True
    if state["total_lines_changed"] >= 100:
        return True
    return False


def codex_available() -> bool:
    """Check if Codex CLI is available."""
    try:
        from codex_wrapper import find_codex_js, find_node
        find_node()
        find_codex_js()
        return True
    except Exception:
        return False


def main():
    try:
        stdin_data = sys.stdin.read()
        if not stdin_data:
            print(json.dumps({}))
            return

        event_data = json.loads(stdin_data)
        file_path = event_data.get("file_path", "")
        content = event_data.get("content", "")

        # v19 H-3: Guard against empty/missing file_path
        if not file_path:
            print(json.dumps({"skipped": True, "reason": "no file_path"}))
            return

        # Estimate lines changed (rough heuristic)
        lines_changed = len(content.splitlines()) if content else 0

        # Update session state
        state = update_state(file_path, lines_changed)

        # Check if review should be suggested
        if should_suggest_review(state) and codex_available():
            msg = (
                f"Implementation milestone reached: {len(state['files_modified'])} files, "
                f"{state['total_lines_changed']} lines changed. "
                f"Consider Codex review (use /sc:codex-system review)"
            )
            print(json.dumps({"message": msg}))
        else:
            print(json.dumps({}))

    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
```

---

### 7. post-test-analysis.py (called by post-bash-orchestrator)

**Purpose**: Suggest Codex debug analysis on test failures

**Called by**: post-bash-orchestrator.py

**Triggers**:
- Command looks like a test (pytest, npm test, cargo test, etc.)
- Exit code is non-zero (test failure)

```python
#!/usr/bin/env python3
"""
Post-test analysis hook: Suggest Codex debug on test failures.

Called by: post-bash-orchestrator.py
"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path.home() / ".claude" / "lib"))
import bootstrap  # noqa: F401

import json


def is_test_command(command: str) -> bool:
    """Check if command is a test invocation."""
    if not command:
        return False

    cmd_lower = command.lower()
    test_keywords = ["pytest", "npm test", "cargo test", "go test", "python -m unittest"]

    return any(kw in cmd_lower for kw in test_keywords)


def codex_available() -> bool:
    """Check if Codex CLI is available."""
    try:
        from codex_wrapper import find_codex_js, find_node
        find_node()
        find_codex_js()
        return True
    except Exception:
        return False


def main():
    try:
        stdin_data = sys.stdin.read()
        if not stdin_data:
            print(json.dumps({}))
            return

        event_data = json.loads(stdin_data)
        command = event_data.get("command", "")
        exit_code = event_data.get("exit_code", 0)
        output = event_data.get("output", "")

        # Check if test failed
        if is_test_command(command) and exit_code != 0 and codex_available():
            msg = (
                f"Test failure detected (exit code {exit_code}). "
                f"Consider Codex debug analysis (use /sc:codex-system debug)"
            )
            # v19 H-2: Do NOT include test_output — may contain secrets.
            # Only include safe metadata (exit code, test runner name).
            print(json.dumps({"message": msg, "exit_code": exit_code, "runner": command.split()[0]}))
        else:
            print(json.dumps({}))

    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
```

---

### 8. suggest-gemini-research.py (PreToolUse WebSearch|WebFetch)

**Purpose**: Suggest Gemini CLI for research queries

**Hook event**: PreToolUse (WebSearch|WebFetch)

**Triggers**:
- Web search or fetch is about to execute
- Gemini CLI is available

```python
#!/usr/bin/env python3
"""
Pre-web-search hook: Suggest Gemini CLI for research.

Hook event: PreToolUse (WebSearch|WebFetch)
"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path.home() / ".claude" / "lib"))
import bootstrap  # noqa: F401

import json
import shutil


def gemini_available() -> bool:
    """Check if Gemini CLI is available."""
    return shutil.which("gemini") is not None


def main():
    try:
        stdin_data = sys.stdin.read()
        if not stdin_data:
            print(json.dumps({}))
            return

        event_data = json.loads(stdin_data)
        tool_name = event_data.get("tool_name", "")
        query = event_data.get("query", "")

        if tool_name in ("WebSearch", "WebFetch") and gemini_available():
            msg = (
                f"Suggestion: Gemini CLI available for enhanced research. "
                f"Consider using /sc:gemini-system for this query: '{query[:50]}...'"
            )
            print(json.dumps({"message": msg}))
        else:
            print(json.dumps({}))

    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
```

---

### 9. post-write-orchestrator.py (PostToolUse Write|Edit)

**Purpose**: Sequence post-write hooks with fail-safe execution

**Hook event**: PostToolUse (Write|Edit)

**Sequence**:
1. lint-on-save.py (30s timeout)
2. post-implementation-review.py (300s timeout)

**Pattern**: Each sub-hook failure does not block subsequent hooks

```python
#!/usr/bin/env python3
"""
Post-write orchestrator: Sequence post-write hooks.

Hook event: PostToolUse (Write|Edit)

Executes in order:
1. lint-on-save.py (lint fixes first)
2. post-implementation-review.py (review after lint)

Design:
- Each sub-script is independently runnable
- Sub-script failure does not block subsequent scripts (fail-safe)
- Returns JSON with all results
"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path.home() / ".claude" / "lib"))
import bootstrap  # noqa: F401

import subprocess
import json
from pathlib import Path


PYTHON = sys.executable
HOOKS_DIR = Path.home() / ".claude" / "hooks"

# Per-script timeouts: scripts that call Codex need longer timeout
HOOK_TIMEOUTS = {
    "lint-on-save.py": 30,
    "post-implementation-review.py": 300,
}
DEFAULT_TIMEOUT = 30


def run_hook(script_name: str, stdin_data: str) -> dict:
    """
    Run a sub-hook and return results.
    Fail-safe: exceptions are caught and returned as error dict.
    """
    script = HOOKS_DIR / script_name
    if not script.exists():
        return {"script": script_name, "success": False, "error": "not found"}

    timeout = HOOK_TIMEOUTS.get(script_name, DEFAULT_TIMEOUT)

    try:
        result = subprocess.run(
            [PYTHON, str(script)],
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            shell=False,
        )
        return {
            "script": script_name,
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"script": script_name, "success": False, "error": "timeout"}
    except Exception as e:
        return {"script": script_name, "success": False, "error": str(e)}


def main():
    try:
        stdin_data = sys.stdin.read()

        results = []

        # Execute hooks in sequence (fail-safe)
        results.append(run_hook("lint-on-save.py", stdin_data))
        results.append(run_hook("post-implementation-review.py", stdin_data))

        # Return aggregated results
        print(json.dumps({"orchestrator": "post-write", "results": results}))

    except Exception as e:
        print(json.dumps({"orchestrator": "post-write", "error": str(e)}))


if __name__ == "__main__":
    main()
```

---

### 10. post-bash-orchestrator.py (PostToolUse Bash)

**Purpose**: Sequence post-bash hooks with fail-safe execution

**Hook event**: PostToolUse (Bash)

**Sequence**:
1. post-test-analysis.py (300s timeout - may call Codex)
2. log-cli-tools.py (10s timeout)

**Pattern**: Same fail-safe pattern as post-write-orchestrator

```python
#!/usr/bin/env python3
"""
Post-bash orchestrator: Sequence post-bash hooks.

Hook event: PostToolUse (Bash)

Executes in order:
1. post-test-analysis.py (may suggest Codex debug)
2. log-cli-tools.py (log CLI tool usage)

Design:
- Each sub-script is independently runnable
- Sub-script failure does not block subsequent scripts (fail-safe)
- Returns JSON with all results
"""
import sys; sys.path.insert(0, str(__import__('pathlib').Path.home() / ".claude" / "lib"))
import bootstrap  # noqa: F401

import subprocess
import json
from pathlib import Path


PYTHON = sys.executable
HOOKS_DIR = Path.home() / ".claude" / "hooks"

# Per-script timeouts
HOOK_TIMEOUTS = {
    "post-test-analysis.py": 300,  # May trigger Codex
    "log-cli-tools.py": 10,
}
DEFAULT_TIMEOUT = 30


def run_hook(script_name: str, stdin_data: str) -> dict:
    """
    Run a sub-hook and return results.
    Fail-safe: exceptions are caught and returned as error dict.
    """
    script = HOOKS_DIR / script_name
    if not script.exists():
        return {"script": script_name, "success": False, "error": "not found"}

    timeout = HOOK_TIMEOUTS.get(script_name, DEFAULT_TIMEOUT)

    try:
        result = subprocess.run(
            [PYTHON, str(script)],
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            shell=False,
        )
        return {
            "script": script_name,
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"script": script_name, "success": False, "error": "timeout"}
    except Exception as e:
        return {"script": script_name, "success": False, "error": str(e)}


def main():
    try:
        stdin_data = sys.stdin.read()

        results = []

        # Execute hooks in sequence (fail-safe)
        results.append(run_hook("post-test-analysis.py", stdin_data))
        results.append(run_hook("log-cli-tools.py", stdin_data))

        # Return aggregated results
        print(json.dumps({"orchestrator": "post-bash", "results": results}))

    except Exception as e:
        print(json.dumps({"orchestrator": "post-bash", "error": str(e)}))


if __name__ == "__main__":
    main()
```

---

## Settings.json (Complete Merged Version)

This settings.json merges existing configuration with new Orchestra hooks.

**Preserved**:
- `language: "japanese"`
- All existing permissions (allow/ask/deny)
- `autoUpdatesChannel: "latest"`
- Stop hook (session_parser)

**Removed**:
- PermissionRequest hook (redundant with Claude Code native Japanese)

**Added**:
- UserPromptSubmit: agent-router.py
- PreToolUse: check-codex-before-write.py, suggest-gemini-research.py
- PostToolUse: post-write-orchestrator.py, post-bash-orchestrator.py, check-codex-after-plan.py

```json
{
  "language": "japanese",
  "permissions": {
    "allow": [
      "Bash(cmd /c copy:*)",
      "Bash(npm run test:*)",
      "Bash(npm test:*)",
      "Bash(pytest:*)",
      "Bash(cargo test:*)",
      "Bash(git diff:*)",
      "Bash(git status:*)",
      "Bash(git log:*)"
    ],
    "ask": [
      "Bash(git push:*)",
      "Bash(npm publish:*)",
      "Bash(cargo publish:*)"
    ],
    "deny": [
      "Bash(env)",
      "Bash(printenv:*)",
      "Bash(set)",
      "Bash(rm -rf:*)",
      "Bash(del /s /q:*)",
      "Bash(rmdir /s /q:*)",
      "Read(.env)",
      "Read(.env.*)"
    ]
  },
  "autoUpdatesChannel": "latest",
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "C:\\Users\\skyeu\\AppData\\Local\\Programs\\Python\\Python313\\python.exe C:\\Users\\skyeu\\.claude\\hooks\\agent-router.py"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "C:\\Users\\skyeu\\AppData\\Local\\Programs\\Python\\Python313\\python.exe C:\\Users\\skyeu\\.claude\\hooks\\check-codex-before-write.py"
          }
        ]
      },
      {
        "matcher": "WebSearch|WebFetch",
        "hooks": [
          {
            "type": "command",
            "command": "C:\\Users\\skyeu\\AppData\\Local\\Programs\\Python\\Python313\\python.exe C:\\Users\\skyeu\\.claude\\hooks\\suggest-gemini-research.py"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "C:\\Users\\skyeu\\AppData\\Local\\Programs\\Python\\Python313\\python.exe C:\\Users\\skyeu\\.claude\\hooks\\post-write-orchestrator.py"
          }
        ]
      },
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "C:\\Users\\skyeu\\AppData\\Local\\Programs\\Python\\Python313\\python.exe C:\\Users\\skyeu\\.claude\\hooks\\post-bash-orchestrator.py"
          }
        ]
      },
      {
        "matcher": "Task",
        "hooks": [
          {
            "type": "command",
            "command": "C:\\Users\\skyeu\\AppData\\Local\\Programs\\Python\\Python313\\python.exe C:\\Users\\skyeu\\.claude\\hooks\\check-codex-after-plan.py"
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "C:\\Users\\skyeu\\AppData\\Local\\Programs\\Python\\Python313\\python.exe C:\\Users\\skyeu\\.claude\\scripts\\claude_session_parser.py --sync"
          }
        ]
      }
    ]
  }
}
```

---

## Migration Plan

### Step-by-step deployment guide

#### 1. Pre-deployment checks

v19 H-4: All commands use PowerShell (Windows 11 target).

```powershell
# Verify Python installation
& "C:\Users\skyeu\AppData\Local\Programs\Python\Python313\python.exe" --version

# Verify existing hooks directory
Get-ChildItem "$env:USERPROFILE\.claude\hooks" -ErrorAction SilentlyContinue

# Verify existing settings.json
Get-Content "$env:USERPROFILE\.claude\settings.json" -ErrorAction SilentlyContinue

# Backup existing configuration
$backupDir = "$env:USERPROFILE\.claude\backup_$(Get-Date -Format yyyyMMdd)"
New-Item -ItemType Directory -Path $backupDir -Force
if (Test-Path "$env:USERPROFILE\.claude\hooks") {
    Copy-Item -Recurse "$env:USERPROFILE\.claude\hooks" "$backupDir\hooks"
}
if (Test-Path "$env:USERPROFILE\.claude\settings.json") {
    Copy-Item "$env:USERPROFILE\.claude\settings.json" "$backupDir\settings.json"
}
```

#### 2. Create hooks directory (if not exists)

```powershell
New-Item -ItemType Directory -Path "$env:USERPROFILE\.claude\hooks" -Force
New-Item -ItemType Directory -Path "$env:USERPROFILE\.claude\logs" -Force
```

#### 3. Deploy hook scripts

Copy all 10 scripts to `~/.claude/hooks/`:

```powershell
# v19 H-4: PowerShell equivalents
$hooksDir = "$env:USERPROFILE\.claude\hooks"

# Individual hook scripts (8 files)
@(
    "agent-router.py",
    "check-codex-before-write.py",
    "check-codex-after-plan.py",
    "lint-on-save.py",
    "log-cli-tools.py",
    "post-implementation-review.py",
    "post-test-analysis.py",
    "suggest-gemini-research.py",
    "post-write-orchestrator.py",
    "post-bash-orchestrator.py"
) | ForEach-Object { New-Item -ItemType File -Path "$hooksDir\$_" -Force }
```

**Important**: Copy the complete Python code from sections 1-10 above into each respective file.

#### 4. Verify shared library exists

These should already exist from plan-v10.md implementation:

```powershell
# v19 H-4: PowerShell equivalents
@("bootstrap.py", "codex_wrapper.py", "gemini_wrapper.py", "vault_sync.py") | ForEach-Object {
    Test-Path "$env:USERPROFILE\.claude\lib\$_"
}
```

If not present, implement Step 0 (shared library) from plan-v10.md first.

#### 5. Update settings.json

```powershell
# v19 H-4: PowerShell equivalents
Copy-Item "$env:USERPROFILE\.claude\settings.json" "$env:USERPROFILE\.claude\settings.json.backup"

# Replace with new merged settings.json
# Copy the JSON from the "Settings.json (Complete Merged Version)" section above
```

**Critical**: This is a MERGE operation, not a replacement. The new settings.json preserves:
- Existing language setting
- Existing permissions
- Existing Stop hook (session_parser)

#### 6. Test each hook individually

Test hooks one by one to verify they work:

```powershell
# v19 H-4: PowerShell test commands
$py = "C:\Users\skyeu\AppData\Local\Programs\Python\Python313\python.exe"
$hooksDir = "$env:USERPROFILE\.claude\hooks"

# Test 1: agent-router.py (should accept empty stdin)
'{}' | & $py "$hooksDir\agent-router.py"

# Test 2: lint-on-save.py (should skip for non-Python)
'{"file_path": "test.txt"}' | & $py "$hooksDir\lint-on-save.py"

# Test 3: post-write-orchestrator.py (should run sub-hooks)
'{"file_path": "test.py"}' | & $py "$hooksDir\post-write-orchestrator.py"

# Test 4: post-bash-orchestrator.py
'{"command": "pytest", "exit_code": 1}' | & $py "$hooksDir\post-bash-orchestrator.py"
```

Expected: Each test should return valid JSON without errors.

#### 7. Test hooks in Claude Code

1. Restart Claude Code to load new settings.json
2. Test UserPromptSubmit hook:
   - Type a prompt containing "review" or "codex"
   - Should see delegation suggestion
3. Test PreToolUse hook:
   - Ask Claude to write a Python file
   - Should see Codex review suggestion (if file is large)
4. Test PostToolUse hook:
   - Complete a file write operation
   - Check `~/.claude/logs/session_state.json` for tracking
5. Test orchestrators:
   - Write a Python file → should trigger lint + review check
   - Run a test command → should trigger test analysis + logging

#### 8. Verify logging

```powershell
# v19 H-4: PowerShell equivalents
Get-ChildItem "$env:USERPROFILE\.claude\logs" -ErrorAction SilentlyContinue

# Should see:
# - cli_tools.jsonl (if Codex/Gemini was called)
# - session_state.json (if files were written)
# - vault_sync.log (if vault operations occurred)
```

#### 9. Performance check

Monitor hook execution times:

```python
# v19 H-4: This is Python code to add inside hooks (not a shell command)
# Add this to any hook's main() for timing (optional):
import time
start = time.time()
# ... hook code ...
duration = time.time() - start
print(json.dumps({"duration_ms": duration * 1000}))
```

Expected timings:
- agent-router.py: <100ms
- lint-on-save.py: <5s (depends on file size)
- post-implementation-review.py: <100ms (unless triggering Codex)
- Orchestrators: sum of sub-hook times

If any hook consistently takes >30s (excluding Codex calls), investigate.

#### 10. Rollback procedure (if needed)

```powershell
# v19 H-4: PowerShell equivalents
$backupDir = "$env:USERPROFILE\.claude\backup_YYYYMMDD"  # Replace with actual date
Remove-Item -Recurse -Force "$env:USERPROFILE\.claude\hooks"
Copy-Item -Recurse "$backupDir\hooks" "$env:USERPROFILE\.claude\hooks"
Copy-Item "$backupDir\settings.json" "$env:USERPROFILE\.claude\settings.json"

# Restart Claude Code
```

---

## Hook Behavior Reference

### Hook Event Flow

```
User types prompt
    ↓
UserPromptSubmit → agent-router.py (suggests delegation)
    ↓
Claude decides to use Write tool
    ↓
PreToolUse (Write) → check-codex-before-write.py (suggests review)
    ↓
Write tool executes (file is written)
    ↓
PostToolUse (Write) → post-write-orchestrator.py
    ↓
    ├─ lint-on-save.py (auto-lint Python files)
    └─ post-implementation-review.py (track changes, suggest review)

User runs bash command (pytest)
    ↓
PostToolUse (Bash) → post-bash-orchestrator.py
    ↓
    ├─ post-test-analysis.py (detect test failure)
    └─ log-cli-tools.py (log if codex/gemini used)

User creates a task (planning)
    ↓
PostToolUse (Task) → check-codex-after-plan.py (suggest review)

User about to search web
    ↓
PreToolUse (WebSearch) → suggest-gemini-research.py (suggest Gemini)
```

### JSON Schemas

#### Hook Input (stdin)

All hooks receive JSON via stdin with tool-specific fields:

```json
{
  "tool_name": "Write|Edit|Bash|Task|WebSearch|WebFetch",
  "file_path": "path/to/file",
  "content": "file content",
  "command": "bash command",
  "exit_code": 0,
  "output": "command output",
  "query": "search query",
  "prompt": "user prompt",
  "result": "task result"
}
```

#### Hook Output (stdout)

All hooks return JSON to stdout:

```json
{
  "message": "Suggestion or info message to show user",
  "error": "Error message if hook failed",
  "skipped": true,
  "reason": "Why hook was skipped",
  "logged": true,
  "success": true
}
```

Empty object `{}` means hook passed with no action.

---

## Security Notes

1. **shell=False strictly enforced**: All subprocess calls use `shell=False` (except npm path resolution in codex_wrapper.py, which has no user input)
2. **No secrets in logs**: log-cli-tools.py sanitizes environment variables before logging
3. **Input validation**: All hooks validate JSON input before processing
4. **Fail-safe design**: Hook failures never block Claude Code operations
5. **Timeout protection**: All hooks have timeouts (30s-300s depending on operation)
6. **Path validation**: All file operations use pathlib.Path and stay within ~/.claude/

---

## Troubleshooting

### Hook not firing

1. Check settings.json syntax (must be valid JSON)
2. Verify Python path is correct in settings.json
3. Check hook script has execution permissions
4. Restart Claude Code after settings.json changes

### Hook fails with import error

1. Verify bootstrap.py exists in ~/.claude/lib/
2. Check 2-line import template is present at top of hook
3. Verify shared libraries (codex_wrapper.py, etc.) exist

### Hook timeout

1. Check HOOK_TIMEOUTS in orchestrators
2. Increase timeout for slow operations (e.g., Codex calls need 300s)
3. Verify Codex CLI is responding (test manually)

### Lint not working

1. Check ruff is installed: `ruff --version`
2. Verify file is Python (.py extension)
3. Check ruff is in PATH

### Logs not appearing

1. Verify ~/.claude/logs/ directory exists
2. Check write permissions on logs directory
3. Verify hook is actually firing (add debug print)

---

## Future Enhancements

Potential improvements for future versions:

1. **Hook metrics dashboard**: Aggregate hook execution stats
2. **Rate limiting**: Prevent excessive Codex calls from hooks
3. **User preferences**: Per-hook enable/disable switches
4. **Async hooks**: Non-blocking execution for long-running operations
5. **Hook chaining**: More sophisticated orchestrator patterns
6. **Error recovery**: Auto-retry for transient failures
7. **Notification system**: Desktop notifications for important suggestions

---

## Version History

- **v19** (2026-02-07): Codex review fixes (H-1: sanitize_command hardening, H-2: test_output redaction, H-3: empty file_path guard, H-4: PowerShell migration commands, H-5: lint --fix notification)
- **v18** (2026-02-06): Complete hook implementation with all scripts and settings.json
- **v10** (2026-02-03): Plan approved with orchestrator pattern and shared library design
- **v9** (2026-02-02): Claude Code internal review (5 medium + 5 low issues)
- **v8** (2026-02-01): Approved with 2 low issues
- **v1-v7**: Iterative refinement addressing Windows compatibility, security, and design issues

---

## References

- Base plan: `plan-v10.md`
- Shared library design: plan-v10.md Step 0
- Orchestrator pattern: plan-v10.md Step 2
- TetsuyaSynapse integration: plan-v10.md Step 9
- Security policy: plan-v10.md Security Policy section

---

## Summary

This document provides production-ready implementations of:

- **10 hook scripts** (8 individual hooks + 2 orchestrators)
- **1 merged settings.json** (preserves existing config, adds Orchestra hooks)
- **Step-by-step migration plan** (backup, deploy, test, verify)
- **Complete documentation** (behavior reference, troubleshooting, security)

All hooks follow the 2-line bootstrap pattern, use shell=False for security, handle errors gracefully, and integrate with the existing TetsuyaSynapse vault sync system.

Next steps:
1. Review this document for completeness
2. Deploy hooks following the migration plan
3. Test each hook individually
4. Monitor hook performance and logs
5. Iterate based on real-world usage

---

End of plan-v18-hooks.md
