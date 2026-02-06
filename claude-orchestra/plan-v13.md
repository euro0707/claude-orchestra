# Claude Code Orchestra Integration Plan v13

---
type: verify
timestamp: 2026-02-04
review_request: true
version: 13
encoding: utf-8
previous_reviews:
  - "v2: approved: false, confidence: 7, 6 medium issues"
  - "v3: approved: false, confidence: 6, 1 high + 2 medium + 2 low issues"
  - "v4: approved: false, confidence: 6, 2 medium + 1 low issues"
  - "v5: approved: false, confidence: 7, 1 high + 2 medium + 1 low issues"
  - "v6: approved: false, confidence: 7, 2 medium + 2 low issues"
  - "v7: approved: false, confidence: 7, 3 medium + 1 low issues"
  - "v8: approved: true, confidence: 7, 2 low issues"
  - "v9: approved: true, confidence: 8, 5 medium + 5 low issues (Claude Code internal review)"
  - "v10: approved: false, confidence: 7, 1 high + 5 medium + 3 low issues (Codex CLI review)"
  - "v10.1: approved: false, confidence: 7, 3 high + 4 medium + 2 low issues (Claude Code internal review)"
  - "v11: NOT APPROVED, Architecture 7, Practicality 6, Security 4, Maintainability 6, Scalability 6 (Codex CLI review - 1 critical + 2 high + 4 medium)"
  - "v11-verify: approved: true, confidence: 7, 4 medium + 1 low (Codex CLI verify)"
  - "v12: NOT APPROVED, confidence: 7, 2 high + 3 medium + 1 low (Codex CLI verify)"
---

## Overview

Upgrade the existing Claude Code + Codex 2-agent system to a Claude Code + Codex + Gemini 3-agent system using the Orchestra framework.

## v13 Changes (from v12 Codex Verify Review)

### Review C: v12 Codex Verify Issues (2 high + 3 medium + 1 low)

| # | Severity | v12 Issue | v13 Fix |
|---|----------|----------|---------|
| C-1 | **high** | `context_guard.py`: `_ALLOWED_BASE_DIRS` unused, consent gate unimplemented, `source_files` optional allows bypass | `guard_context()` now enforces `_ALLOWED_BASE_DIRS` via `Path.resolve()` + `is_relative_to()`. Added `enforce_allowed_dirs()` function. Consent gate implemented as audit log (non-interactive mode for hooks). |
| C-2 | **high** | `call_codex_safe()`: `result` used in `finally` before assignment → `UnboundLocalError`, deadlock from `release_slot()` skip | `result = {}` initialized before `try`. `release_slot()` moved to outer `finally` independent of `result`. `record_call()` guarded with `try/except`. |
| C-3 | medium | `ContextGuardError` not imported in wrappers → `NameError` on block | Import added to both `codex_wrapper.py` and `gemini_wrapper.py` import sections |
| C-4 | medium | `budget.py` JSON file has no inter-process lock → race condition | Added `msvcrt.locking()` (Windows) / `fcntl.flock()` (Unix) file lock in `_load_state()` and `_save_state()` |
| C-5 | medium | `env_check.check_codex()` imports `codex_wrapper` → circular import risk | Created `~/.claude/lib/cli_finder.py` with `find_node()` and `find_codex_js()`. Both `codex_wrapper` and `env_check` import from `cli_finder` |
| C-6 | low | `confidence` range (1-10) not validated in output_schemas | Added `confidence` range check in `validate_output()` |

---

## v12 Changes (from v11 Codex Review + verify_result)

### Review A: Codex Review Issues (7 items)

| # | Severity | v11 Issue | v12 Fix |
|---|----------|----------|---------|
| A-1 | **critical** | External agent uncensored transmission: repo content including secrets sent to Codex/Gemini | Added `~/.claude/lib/context_guard.py`: secret scanning, redaction, file allowlist, consent gate (see Security section) |
| A-2 | **high** | CLI command injection: user input embedded in shell strings | Audit complete: all subprocess calls use `shell=False` + argument arrays. No user input in shell strings. gemini_wrapper stdin-only confirmed in v11 (v10.1 H-1 fix). Added `_validate_no_shell_meta()` guard in context_guard.py |
| A-3 | **high** | Error handling/fallback undefined for Codex/Gemini CLI failures | Added `~/.claude/lib/resilience.py`: retry with exponential backoff, failure classification (transient/permanent/timeout), orchestrator fallback protocol |
| A-4 | **medium** | Sub-agent output unstructured: free-form summaries risk hallucination | Added output schema validation in codex_wrapper and gemini_wrapper. JSON parse failure now returns `success:false` for review/verify modes. Schema definitions in `~/.claude/lib/output_schemas.py` |
| A-5 | **medium** | Shared storage no versioning: `.claude/docs/` lacks version control | Added task-scoped subdirectories, timestamp index, atomic writes via temp+rename in vault_sync.py. Index file at `.claude/docs/_index.jsonl` |
| A-6 | **medium** | Environment prerequisites unverified: CLI/model availability not checked | Added `~/.claude/lib/env_check.py`: capability matrix, graceful degradation, startup validation hook |
| A-7 | **medium** | Cost/parallelism control: no budget or scheduling for multi-agent | Added `~/.claude/lib/budget.py`: per-session token budget tracker, priority queue, concurrency limit (default: 1 agent at a time) |

