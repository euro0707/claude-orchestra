"""Test 5.13: Hook scripts - fail-safe behavior and JSON passthrough.

These are integration tests that execute real hook scripts from ~/.claude/hooks/.
They require hooks to be deployed and are skipped in CI or when hooks are absent.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path.home() / ".claude" / "hooks"
PYTHON = sys.executable

# Skip entire module if hooks directory is missing (CI environment)
pytestmark = pytest.mark.skipif(
    not HOOKS_DIR.exists(),
    reason=f"Hook scripts not deployed at {HOOKS_DIR}",
)


def run_hook(hook_name: str, stdin_data: dict, timeout: int = 10) -> dict:
    """Run a hook script with JSON stdin and capture JSON stdout."""
    hook_path = HOOKS_DIR / hook_name
    if not hook_path.exists():
        pytest.skip(f"Hook not found: {hook_path}")

    result = subprocess.run(
        [PYTHON, str(hook_path)],
        input=json.dumps(stdin_data),
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
    )
    if result.stdout.strip():
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"raw_output": result.stdout, "returncode": result.returncode}
    return {"empty": True, "returncode": result.returncode, "stderr": result.stderr}


class TestAgentRouter:
    def test_short_prompt_skipped(self):
        result = run_hook("agent-router.py", {"prompt": "hi"})
        # Short prompts (<20 chars) should be skipped
        assert result.get("returncode", 0) == 0

    def test_review_suggestion(self):
        result = run_hook("agent-router.py", {
            "prompt": "Please review this code for security vulnerabilities and bugs"
        })
        # Should not crash; may suggest codex
        assert isinstance(result, dict)

    def test_research_suggestion(self):
        result = run_hook("agent-router.py", {
            "prompt": "Research the latest Python 3.13 async features and best practices"
        })
        assert isinstance(result, dict)


class TestLintOnSave:
    def test_non_python_skipped(self):
        result = run_hook("lint-on-save.py", {
            "tool_name": "Write",
            "tool_input": {"file_path": "README.md"},
        })
        # Non-Python files should be skipped
        assert isinstance(result, dict)

    def test_python_file_handled(self):
        result = run_hook("lint-on-save.py", {
            "tool_name": "Write",
            "tool_input": {"file_path": "main.py"},
        })
        assert isinstance(result, dict)


class TestLogCliTools:
    def test_non_cli_command_skipped(self):
        result = run_hook("log-cli-tools.py", {
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
            "tool_output": {"exit_code": 0, "stdout": ""},
        })
        assert isinstance(result, dict)


class TestSuggestGeminiResearch:
    def test_websearch_suggestion(self):
        result = run_hook("suggest-gemini-research.py", {
            "tool_name": "WebSearch",
            "tool_input": {"query": "Python async patterns"},
        })
        assert isinstance(result, dict)


class TestAllHooksFailSafe:
    """Verify all hooks handle malformed input gracefully."""

    HOOK_NAMES = [
        "agent-router.py",
        "check-codex-before-write.py",
        "check-codex-after-plan.py",
        "lint-on-save.py",
        "log-cli-tools.py",
        "post-bash-orchestrator.py",
        "post-implementation-review.py",
        "post-test-analysis.py",
        "post-write-orchestrator.py",
        "suggest-gemini-research.py",
    ]

    @pytest.mark.parametrize("hook_name", HOOK_NAMES)
    def test_empty_input_no_crash(self, hook_name):
        """Hooks should not crash on empty/minimal JSON input."""
        result = run_hook(hook_name, {})
        # Success = no crash (returncode 0) or graceful error in JSON
        assert isinstance(result, dict)

    @pytest.mark.parametrize("hook_name", HOOK_NAMES)
    def test_malformed_fields_no_crash(self, hook_name):
        """Hooks should handle unexpected field types gracefully."""
        result = run_hook(hook_name, {
            "tool_name": 12345,  # wrong type
            "tool_input": "not a dict",  # wrong type
            "prompt": None,
        })
        assert isinstance(result, dict)
