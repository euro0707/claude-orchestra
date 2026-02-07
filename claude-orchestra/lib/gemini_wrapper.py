"""
Gemini CLI wrapper for Orchestra integration.

v18 consolidated version (v10 base + v12-v17 changes):
- Graceful skip when Gemini CLI is not installed
- shell=False strictly enforced
- Prompt via stdin (same policy as codex_wrapper.py)
- context_guard applied before sending
- output_schemas validation (optional)
- retry + budget control via call_gemini_safe()
"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from context_guard import guard_context, ContextGuardError
from output_schemas import validate_output, make_error_response  # v19 L-5: add make_error_response
from budget import check_budget, acquire_slot, release_slot, record_call
from resilience import retry_with_backoff, fallback_to_orchestrator


def find_gemini() -> str | None:
    """
    Resolve Gemini CLI executable path.
    Returns None if not installed (graceful skip).
    """
    path = shutil.which("gemini")
    if path:
        return path
    return None


def call_gemini(query: str, timeout: int = 120, source_files: list[str] = None) -> dict:
    """
    Call Gemini CLI and return results.

    v12: Prompt is passed via stdin to avoid CLI arg length limits.
    v15 E-1: Accepts source_files parameter for context_guard provenance tracking.
    If Gemini CLI is not installed, returns graceful skip result.

    Args:
        query: Research query or prompt to send
        timeout: Timeout in seconds (default 120)
        source_files: v15 E-1: File paths included in context for allowlist enforcement

    Returns:
        dict with keys: success, method, error (if failed), raw_output (if success)
    """
    gemini_path = find_gemini()
    if not gemini_path:
        return {
            "success": False,
            "error": "not_installed",
            "message": "Gemini CLI not found. Install from: https://github.com/google-gemini/gemini-cli",
        }

    # v15 E-1: Apply context guard with source_files provenance
    try:
        guarded_query = guard_context(query, source_files=source_files)
    except ContextGuardError as e:
        return {"success": False, "error": "context_blocked", "message": str(e)}

    try:
        # v12: Pass via stdin (not -p flag) to avoid length limits
        result = subprocess.run(
            [gemini_path],
            input=guarded_query,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            shell=False,
        )
        if result.stdout.strip():
            # Try JSON parse first
            try:
                parsed = json.loads(result.stdout)
                # v19 L-5: Validate Gemini output against schema (consistent with Codex)
                validation = validate_output(parsed, "research")
                if not validation["valid"]:
                    return make_error_response(
                        "research",
                        f"Schema validation failed: {'; '.join(validation['errors'])}",
                        result.stdout[:2000],
                    )
                return {"success": True, "method": "json", **parsed}
            except json.JSONDecodeError:
                return {
                    "success": True,
                    "method": "raw",
                    "raw_output": result.stdout,
                }
        return {
            "success": False,
            "error": "empty_output",
            "stderr": result.stderr[:500] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "timeout", "method": "gemini"}
    except Exception as e:
        return {"success": False, "error": str(e), "method": "gemini"}


def call_gemini_safe(query: str, timeout: int = 120, source_files: list[str] = None) -> dict:
    """
    Safe wrapper around call_gemini with retry, budget, and context guard.

    This is the recommended entry point for all Gemini calls from hooks/skills.

    Args:
        query: Research query or prompt to send
        timeout: Timeout in seconds
        source_files: v15 E-1: File paths included in context for allowlist enforcement
    """
    # Budget check
    budget = check_budget(estimated_tokens=5000)  # Conservative estimate
    if not budget["allowed"]:
        return {
            "success": False,
            "error": "budget_exceeded",
            "remaining_tokens": budget["remaining"],
        }

    if not acquire_slot("gemini"):
        return {
            "success": False,
            "error": "concurrency_limit",
            "message": "Another agent call is in progress. Please wait.",
        }

    import time
    start = time.time()
    result = {}
    try:
        def _call(timeout_factor=1.0):
            adjusted_timeout = int(timeout * timeout_factor)
            return call_gemini(query, adjusted_timeout, source_files=source_files)

        try:
            result = retry_with_backoff(_call, max_retries=1)
        except Exception as e:
            result = {"success": False, "error": str(e), "failure_type": "permanent"}

        if not result.get("success") and result.get("failure_type") == "permanent":
            result = fallback_to_orchestrator("gemini", query[:100], result)

        return result
    finally:
        try:
            elapsed_ms = int((time.time() - start) * 1000)
            tokens = len(str(result.get("raw_output", result.get("result", "")))) // 4
            record_call("gemini", max(tokens, 500), elapsed_ms)
        except Exception:
            pass
        release_slot()