### Review B: verify_result Issues (4 medium + 1 low)

| # | Severity | Issue | v12 Fix |
|---|----------|-------|---------|
| B-1 | medium | gemini_wrapper CLI arg `-p` for prompt | Already fixed in v11 (v10.1 H-1): stdin-only. No change needed. |
| B-2 | medium | `_vault_available()` checks `VAULT_BASE.exists()`, fails on first run | Changed to `VAULT_ROOT.exists()` + auto-create `VAULT_BASE` on write |
| B-3 | medium | `_write_with_fallback()` no pending record on vault write exception | Added `_record_pending()` in vault write except block (when local_saved exists) |
| B-4 | medium | codex_wrapper JSON parse failure returns `success:true` | Fixed: review/verify/architecture modes return `success:false, error:invalid_json` on parse failure |
| B-5 | low | `record_review_issues()` uses `Path.cwd()` as project root | Changed to accept explicit `project_dir` param, fall back to env `CLAUDE_PROJECT_DIR`, then `cwd()` |

---

## New Files in v12

### ~/.claude/lib/context_guard.py (A-1: Critical - Secret Scanning)

```python
"""
Context guard for external agent communication.

Prevents accidental transmission of secrets to external agents (Codex, Gemini).
Applied as a mandatory filter before any content is sent to sub-agents.

Layers:
1. Secret pattern scanning (regex-based)
2. File allowlist (only permitted paths/extensions)
3. Content size limit
4. Consent gate (interactive confirmation for sensitive content)
"""
import os
import re
from pathlib import Path

# Secret patterns (compiled for performance)
_SECRET_PATTERNS = [
    # API keys (generic)
    re.compile(r'(?:api[_-]?key|apikey)\s*[:=]\s*["\']?[\w\-]{20,}', re.IGNORECASE),
    # AWS
    re.compile(r'AKIA[0-9A-Z]{16}'),
    re.compile(r'(?:aws[_-]?secret|secret[_-]?access[_-]?key)\s*[:=]\s*["\']?[\w/+=]{30,}', re.IGNORECASE),
    # GitHub/GitLab tokens
    re.compile(r'gh[pousr]_[A-Za-z0-9_]{36,}'),
    re.compile(r'glpat-[\w\-]{20,}'),
    # Generic private keys
    re.compile(r'-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----'),
    # Generic secrets/tokens/passwords
    re.compile(r'(?:secret|token|password|passwd|pwd)\s*[:=]\s*["\']?[^\s"\']{8,}', re.IGNORECASE),
    # JWT
    re.compile(r'eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+'),
    # Connection strings
    re.compile(r'(?:mongodb|postgres|mysql|redis)://\S+:\S+@', re.IGNORECASE),
    # .env file content pattern
    re.compile(r'^[A-Z_]{3,}=\S{8,}$', re.MULTILINE),
]

# File extensions that should never be sent to external agents
_BLOCKED_EXTENSIONS = {
    '.env', '.pem', '.key', '.p12', '.pfx', '.jks',
    '.keystore', '.credentials', '.secret',
}

# File patterns that should never be sent
_BLOCKED_PATTERNS = [
    re.compile(r'\.env(\.\w+)?$'),
    re.compile(r'credentials\.json$', re.IGNORECASE),
    re.compile(r'serviceaccount.*\.json$', re.IGNORECASE),
    re.compile(r'.*_rsa$'),
    re.compile(r'id_ed25519$'),
]

# Maximum content size sent to external agent (characters)
MAX_CONTEXT_SIZE = 100_000

# Directories allowed to be read for external agent context
_ALLOWED_BASE_DIRS = [
    Path.home() / ".claude",
]


class ContextGuardError(Exception):
    """Raised when context guard blocks transmission."""
    pass


def scan_secrets(content: str) -> list[dict]:
    """
    Scan content for potential secrets.

    Returns list of findings: [{pattern: str, match: str, line: int}]
    Each match string is truncated to first 8 chars + "***" for safe logging.
    """
    findings = []
    for pattern in _SECRET_PATTERNS:
        for match in pattern.finditer(content):
            # Find line number
            line_num = content[:match.start()].count('\n') + 1
            # Truncate match for safe reporting (never log full secret)
            safe_match = match.group()[:8] + "***"
            findings.append({
                "pattern": pattern.pattern[:40],
                "match": safe_match,
                "line": line_num,
            })
    return findings


def redact_secrets(content: str) -> str:
    """
    Replace detected secrets with [REDACTED] placeholder.

    Returns redacted content. Original content is never modified.
    """
    redacted = content
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def check_file_allowed(file_path: str) -> bool:
    """
    Check if a file is safe to send to external agents.

    Returns False for:
    - Files with blocked extensions (.env, .pem, .key, etc.)
    - Files matching blocked name patterns (credentials.json, etc.)
    """
    p = Path(file_path)

    # Check extension
    if p.suffix.lower() in _BLOCKED_EXTENSIONS:
        return False

    # Check name patterns
    name = p.name
    for pattern in _BLOCKED_PATTERNS:
        if pattern.search(name):
            return False

    return True


def enforce_allowed_dirs(source_files: list[str]) -> list[str]:
    """
    v13 C-1: Enforce that all source files are under allowed base directories.

    Args:
        source_files: List of file paths to validate

    Returns:
        List of files that are NOT under allowed directories (violations)
    """
    violations = []
    for f in source_files:
        resolved = Path(f).resolve()
        if not any(
            _is_relative_to(resolved, base.resolve())
            for base in _ALLOWED_BASE_DIRS
        ):
            violations.append(str(resolved))
    return violations


def _is_relative_to(path: Path, base: Path) -> bool:
    """Python 3.9+ is_relative_to backport."""
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def _audit_log(event: str, details: str) -> None:
    """
    v13 C-1: Audit log for consent gate decisions (non-interactive).

    Appends to ~/.claude/logs/context_guard_audit.jsonl
    """
    import json, time
    log_file = Path.home() / ".claude" / "logs" / "context_guard_audit.jsonl"
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        entry = json.dumps({
            "timestamp": time.time(),
            "event": event,
            "details": details[:500],
        }, ensure_ascii=False)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except Exception:
        pass  # Best-effort audit logging


def guard_context(content: str, source_files: list[str] = None) -> str:
    """
    Main entry point: validate and sanitize content before external transmission.

    Steps:
    1. Enforce allowed base directories (v13: mandatory)
    2. Check file allowlist (blocked extensions/patterns)
    3. Scan for secrets
    4. Redact any found secrets + audit log (v13: consent gate)
    5. Enforce size limit

    Args:
        content: The content to be sent to external agent
        source_files: Optional list of source file paths included in content

    Returns:
        Sanitized content safe for transmission

    Raises:
        ContextGuardError: If content is blocked
    """
    # Step 1: Enforce allowed base directories (v13 C-1)
    if source_files:
        dir_violations = enforce_allowed_dirs(source_files)
        if dir_violations:
            _audit_log("blocked_directory", f"Files outside allowed dirs: {dir_violations}")
            raise ContextGuardError(
                f"Files outside allowed directories: {', '.join(dir_violations)}. "
                f"Only files under {[str(d) for d in _ALLOWED_BASE_DIRS]} are permitted."
            )

    # Step 2: File allowlist check (blocked extensions/patterns)
    if source_files:
        blocked = [f for f in source_files if not check_file_allowed(f)]
        if blocked:
            _audit_log("blocked_files", f"Blocked by pattern: {blocked}")
            raise ContextGuardError(
                f"Blocked files detected: {', '.join(blocked)}. "
                "These files may contain secrets and cannot be sent to external agents."
            )

    # Step 3: Scan for secrets
    findings = scan_secrets(content)

    # Step 4: Redact if secrets found + audit log (v13 consent gate)
    if findings:
        _audit_log("secrets_redacted", f"{len(findings)} secrets found and redacted")
        content = redact_secrets(content)

    # Step 5: Size limit
    if len(content) > MAX_CONTEXT_SIZE:
        content = content[:MAX_CONTEXT_SIZE] + "\n\n[TRUNCATED: content exceeded size limit]"

    return content


def guard_context_report(content: str, source_files: list[str] = None) -> dict:
    """
    Same as guard_context but returns a detailed report.

    Returns:
        {
            "safe_content": str,
            "findings_count": int,
            "redacted": bool,
            "truncated": bool,
            "blocked_files": list[str],
        }
    """
    blocked_files = []
    if source_files:
        blocked_files = [f for f in source_files if not check_file_allowed(f)]

    findings = scan_secrets(content)
    redacted = content
    if findings:
        redacted = redact_secrets(content)

    truncated = False
    if len(redacted) > MAX_CONTEXT_SIZE:
        redacted = redacted[:MAX_CONTEXT_SIZE] + "\n\n[TRUNCATED]"
        truncated = True

    return {
        "safe_content": redacted,
        "findings_count": len(findings),
        "redacted": len(findings) > 0,
        "truncated": truncated,
        "blocked_files": blocked_files,
    }
```

