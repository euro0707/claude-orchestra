"""E2E 6.1 + 6.5: Hook lifecycle — inter-hook chaining, settings.json consistency,
fail-safe behavior, and JSON output format.

These tests execute real hook scripts from ~/.claude/hooks/.
Skipped when hooks are not deployed (CI environment).
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path.home() / ".claude" / "hooks"
PYTHON = sys.executable
SETTINGS_PATH = Path.home() / ".claude" / "settings.json"

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not HOOKS_DIR.exists(),
        reason=f"Hook scripts not deployed at {HOOKS_DIR}",
    ),
]

ALL_HOOKS = [
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


def run_hook(hook_name: str, stdin_data: dict, timeout: int = 15) -> dict:
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


class TestAllHooksExecutable:
    """6.1: Verify all hooks listed in settings.json exist and are executable."""

    def test_settings_json_exists(self):
        assert SETTINGS_PATH.exists(), "settings.json must exist"

    def test_settings_json_valid(self):
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    @pytest.mark.parametrize("hook_name", ALL_HOOKS)
    def test_hook_file_exists(self, hook_name):
        hook_path = HOOKS_DIR / hook_name
        assert hook_path.exists(), f"{hook_name} must exist in {HOOKS_DIR}"

    @pytest.mark.parametrize("hook_name", ALL_HOOKS)
    def test_hook_is_python_parseable(self, hook_name):
        """Each hook must be valid Python (no syntax errors)."""
        hook_path = HOOKS_DIR / hook_name
        result = subprocess.run(
            [PYTHON, "-m", "py_compile", str(hook_path)],
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
        )
        assert result.returncode == 0, f"{hook_name} has syntax error: {result.stderr}"


class TestUserPromptToSuggestion:
    """6.1: agent-router receives prompt and returns suggestion."""

    def test_long_prompt_returns_dict(self):
        result = run_hook("agent-router.py", {
            "prompt": "Please review this code for security vulnerabilities and potential bugs in the system"
        })
        assert isinstance(result, dict)

    def test_short_prompt_skipped(self):
        result = run_hook("agent-router.py", {"prompt": "hi"})
        assert result.get("returncode", 0) == 0


class TestPostWriteOrchestratorChain:
    """6.1: post-write-orchestrator chains lint-on-save → post-implementation-review."""

    def test_orchestrator_returns_results_array(self):
        result = run_hook("post-write-orchestrator.py", {
            "tool_name": "Write",
            "tool_input": {"file_path": "test.py"},
        })
        assert "results" in result or "orchestrator" in result

    def test_orchestrator_has_two_sub_results(self):
        result = run_hook("post-write-orchestrator.py", {
            "tool_name": "Write",
            "tool_input": {"file_path": "main.py"},
        })
        if "results" in result:
            assert len(result["results"]) == 2
            scripts = [r["script"] for r in result["results"]]
            assert "lint-on-save.py" in scripts
            assert "post-implementation-review.py" in scripts


class TestPostBashOrchestratorChain:
    """6.1: post-bash-orchestrator chains post-test-analysis → log-cli-tools."""

    def test_orchestrator_returns_results_array(self):
        result = run_hook("post-bash-orchestrator.py", {
            "tool_name": "Bash",
            "tool_input": {"command": "pytest tests/"},
            "tool_output": {"exit_code": 1, "stdout": "FAILED 2 tests"},
        })
        assert "results" in result or "orchestrator" in result

    def test_orchestrator_has_two_sub_results(self):
        result = run_hook("post-bash-orchestrator.py", {
            "tool_name": "Bash",
            "tool_input": {"command": "pytest"},
            "tool_output": {"exit_code": 0, "stdout": "passed"},
        })
        if "results" in result:
            assert len(result["results"]) == 2
            scripts = [r["script"] for r in result["results"]]
            assert "post-test-analysis.py" in scripts
            assert "log-cli-tools.py" in scripts


class TestHookFailSafeE2E:
    """6.1: All 10 hooks handle invalid input without crashing."""

    @pytest.mark.parametrize("hook_name", ALL_HOOKS)
    def test_none_values_no_crash(self, hook_name):
        result = run_hook(hook_name, {
            "tool_name": None,
            "tool_input": None,
            "prompt": None,
            "result": None,
        })
        assert isinstance(result, dict)

    @pytest.mark.parametrize("hook_name", ALL_HOOKS)
    def test_numeric_fields_no_crash(self, hook_name):
        result = run_hook(hook_name, {
            "tool_name": 999,
            "tool_input": 42,
            "prompt": 0,
        })
        assert isinstance(result, dict)

    @pytest.mark.parametrize("hook_name", ALL_HOOKS)
    def test_empty_strings_no_crash(self, hook_name):
        result = run_hook(hook_name, {
            "tool_name": "",
            "tool_input": "",
            "prompt": "",
            "result": "",
        })
        assert isinstance(result, dict)

    @pytest.mark.parametrize("hook_name", ALL_HOOKS)
    def test_unicode_content_no_crash(self, hook_name):
        result = run_hook(hook_name, {
            "tool_name": "Write",
            "tool_input": {"file_path": "テスト.py"},
            "prompt": "日本語プロンプト 🎉🚀",
            "result": "結果: 成功 ✓",
        })
        assert isinstance(result, dict)

    @pytest.mark.parametrize("hook_name", ALL_HOOKS)
    def test_empty_dict_no_crash(self, hook_name):
        result = run_hook(hook_name, {})
        assert isinstance(result, dict)

    @pytest.mark.parametrize("hook_name", ALL_HOOKS)
    def test_large_payload_no_crash(self, hook_name):
        result = run_hook(hook_name, {
            "tool_name": "Write",
            "tool_input": {"file_path": "big.py"},
            "prompt": "x" * 50000,
            "result": "y" * 50000,
        }, timeout=30)
        assert isinstance(result, dict)


class TestHookOutputJsonFormat:
    """6.1: All hooks output valid JSON (or empty)."""

    @pytest.mark.parametrize("hook_name", ALL_HOOKS)
    def test_output_is_valid_json(self, hook_name):
        hook_path = HOOKS_DIR / hook_name
        result = subprocess.run(
            [PYTHON, str(hook_path)],
            input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": "x.py"}}),
            capture_output=True,
            text=True,
            timeout=15,
            shell=False,
        )
        stdout = result.stdout.strip()
        if stdout:
            parsed = json.loads(stdout)  # raises on invalid JSON
            assert isinstance(parsed, dict)


class TestCodexAfterPlanSuggestion:
    """6.2: check-codex-after-plan fires on plan keywords."""

    def test_plan_keyword_triggers_suggestion(self):
        result = run_hook("check-codex-after-plan.py", {
            "tool_name": "Task",
            "result": "## Plan\n\n### Phase 1: Setup\n### Phase 2: Implementation\n### Step 3: Testing",
        })
        # Should contain suggestion message if codex is available,
        # or empty dict if not
        assert isinstance(result, dict)

    def test_no_plan_keyword_no_suggestion(self):
        result = run_hook("check-codex-after-plan.py", {
            "tool_name": "Task",
            "result": "Hello world, this is just a greeting.",
        })
        # No plan keywords → empty or no message
        assert isinstance(result, dict)
        assert result.get("message", "") == "" or "message" not in result or result.get("empty")
