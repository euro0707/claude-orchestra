"""
Codex CLI wrapper for Windows environments.

v18 consolidated version (v10 base + v12-v17 changes):
- Execute codex.js directly via node (never use codex.cmd)
- shell=False strictly enforced
- Dynamic codex.js path resolution (CODEX_JS env -> default npm -> npm root -g)
- ALL prompts passed via stdin (never CLI args)
- context_guard applied before sending
- output_schemas validation after receiving
- retry + budget control via call_codex_safe()
"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from cli_finder import find_node, find_codex_js
from context_guard import guard_context, ContextGuardError
from output_schemas import validate_output, make_error_response
from resilience import retry_with_backoff, fallback_to_orchestrator
from budget import check_budget, acquire_slot, release_slot, record_call


def call_codex(mode: str, context: str, timeout: int = 300, source_files: list[str] = None) -> dict:
    """
    Call Codex CLI and return results.

    v15 E-1: Accepts source_files parameter for context_guard provenance tracking.

    All prompts are passed via stdin to avoid CLI arg length limits
    and process-list exposure.

    Staged fallback:
    1. node codex.js exec --json (prompt via stdin) -> parse stdout
    2. If stdout empty -> temp file output via -o
    3. If all fail -> return manual execution command

    Args:
        mode: Operation mode (verify, review, opinion, diff, architecture)
        context: Content to send to Codex
        timeout: Timeout in seconds (default 300)
        source_files: v15 E-1: File paths included in context for allowlist enforcement

    Returns:
        dict with keys: success, method, and mode-specific results
    """
    # P4-2: Wrap path resolution to return structured error instead of raising
    try:
        node_path = find_node()
        codex_js_path = find_codex_js()
    except FileNotFoundError as e:
        return {"success": False, "error": "not_installed", "message": str(e)}

    prompt = f"[mode: {mode}]\n{context}"

    # v15 E-1: Apply context guard with source_files provenance
    try:
        prompt = guard_context(prompt, source_files=source_files)
    except ContextGuardError as e:
        return {"success": False, "error": "context_blocked", "message": str(e)}

    try:
        # --- Stage 1: --json + stdout capture (prompt via stdin) ---
        try:
            result = subprocess.run(
                [
                    node_path,
                    codex_js_path,
                    "exec",
                    "--full-auto",
                    "--json",
                    "--no-alt-screen",
                    "-",
                ],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                shell=False,
            )
            # v19 L-3: Check returncode; non-zero with stdout is still a failure
            if result.returncode != 0:
                return {
                    "success": False,
                    "error": f"codex exited with code {result.returncode}",
                    "method": "stdout",
                    "stderr": (result.stderr or "")[:500],
                    "stdout": (result.stdout or "")[:500],
                }
            if result.stdout.strip():
                try:
                    parsed = json.loads(result.stdout)
                    # v12: Validate structured output for review/verify modes
                    validation = validate_output(parsed, mode)
                    if not validation["valid"]:
                        return make_error_response(
                            mode,
                            f"Schema validation failed: {'; '.join(validation['errors'])}",
                            result.stdout[:2000],
                        )
                    return {"success": True, "method": "stdout", **parsed}
                except json.JSONDecodeError:
                    # v12: For review/verify modes, non-JSON = failure (not success)
                    if mode in ("review", "verify", "architecture"):
                        return make_error_response(
                            mode, "Non-JSON output from --json mode", result.stdout[:2000]
                        )
                    return {
                        "success": True,
                        "method": "stdout_raw",
                        "raw_output": result.stdout,
                    }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "timeout", "method": "stdout"}
        except Exception:
            pass  # Fall through to stage 2

        # --- Stage 2: Temp file output via -o (prompt via stdin) ---
        output_path = None
        try:
            out_tmp = tempfile.NamedTemporaryFile(
                suffix=".md", delete=False, dir=tempfile.gettempdir()
            )
            output_path = out_tmp.name
            out_tmp.close()

            stage2_result = subprocess.run(
                [
                    node_path,
                    codex_js_path,
                    "exec",
                    "--full-auto",
                    "-o",
                    output_path,
                    "-",
                ],
                input=prompt,
                capture_output=True,
                timeout=timeout,
                shell=False,
                encoding="utf-8",
            )
            # v20 Phase1-L2: Check returncode and stderr for Stage 2
            if stage2_result.returncode != 0:
                return {
                    "success": False,
                    "error": f"codex stage2 exited with code {stage2_result.returncode}",
                    "method": "tempfile",
                    "stderr": (stage2_result.stderr or "")[:500],
                }

            output_file = Path(output_path)
            if output_file.exists() and output_file.stat().st_size > 0:
                content = output_file.read_text(encoding="utf-8")
                try:
                    parsed = json.loads(content)
                    # v12: Validate for review/verify modes
                    validation = validate_output(parsed, mode)
                    if not validation["valid"]:
                        return make_error_response(
                            mode,
                            f"Schema validation failed: {'; '.join(validation['errors'])}",
                            content[:2000],
                        )
                    return {"success": True, "method": "tempfile", **parsed}
                except json.JSONDecodeError:
                    # v12: non-JSON = failure for review/verify
                    if mode in ("review", "verify", "architecture"):
                        return make_error_response(
                            mode, "Non-JSON output from -o temp file", content[:2000]
                        )
                    return {
                        "success": True,
                        "method": "tempfile_raw",
                        "raw_output": content,
                    }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "timeout", "method": "tempfile"}
        except Exception:
            pass  # Fall through to stage 3
        finally:
            if output_path:
                try:
                    os.unlink(output_path)
                except OSError:
                    pass

        # --- Stage 3: Manual fallback ---
        return {
            "success": False,
            "error": "all_methods_failed",
            "method": "manual_fallback",
            "manual_command": "codex exec --full-auto -",
            "message": (
                "Codex CLI automatic execution failed. "
                "Please run manually in a separate terminal."
            ),
        }

    except Exception as e:
        return {"success": False, "error": str(e), "method": "exception"}


def call_codex_safe(mode: str, context: str, timeout: int = 300,
                    source_files: list[str] = None) -> dict:
    """
    Safe wrapper around call_codex with retry, budget, and context guard.

    This is the recommended entry point for all Codex calls from hooks/skills.

    Args:
        mode: Operation mode (review, verify, architecture, opinion, diff)
        context: Content to send to Codex
        timeout: Timeout in seconds
        source_files: v15 E-1: File paths included in context for allowlist enforcement
    """
    # Budget check
    budget = check_budget(estimated_tokens=10000)  # Conservative estimate
    if not budget["allowed"]:
        return {
            "success": False,
            "error": "budget_exceeded",
            "remaining_tokens": budget["remaining"],
        }

    if not acquire_slot("codex"):
        return {
            "success": False,
            "error": "concurrency_limit",
            "message": "Another agent call is in progress. Please wait.",
        }

    import time
    start = time.time()
    result = {}  # v13 C-2: Initialize before try to prevent UnboundLocalError
    try:
        def _call(timeout_factor=1.0):
            adjusted_timeout = int(timeout * timeout_factor)
            return call_codex(mode, context, adjusted_timeout,
                              source_files=source_files)  # v15 E-1: propagate

        try:
            result = retry_with_backoff(_call, max_retries=1)
        except Exception as e:
            result = {"success": False, "error": str(e), "failure_type": "permanent"}

        if not result.get("success") and result.get("failure_type") == "permanent":
            result = fallback_to_orchestrator("codex", f"[{mode}] {context[:100]}", result)

        return result
    finally:
        # v13 C-2: release_slot() always runs, record_call() is best-effort
        try:
            elapsed_ms = int((time.time() - start) * 1000)
            tokens = len(str(result.get("raw_output", result.get("summary", "")))) // 4
            record_call("codex", max(tokens, 1000), elapsed_ms)
        except Exception:
            pass  # Never let recording failure mask the real error
        release_slot()