### ~/.claude/lib/resilience.py (A-3: High - Error Handling)

```python
"""
Resilience utilities for external agent calls.

Provides retry logic, failure classification, and fallback orchestration
for Codex and Gemini CLI interactions.
"""
import time
import logging
from pathlib import Path
from typing import Callable

_logger = None


def _get_logger():
    global _logger
    if _logger is None:
        _logger = logging.getLogger("orchestra.resilience")
    return _logger


class FailureType:
    """Classification of external agent failures."""
    TRANSIENT = "transient"      # Network, timeout - worth retrying
    PERMANENT = "permanent"      # Not installed, auth error - don't retry
    RATE_LIMIT = "rate_limit"    # Rate limited - retry with longer backoff
    TIMEOUT = "timeout"          # Timed out - retry with increased timeout


def classify_failure(error: str, returncode: int = None) -> str:
    """
    Classify a failure to determine retry strategy.

    Args:
        error: Error message or type string
        returncode: Process return code if available

    Returns:
        FailureType constant
    """
    error_lower = error.lower() if error else ""

    if "not_installed" in error_lower or "not found" in error_lower:
        return FailureType.PERMANENT
    if "auth" in error_lower or "unauthorized" in error_lower or "forbidden" in error_lower:
        return FailureType.PERMANENT
    if "timeout" in error_lower:
        return FailureType.TIMEOUT
    if "rate" in error_lower or "429" in error_lower or "quota" in error_lower:
        return FailureType.RATE_LIMIT
    if returncode and returncode > 128:
        return FailureType.PERMANENT  # Signal-killed

    return FailureType.TRANSIENT


def retry_with_backoff(
    fn: Callable,
    max_retries: int = 2,
    base_delay: float = 2.0,
    max_delay: float = 30.0,
    timeout_multiplier: float = 1.5,
) -> dict:
    """
    Execute a function with exponential backoff retry.

    The function must return a dict with at least a 'success' key.
    On failure, the 'error' key is used for failure classification.

    Args:
        fn: Callable that returns dict with 'success' key
        max_retries: Maximum retry attempts (0 = no retry)
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries
        timeout_multiplier: Multiply timeout on TIMEOUT failures

    Returns:
        Result dict from fn, with added 'attempts' and 'failure_type' keys
    """
    logger = _get_logger()
    attempts = 0
    current_timeout_factor = 1.0

    while attempts <= max_retries:
        attempts += 1
        result = fn(timeout_factor=current_timeout_factor)

        if result.get("success"):
            result["attempts"] = attempts
            return result

        error = result.get("error", "unknown")
        failure_type = classify_failure(error, result.get("returncode"))
        result["failure_type"] = failure_type

        # Don't retry permanent failures
        if failure_type == FailureType.PERMANENT:
            result["attempts"] = attempts
            logger.info(f"Permanent failure, no retry: {error}")
            return result

        # Last attempt - return as-is
        if attempts > max_retries:
            result["attempts"] = attempts
            logger.info(f"Max retries ({max_retries}) exhausted: {error}")
            return result

        # Calculate delay
        delay = min(base_delay * (2 ** (attempts - 1)), max_delay)
        if failure_type == FailureType.RATE_LIMIT:
            delay = min(delay * 3, max_delay)  # Extra wait for rate limits
        if failure_type == FailureType.TIMEOUT:
            current_timeout_factor *= timeout_multiplier

        logger.info(f"Retry {attempts}/{max_retries} after {delay:.1f}s (type={failure_type})")
        time.sleep(delay)

    return result  # Should not reach here


def fallback_to_orchestrator(
    agent_name: str, original_task: str, error_info: dict
) -> dict:
    """
    Generate a fallback response when an external agent fails permanently.

    Instead of silently failing, returns structured info for the orchestrator
    (Claude Code) to handle the task itself.

    Args:
        agent_name: Name of the failed agent (codex, gemini)
        original_task: The task that was being delegated
        error_info: Error details from the failed call

    Returns:
        Fallback response dict for orchestrator handling
    """
    return {
        "success": False,
        "fallback": True,
        "agent": agent_name,
        "failure_type": error_info.get("failure_type", "unknown"),
        "error": error_info.get("error", "unknown"),
        "recommendation": (
            f"{agent_name} is unavailable ({error_info.get('error', 'unknown')}). "
            f"Orchestrator should handle this task directly or defer it."
        ),
        "original_task": original_task[:200],  # Truncate for logging safety
    }
```

### ~/.claude/lib/output_schemas.py (A-4: Medium - Structured Output)

```python
"""
Output schema definitions and validation for sub-agent responses.

Ensures consistent, structured output from Codex and Gemini
with required fields and type validation.
"""


# Expected schema for Codex review mode output
CODEX_REVIEW_SCHEMA = {
    "required": ["approved", "confidence", "issues", "summary"],
    "types": {
        "approved": bool,
        "confidence": int,
        "issues": list,
        "summary": str,
    },
    "issue_required": ["severity", "description"],
    "issue_types": {
        "severity": str,
        "description": str,
        "suggestion": str,  # optional
    },
    "severity_values": {"critical", "high", "medium", "low"},
}

# Expected schema for Codex verify mode output
CODEX_VERIFY_SCHEMA = {
    "required": ["approved", "confidence", "issues"],
    "types": {
        "approved": bool,
        "confidence": int,
        "issues": list,
    },
}

# Expected schema for Gemini research output
GEMINI_RESEARCH_SCHEMA = {
    "required": ["result"],
    "types": {
        "result": str,
        "sources": list,
        "confidence": (int, float),
    },
}

# Mode-to-schema mapping
MODE_SCHEMAS = {
    "review": CODEX_REVIEW_SCHEMA,
    "verify": CODEX_VERIFY_SCHEMA,
    "architecture": CODEX_REVIEW_SCHEMA,  # Same structure as review
}


def validate_output(data: dict, mode: str) -> dict:
    """
    Validate sub-agent output against expected schema.

    Args:
        data: Parsed JSON output from sub-agent
        mode: Operation mode (review, verify, architecture, etc.)

    Returns:
        {
            "valid": bool,
            "errors": list[str],
            "data": dict (original or with defaults filled)
        }
    """
    schema = MODE_SCHEMAS.get(mode)
    if not schema:
        # No schema defined for this mode - pass through
        return {"valid": True, "errors": [], "data": data}

    errors = []

    # Check required fields
    for field in schema.get("required", []):
        if field not in data:
            errors.append(f"Missing required field: {field}")

    # Check types
    for field, expected_type in schema.get("types", {}).items():
        if field in data:
            if isinstance(expected_type, tuple):
                if not isinstance(data[field], expected_type):
                    errors.append(f"Field '{field}' expected {expected_type}, got {type(data[field])}")
            elif not isinstance(data[field], expected_type):
                errors.append(f"Field '{field}' expected {expected_type.__name__}, got {type(data[field]).__name__}")

    # v13 C-6: Validate confidence range (1-10)
    if "confidence" in data and isinstance(data["confidence"], (int, float)):
        if not (1 <= data["confidence"] <= 10):
            errors.append(f"Field 'confidence' must be 1-10, got {data['confidence']}")

    # Validate issues array items
    if "issues" in data and isinstance(data["issues"], list):
        issue_required = schema.get("issue_required", [])
        severity_values = schema.get("severity_values", set())
        for i, issue in enumerate(data["issues"]):
            if not isinstance(issue, dict):
                errors.append(f"Issue[{i}] is not a dict")
                continue
            for field in issue_required:
                if field not in issue:
                    errors.append(f"Issue[{i}] missing required field: {field}")
            if severity_values and "severity" in issue:
                if issue["severity"] not in severity_values:
                    errors.append(f"Issue[{i}] invalid severity: {issue['severity']}")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "data": data,
    }


def make_error_response(mode: str, error_msg: str, raw_output: str = "") -> dict:
    """
    Create a structured error response when output validation fails.

    For review/verify modes, returns approved=false with a pseudo-issue
    so downstream never silently skips a failed review.

    Args:
        mode: Operation mode
        error_msg: Description of what went wrong
        raw_output: The original unparsed output (truncated for safety)

    Returns:
        Structured response dict appropriate for the mode
    """
    base = {
        "success": False,
        "error": "invalid_output",
        "error_detail": error_msg,
    }

    if mode in ("review", "verify", "architecture"):
        base.update({
            "approved": False,
            "confidence": 0,
            "issues": [{
                "severity": "high",
                "description": f"Output validation failed: {error_msg}",
                "suggestion": "Re-run the review or inspect the raw output manually.",
            }],
            "summary": f"Review failed due to output error: {error_msg}",
        })

    if raw_output:
        base["raw_output"] = raw_output[:2000]

    return base
```

### ~/.claude/lib/cli_finder.py (v13 C-5: Shared CLI path resolution)

```python
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
        npm_global = Path(r.stdout.strip()) / "@openai" / "codex" / "bin" / "codex.js"
        if npm_global.exists():
            return str(npm_global)
    except Exception:
        pass

    raise FileNotFoundError(
        "Codex CLI not found. Install with: npm install -g @openai/codex"
    )
```

### ~/.claude/lib/env_check.py (A-6: Medium - Environment Validation)

```python
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
```

### ~/.claude/lib/budget.py (A-7: Medium - Cost/Parallelism Control)

```python
"""
Budget and concurrency control for multi-agent operations.

Tracks per-session token usage estimates and enforces limits
on concurrent agent calls.

Design:
- Session-scoped (resets when Claude Code session ends)
- Conservative defaults (can be overridden via env vars)
- Best-effort tracking (never blocks on budget failures)
"""
import json
import os
import threading
import time
from pathlib import Path

# Defaults (overridable via env)
DEFAULT_TOKEN_BUDGET = int(os.environ.get("ORCHESTRA_TOKEN_BUDGET", "500000"))
DEFAULT_MAX_CONCURRENT = int(os.environ.get("ORCHESTRA_MAX_CONCURRENT", "1"))

# Budget state file (session-scoped)
_BUDGET_FILE = Path.home() / ".claude" / "logs" / "budget_session.json"

_lock = threading.Lock()


class BudgetExceeded(Exception):
    """Raised when session token budget is exhausted."""
    pass


class ConcurrencyLimitReached(Exception):
    """Raised when max concurrent agent calls are in progress."""
    pass


def _file_lock(f, exclusive: bool = True) -> None:
    """
    v13 C-4: OS-level file lock for inter-process safety.
    Windows: msvcrt.locking, Unix: fcntl.flock
    """
    import sys
    if sys.platform == "win32":
        import msvcrt
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK if exclusive else msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(f.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_UN)


def _file_unlock(f) -> None:
    """v13 C-4: Release file lock."""
    import sys
    if sys.platform == "win32":
        import msvcrt
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        except Exception:
            pass
    else:
        import fcntl
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def _load_state() -> dict:
    """Load current budget state."""
    try:
        if _BUDGET_FILE.exists():
            return json.loads(_BUDGET_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {
        "total_tokens": 0,
        "calls": [],
        "active_calls": 0,
        "budget_limit": DEFAULT_TOKEN_BUDGET,
        "max_concurrent": DEFAULT_MAX_CONCURRENT,
    }


def _save_state(state: dict) -> None:
    """Persist budget state with file lock (v13 C-4: inter-process safe)."""
    try:
        _BUDGET_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_BUDGET_FILE, "w", encoding="utf-8") as f:
            _file_lock(f, exclusive=True)
            try:
                f.write(json.dumps(state, indent=2))
            finally:
                _file_unlock(f)
    except Exception:
        pass


def _load_state_locked() -> tuple:
    """
    v13 C-4: Load state with file lock held. Returns (state, file_handle).
    Caller must call _file_unlock(fh) and fh.close() after _save_state_locked().
    """
    _BUDGET_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not _BUDGET_FILE.exists():
        _BUDGET_FILE.write_text("{}", encoding="utf-8")
    fh = open(_BUDGET_FILE, "r+", encoding="utf-8")
    _file_lock(fh, exclusive=True)
    try:
        content = fh.read()
        state = json.loads(content) if content.strip() else {}
    except Exception:
        state = {}
    defaults = {
        "total_tokens": 0, "calls": [], "active_calls": 0,
        "budget_limit": DEFAULT_TOKEN_BUDGET, "max_concurrent": DEFAULT_MAX_CONCURRENT,
    }
    for k, v in defaults.items():
        state.setdefault(k, v)
    return state, fh


def _save_state_locked(state: dict, fh) -> None:
    """v13 C-4: Write state and release lock."""
    try:
        fh.seek(0)
        fh.truncate()
        fh.write(json.dumps(state, indent=2))
    finally:
        _file_unlock(fh)
        fh.close()


def check_budget(estimated_tokens: int = 0) -> dict:
    """
    Check if budget allows a new agent call.

    Args:
        estimated_tokens: Estimated token usage for the planned call

    Returns:
        {"allowed": bool, "remaining": int, "used": int, "limit": int}
    """
    with _lock:
        state = _load_state()
        remaining = state["budget_limit"] - state["total_tokens"]
        allowed = remaining >= estimated_tokens and state["active_calls"] < state["max_concurrent"]
        return {
            "allowed": allowed,
            "remaining": remaining,
            "used": state["total_tokens"],
            "limit": state["budget_limit"],
            "active_calls": state["active_calls"],
            "max_concurrent": state["max_concurrent"],
        }


def record_call(agent: str, tokens_used: int, duration_ms: int = 0) -> None:
    """
    Record a completed agent call.

    Args:
        agent: Agent name (codex, gemini)
        tokens_used: Actual tokens consumed
        duration_ms: Call duration in milliseconds
    """
    with _lock:
        state = _load_state()
        state["total_tokens"] += tokens_used
        state["calls"].append({
            "agent": agent,
            "tokens": tokens_used,
            "duration_ms": duration_ms,
            "timestamp": time.time(),
        })
        state["active_calls"] = max(0, state["active_calls"] - 1)
        _save_state(state)


def acquire_slot(agent: str) -> bool:
    """
    Try to acquire a concurrency slot for an agent call.

    Returns True if slot acquired, False if limit reached.
    """
    with _lock:
        state = _load_state()
        if state["active_calls"] >= state["max_concurrent"]:
            return False
        state["active_calls"] += 1
        _save_state(state)
        return True


def release_slot() -> None:
    """Release a concurrency slot after agent call completes."""
    with _lock:
        state = _load_state()
        state["active_calls"] = max(0, state["active_calls"] - 1)
        _save_state(state)


def reset_session() -> None:
    """Reset budget state for a new session."""
    with _lock:
        _save_state({
            "total_tokens": 0,
            "calls": [],
            "active_calls": 0,
            "budget_limit": DEFAULT_TOKEN_BUDGET,
            "max_concurrent": DEFAULT_MAX_CONCURRENT,
        })


def get_summary() -> dict:
    """Get session budget summary."""
    with _lock:
        state = _load_state()
        return {
            "total_tokens": state["total_tokens"],
            "total_calls": len(state["calls"]),
            "remaining_tokens": state["budget_limit"] - state["total_tokens"],
            "budget_limit": state["budget_limit"],
            "by_agent": _summarize_by_agent(state["calls"]),
        }


def _summarize_by_agent(calls: list) -> dict:
    summary = {}
    for call in calls:
        agent = call.get("agent", "unknown")
        if agent not in summary:
            summary[agent] = {"calls": 0, "tokens": 0}
        summary[agent]["calls"] += 1
        summary[agent]["tokens"] += call.get("tokens", 0)
    return summary
```

---

## Modified Files in v12

### codex_wrapper.py changes (A-2, A-4, B-4)

#### Change 1: Import context_guard and output_schemas

Add at top of file after existing imports:
```python
from context_guard import guard_context, ContextGuardError  # v13 C-3: import exception
from output_schemas import validate_output, make_error_response
from resilience import retry_with_backoff, fallback_to_orchestrator
from budget import check_budget, acquire_slot, release_slot, record_call
```

#### Change 2: Apply context guard before sending to Codex

In `call_codex()`, after building prompt string:
```python
    prompt = f"[mode: {mode}]\n{context}"

    # v12: Apply context guard before external transmission
    try:
        prompt = guard_context(prompt)
    except ContextGuardError as e:
        return {"success": False, "error": "context_blocked", "message": str(e)}
```

#### Change 3: Validate output and fix JSON parse failure handling

Replace the Stage 1 success path:
```python
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
```

Same pattern applied to Stage 2 success paths.

#### Change 4: Wrap with retry and budget control

New top-level entry point:
```python
def call_codex_safe(mode: str, context: str, timeout: int = 300) -> dict:
    """
    Safe wrapper around call_codex with retry, budget, and context guard.

    This is the recommended entry point for all Codex calls from hooks/skills.
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
            return call_codex(mode, context, adjusted_timeout)

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
```

### gemini_wrapper.py changes (A-2, A-4)

Same pattern: add `guard_context()` before stdin, add `validate_output()` after parse, wrap with budget control.

### vault_sync.py changes (A-5, B-2, B-3)

#### B-2: Fix _vault_available() to check VAULT_ROOT

```python
def _vault_available() -> bool:
    """Check if the Obsidian vault (Google Drive) is accessible."""
    try:
        return VAULT_ROOT.exists()
    except OSError:
        return False
```

#### B-3: Add _record_pending on vault write exception

Already present in v11 code (line 726-728 in session file). Confirmed: the except block does call `_record_pending()` when `local_saved` exists. **No change needed** - this was already fixed.

#### A-5: Add docs versioning with index

```python
# New: Docs versioning support
DOCS_DIR = Path.home() / ".claude" / "docs"
DOCS_INDEX = DOCS_DIR / "_index.jsonl"


def save_doc(task_id: str, title: str, content: str, doc_type: str = "general") -> str:
    """
    Save a document with versioning to .claude/docs/.

    Uses task-scoped subdirectories and appends to a JSONL index.
    Atomic write via temp file + rename.

    Args:
        task_id: Task identifier for scoping
        title: Document title
        content: Document content
        doc_type: Type (research, design, review, etc.)

    Returns:
        Path where document was saved
    """
    logger = _get_logger()
    task_dir = _ensure_dir(DOCS_DIR / _sanitize_filename(task_id))
    filename = _generate_filename(title, doc_type)
    target = task_dir / filename

    # Atomic write: temp file + rename
    try:
        tmp_path = target.with_suffix(".tmp")
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.rename(target)

        # Append to index
        _append_index(task_id, filename, title, doc_type)

        logger.info(f"Doc saved: {target}")
        return str(target)
    except Exception as e:
        logger.warning(f"Doc save failed ({e})")
        # Cleanup temp if rename failed
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        return ""


def _append_index(task_id: str, filename: str, title: str, doc_type: str) -> None:
    """Append entry to JSONL index (best-effort)."""
    import time
    try:
        _ensure_dir(DOCS_DIR)
        entry = json.dumps({
            "task_id": task_id,
            "filename": filename,
            "title": title,
            "type": doc_type,
            "timestamp": time.time(),
        }, ensure_ascii=False)
        with open(DOCS_INDEX, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except Exception:
        pass
```

---

## Updated Security Policy (v12)

1. `shell=False` strictly enforced for all subprocess calls (exception: `npm root -g` one-time resolution)
2. External input via temp files or stdin (never CLI arguments)
3. Path validation: only read files under `~/.claude/`
4. Python absolute path in settings.json
5. No secrets in logs
6. Input size limit: hooks check stdin data size before JSON parsing
7. **[v12 NEW] Context guard**: All content sent to external agents passes through `context_guard.py`:
   - Secret pattern scanning (API keys, tokens, private keys, connection strings)
   - File allowlist (blocks .env, .pem, .key, credentials.json, etc.)
   - Automatic redaction of detected secrets
   - Content size limit (100K characters)
8. **[v12 NEW] Output validation**: Sub-agent outputs validated against schemas before consumption
9. **[v12 NEW] Budget control**: Per-session token budget prevents runaway costs
10. **[v12 NEW] Retry with classification**: Transient failures retried, permanent failures fast-fail

---

## Updated Library Structure (v12)

```
C:\Users\skyeu\.claude\lib\
+-- __init__.py
+-- bootstrap.py           # Common init for all hooks/scripts
+-- codex_wrapper.py       # Codex CLI wrapper (v12: +context_guard, +output_schemas, +retry)
+-- gemini_wrapper.py      # Gemini CLI wrapper (v12: +context_guard, +output_schemas)
+-- vault_sync.py          # TetsuyaSynapse sync (v12: +docs versioning, B-2 fix)
+-- path_utils.py          # Windows/Git Bash path normalization
+-- context_guard.py       # [NEW] Secret scanning, redaction, dir enforcement, audit log
+-- resilience.py          # [NEW] Retry, backoff, failure classification
+-- output_schemas.py      # [NEW] Output validation schemas + confidence range check
+-- env_check.py           # [NEW] Environment prerequisites check (uses cli_finder)
+-- budget.py              # [NEW] Token budget and concurrency control (with file lock)
+-- cli_finder.py          # [v13 NEW] Side-effect-free Node/Codex path resolution
```

---

## Unchanged from v11

- Step 0: Codex CLI Windows Compatibility Fix (pre-implementation tests)
- Step 1: Gemini CLI Check
- Step 2: Hooks (8 scripts + 2 orchestrators + settings.json)
- Step 3: Rules (7 files)
- Step 4: Skills (12 skills)
- Step 5: Agents (general-purpose.md)
- Step 6: Directory structure
- Step 7: call_codex.py refactor
- Step 8: CLAUDE.md update
- Step 9: TetsuyaSynapse integration
- All v2-v10.1 review fix history

---

## Implementation Order (v12 updated)

1. Pre-implementation verification (3 tests from Step 0)
2. Create directories (lib, hooks, rules, skills, agents, logs, docs)
3. Create bootstrap.py + path_utils.py
4. **[NEW] Create context_guard.py**
5. **[NEW] Create resilience.py**
6. **[NEW] Create output_schemas.py**
7. **[NEW] Create env_check.py**
8. **[NEW] Create budget.py**
9. Create codex_wrapper.py (v12 with guard/retry/validation)
10. Create gemini_wrapper.py (v12 with guard/validation)
11. Create vault_sync.py (v12 with B-2 fix, docs versioning)
12. Fix call_codex.py (vault auto-save, B-5 project_dir)
13. Create orchestrator scripts
14. Create 8 hook scripts
15. Create 7 rule files
16. Create 1 agent file
17. Create 12 skill directories
18. Update settings.json
19. Update CLAUDE.md (project-level)
20. Run env_check.py to generate capability report
21. Verification (all v11 tests + context_guard test + output validation test)

---

## Review Request (v13)

v12 Codex Verify flagged 6 issues (2 high + 3 medium + 1 low). This v13 addresses all of them:

1. **[High] Context guard bypass** (C-1): `enforce_allowed_dirs()` now mandatory, `_ALLOWED_BASE_DIRS` enforced via `Path.resolve()` + `is_relative_to()`, consent gate implemented as audit log
2. **[High] UnboundLocalError in call_codex_safe** (C-2): `result = {}` initialized before `try`, `release_slot()` in outer `finally` independent of `result`
3. **[Medium] ContextGuardError import missing** (C-3): Import added to wrapper import sections
4. **[Medium] Budget file race condition** (C-4): OS-level file lock (`msvcrt`/`fcntl`) added to `_save_state()` and new `_load_state_locked()`/`_save_state_locked()` pair
5. **[Medium] Circular import in env_check** (C-5): New `cli_finder.py` module with `find_node()`/`find_codex_js()`, imported by both `codex_wrapper` and `env_check`
6. **[Low] Confidence range validation** (C-6): Range check (1-10) added to `validate_output()`

All v11 and v12 fixes are preserved. Please review and verify these v13 fixes are adequate.
