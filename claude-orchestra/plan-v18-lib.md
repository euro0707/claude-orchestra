# Orchestra Integration Plan v18 - Library Code

---
type: implementation
version: 18
timestamp: 2026-02-06
previous: v17 (APPROVED)
---

## Overview
Complete library code for ~/.claude/lib/. Each section is a copy-paste-ready Python file.

## Changes from v17
- Added path_utils.py (C-2 gap - was never defined before)
- Updated bootstrap.py with CLAUDE_PROJECT_DIR auto-detection (C-3 gap)
- Fixed budget.py 1-byte lock issue (I-6)
- Fixed unguarded fh variables in budget.py (M-6)
- Consolidated codex_wrapper.py and gemini_wrapper.py (I-2, I-3)

## Changes from v18 (Codex Review v19 fixes)
- **L-1**: Applied `path_utils.normalize_path` in bootstrap.py, context_guard.py (_build_allowed_dirs, enforce_allowed_dirs)
- **L-2**: cli_finder.find_codex_js now requires `returncode == 0` and non-empty stdout from `npm root -g`
- **L-3**: codex_wrapper.call_codex checks subprocess returncode; includes stderr in error response
- **L-4**: env_check.check_node/check_codex/check_gemini verify returncode before reporting available
- **L-5**: gemini_wrapper.call_gemini validates JSON output against GEMINI_RESEARCH_SCHEMA

## File: __init__.py

```python
"""
Orchestra library for Claude Code.

Provides shared utilities for multi-agent coordination (Claude Code, Codex, Gemini).
"""

__version__ = "1.0.0"

# Re-export main modules for convenience
from . import bootstrap
from . import codex_wrapper
from . import gemini_wrapper
from . import vault_sync
from . import path_utils
from . import context_guard
from . import resilience
from . import output_schemas
from . import env_check
from . import budget
from . import cli_finder

__all__ = [
    "bootstrap",
    "codex_wrapper",
    "gemini_wrapper",
    "vault_sync",
    "path_utils",
    "context_guard",
    "resilience",
    "output_schemas",
    "env_check",
    "budget",
    "cli_finder",
]
```

## File: path_utils.py

```python
"""Windows/Git Bash path normalization utilities."""
import os
import re
from pathlib import Path


def normalize_path(path_str: str) -> str:
    """
    Convert Git Bash /c/Users/... to Windows C:\\Users\\...

    Git Bash (MSYS2) uses Unix-style paths like /c/Users/... but Python subprocess
    on Windows requires native paths like C:\\Users\\...

    Args:
        path_str: Path string (may be MSYS2 format or Windows format)

    Returns:
        Windows-style path string
    """
    if not path_str:
        return path_str
    # Git Bash MSYS2 path pattern: /c/path or /C/path
    match = re.match(r'^/([a-zA-Z])(/.*)?$', path_str)
    if match:
        drive = match.group(1).upper()
        rest = match.group(2) or ''
        return f"{drive}:{rest}".replace('/', '\\')
    return path_str


def to_windows_path(path) -> Path:
    """
    Ensure path is Windows-style Path object.

    Args:
        path: str or Path object (may be MSYS2 format)

    Returns:
        pathlib.Path object with Windows-style path
    """
    if isinstance(path, str):
        path = normalize_path(path)
    return Path(path)


def to_posix_string(path) -> str:
    """
    Convert path to POSIX string for subprocess.

    Some CLI tools expect forward slashes even on Windows.

    Args:
        path: str or Path object

    Returns:
        POSIX-style path string (forward slashes)
    """
    p = Path(path)
    return str(p).replace('\\', '/')
```

## File: bootstrap.py

```python
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
```

## File: cli_finder.py

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
```

## File: context_guard.py

```python
"""
Context guard for external agent communication.

Prevents accidental transmission of secrets to external agents (Codex, Gemini).
Applied as a mandatory filter before any content is sent to sub-agents.

Layers:
1. Secret pattern scanning (regex-based)
2. File allowlist (only permitted paths/extensions)
3. Content size limit
4. Consent gate (policy-based: block/redact/require_allowlist)
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

# v14 D-4: Consent policy (env-configurable)
# "block" = block on any finding, "redact" = redact and continue (default),
# "require_allowlist" = require explicit source_files or block
_VALID_POLICIES = {"block", "redact", "require_allowlist"}


def _get_consent_policy() -> str:
    """
    v16 F-4: Resolve consent policy per-call (not at import time).
    Validates against known values, warns on typo.
    """
    raw = os.environ.get("ORCHESTRA_CONSENT_POLICY", "redact")
    if raw in _VALID_POLICIES:
        return raw
    _audit_log("invalid_policy", f"Unknown ORCHESTRA_CONSENT_POLICY='{raw}', defaulting to 'redact'")
    return "redact"


# v14 D-1/D-2: Directories allowed for external agent context (dynamically expandable)
def _build_allowed_dirs() -> list[Path]:
    """Build allowed base directories from defaults + env vars."""
    from path_utils import normalize_path  # v19 L-1: normalize all paths
    dirs = [Path.home() / ".claude"]
    # Add project dir if set
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if project_dir:
        dirs.append(Path(normalize_path(project_dir)))
    # Add extra dirs from ORCHESTRA_ALLOWED_DIRS (comma-separated)
    extra = os.environ.get("ORCHESTRA_ALLOWED_DIRS", "")
    if extra:
        for d in extra.split(","):
            d = d.strip()
            if d:
                dirs.append(Path(normalize_path(d)))
    # v15 E-2: cwd() no longer auto-added (was overly permissive)
    # v16 F-3: Warn if no project dir is configured
    if not project_dir and not extra:
        _audit_log("no_project_dir",
                   "Neither CLAUDE_PROJECT_DIR nor ORCHESTRA_ALLOWED_DIRS is set. "
                   "Project files will be blocked by context guard. "
                   "Set CLAUDE_PROJECT_DIR in bootstrap.py or environment.")
    return dirs


# v17 G-1: REMOVED module-level _ALLOWED_BASE_DIRS = _build_allowed_dirs()
# Directories are now resolved per-call in enforce_allowed_dirs() and guard_context().


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
    v13 C-1, v17 G-1: Enforce that all source files are under allowed base directories.
    v17: Directories resolved per-call (not cached at import time).
    v19 L-1: Normalize source_files paths before resolution.

    Args:
        source_files: List of file paths to validate

    Returns:
        List of files that are NOT under allowed directories (violations)
    """
    from path_utils import normalize_path  # v19 L-1
    allowed_dirs = _build_allowed_dirs()  # v17 G-1: per-call resolution
    violations = []
    for f in source_files:
        resolved = Path(normalize_path(f)).resolve()  # v19 L-1: normalize before resolve
        if not any(
            _is_relative_to(resolved, base.resolve())
            for base in allowed_dirs
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

    v14 redesign:
    1. Enforce size limit FIRST (D-6: performance)
    2. Policy check for unknown origin (D-1: source_files=None handling)
    3. Enforce allowed base directories
    4. Check file allowlist (blocked extensions/patterns)
    5. Scan for secrets
    6. Apply consent policy (D-4: block/redact/require_allowlist)

    Args:
        content: The content to be sent to external agent
        source_files: List of source file paths for provenance tracking.
            - list with paths: Files are validated against allowlist/blocklist.
            - None: Unknown origin. Consent policy determines behavior.
            - [] (empty list): Treated same as None (v16 F-1, v17 G-4).
              Both None and [] mean "origin unknown" — there is no semantic
              difference between "not provided" and "explicitly empty".

    Returns:
        Sanitized content safe for transmission

    Raises:
        ContextGuardError: If content is blocked by policy
    """
    # Step 1: Size limit FIRST (v14 D-6: truncate before expensive scan)
    truncated = False
    if len(content) > MAX_CONTEXT_SIZE:
        content = content[:MAX_CONTEXT_SIZE] + "\n\n[TRUNCATED: content exceeded size limit]"
        truncated = True

    # Step 2: Unknown origin policy (v14 D-1, v16 F-1, v17 H-1: strict origin)
    policy = _get_consent_policy()  # v16 F-4: resolve per-call
    if not source_files:  # None or empty list
        if policy == "require_allowlist":
            _audit_log("blocked_unknown_origin", "source_files not provided, policy=require_allowlist")
            raise ContextGuardError(
                "source_files is required when ORCHESTRA_CONSENT_POLICY=require_allowlist. "
                "Provide explicit file paths for content being sent to external agents."
            )
        # v17 H-1: Strict origin mode — block unknown origin even under redact
        strict_origin = os.environ.get("ORCHESTRA_STRICT_ORIGIN", "0") == "1"
        if strict_origin:
            _audit_log("blocked_strict_origin",
                       f"source_files not provided, ORCHESTRA_STRICT_ORIGIN=1, policy={policy}")
            raise ContextGuardError(
                "ORCHESTRA_STRICT_ORIGIN is enabled. source_files must be provided "
                "for all content sent to external agents."
            )
        # For "block" and "redact" policies without strict mode, proceed with content-only scanning
        _audit_log("unknown_origin", f"No source_files provided, policy={policy}")

    # Step 3: Enforce allowed base directories (v13 C-1, v16 F-1, v17 G-1: per-call)
    if source_files is not None and len(source_files) > 0:
        dir_violations = enforce_allowed_dirs(source_files)
        if dir_violations:
            allowed_dirs = _build_allowed_dirs()  # v17 G-1: for error message
            _audit_log("blocked_directory", f"Files outside allowed dirs: {dir_violations}")
            raise ContextGuardError(
                f"Files outside allowed directories: {', '.join(dir_violations)}. "
                f"Only files under {[str(d) for d in allowed_dirs]} are permitted."
            )

    # Step 4: File allowlist check (blocked extensions/patterns, v16 F-1)
    if source_files is not None and len(source_files) > 0:
        blocked = [f for f in source_files if not check_file_allowed(f)]
        if blocked:
            _audit_log("blocked_files", f"Blocked by pattern: {blocked}")
            raise ContextGuardError(
                f"Blocked files detected: {', '.join(blocked)}. "
                "These files may contain secrets and cannot be sent to external agents."
            )

    # Step 5: Scan for secrets
    findings = scan_secrets(content)

    # Step 6: Apply consent policy (v14 D-4)
    if findings:
        _audit_log("secrets_found", f"{len(findings)} secrets detected, policy={policy}")
        if policy == "block":
            raise ContextGuardError(
                f"{len(findings)} potential secrets detected. "
                "Policy is 'block': transmission blocked. Review content manually."
            )
        # "redact" (default) or "require_allowlist": redact and continue
        content = redact_secrets(content)

    return content


def _guard_context_report_internal(content: str, source_files: list[str] = None) -> dict:
    """
    v15 E-5: Internal diagnostics only. NOT for outbound content.
    Renamed from guard_context_report() to prevent misuse for external transmission.

    Returns a report without enforcing policies (for debugging/logging).

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

## File: resilience.py

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

    v17 I-3: original_task is now redacted before inclusion to prevent
    secret leakage in fallback responses.

    Args:
        agent_name: Name of the failed agent (codex, gemini)
        original_task: The task that was being delegated
        error_info: Error details from the failed call

    Returns:
        Fallback response dict for orchestrator handling
    """
    # v17 I-3: Redact potential secrets from original_task before including in fallback
    try:
        from context_guard import redact_secrets
        safe_task = redact_secrets(original_task[:200])
    except Exception:
        safe_task = original_task[:50] + "..." if len(original_task) > 50 else original_task

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
        "original_task": safe_task,  # v17 I-3: redacted for safety
    }
```

## File: output_schemas.py

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
            "confidence": 1,  # v14 D-5: minimum valid value (1-10 range)
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

## File: env_check.py

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
```

## File: budget.py

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
    v13 C-4, v17 G-2: OS-level file lock for inter-process safety.
    v17: Windows uses LK_LOCK (blocking) instead of LK_NBLCK (non-blocking).
    v18 I-6: Lock 1024 bytes instead of 1 byte to avoid Windows locking issues.
    """
    import sys
    if sys.platform == "win32":
        import msvcrt
        # v17 G-2: LK_LOCK blocks until lock is available (was LK_NBLCK)
        # v18 I-6: Lock 1024 bytes (not 1) to work around Windows file locking quirks
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK if exclusive else msvcrt.LK_UNLCK, 1024)
    else:
        import fcntl
        fcntl.flock(f.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_UN)


def _file_unlock(f) -> None:
    """v13 C-4: Release file lock."""
    import sys
    if sys.platform == "win32":
        import msvcrt
        try:
            # Seek to start before unlocking (I-6 workaround)
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1024)
        except Exception:
            pass
    else:
        import fcntl
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


# v15 E-3: _load_state() and _save_state() REMOVED.
# All operations now use _load_state_locked()/_save_state_locked() for atomic access.


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
    v14 D-3: Uses file-locked atomic read.
    v17 H-3: Returns permissive fallback on lock/I/O failure (best-effort).

    Args:
        estimated_tokens: Estimated token usage for the planned call

    Returns:
        {"allowed": bool, "remaining": int, "used": int, "limit": int}
    """
    with _lock:
        fh = None  # v18 M-6: Initialize before try
        try:
            state, fh = _load_state_locked()
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
        except Exception:
            # v17 H-3: Best-effort — allow the call if budget check itself fails
            return {
                "allowed": True,
                "remaining": DEFAULT_TOKEN_BUDGET,
                "used": 0,
                "limit": DEFAULT_TOKEN_BUDGET,
                "active_calls": 0,
                "max_concurrent": DEFAULT_MAX_CONCURRENT,
                "fallback": True,
            }
        finally:
            if fh is not None:
                try:
                    _file_unlock(fh)
                    fh.close()
                except Exception:
                    pass


def record_call(agent: str, tokens_used: int, duration_ms: int = 0) -> None:
    """
    Record a completed agent call (token usage only).
    v16 F-2: No longer decrements active_calls (only release_slot does that).
    v14 D-3: Atomic read-modify-write with file lock.
    """
    with _lock:
        fh = None  # v18 M-6: Initialize before try
        try:
            state, fh = _load_state_locked()
            state["total_tokens"] += tokens_used
            state["calls"].append({
                "agent": agent,
                "tokens": tokens_used,
                "duration_ms": duration_ms,
                "timestamp": time.time(),
            })
            # v16 F-2: active_calls decrement REMOVED (release_slot() handles it)
            _save_state_locked(state, fh)
        except Exception:
            if fh is not None:
                try:
                    _file_unlock(fh)
                    fh.close()
                except Exception:
                    pass


def acquire_slot(agent: str) -> bool:
    """
    Try to acquire a concurrency slot for an agent call.
    v14 D-3: Atomic read-modify-write with file lock.

    Returns True if slot acquired, False if limit reached.
    """
    with _lock:
        fh = None  # v18 M-6: Initialize before try
        try:
            state, fh = _load_state_locked()
            if state["active_calls"] >= state["max_concurrent"]:
                _file_unlock(fh)
                fh.close()
                return False
            state["active_calls"] += 1
            _save_state_locked(state, fh)
            return True
        except Exception:
            if fh is not None:
                try:
                    _file_unlock(fh)
                    fh.close()
                except Exception:
                    pass
            return False


def release_slot() -> None:
    """
    Release a concurrency slot after agent call completes.
    v14 D-3: Atomic read-modify-write with file lock.
    """
    with _lock:
        fh = None  # v18 M-6: Initialize before try
        try:
            state, fh = _load_state_locked()
            state["active_calls"] = max(0, state["active_calls"] - 1)
            _save_state_locked(state, fh)
        except Exception:
            if fh is not None:
                try:
                    _file_unlock(fh)
                    fh.close()
                except Exception:
                    pass


def reset_session() -> None:
    """Reset budget state for a new session. v15 E-3: uses file lock."""
    with _lock:
        fh = None  # v18 M-6: Initialize before try
        try:
            state, fh = _load_state_locked()
            state.update({
                "total_tokens": 0,
                "calls": [],
                "active_calls": 0,
                "budget_limit": DEFAULT_TOKEN_BUDGET,
                "max_concurrent": DEFAULT_MAX_CONCURRENT,
            })
            _save_state_locked(state, fh)
        except Exception:
            if fh is not None:
                try:
                    _file_unlock(fh)
                    fh.close()
                except Exception:
                    pass


def get_summary() -> dict:
    """Get session budget summary. v15 E-3: uses file lock."""
    with _lock:
        fh = None  # v18 M-6: Initialize before try
        try:
            state, fh = _load_state_locked()
            result = {
                "total_tokens": state["total_tokens"],
                "total_calls": len(state["calls"]),
                "remaining_tokens": state["budget_limit"] - state["total_tokens"],
                "budget_limit": state["budget_limit"],
                "by_agent": _summarize_by_agent(state["calls"]),
            }
            _file_unlock(fh)
            fh.close()
            return result
        except Exception:
            if fh is not None:
                try:
                    _file_unlock(fh)
                    fh.close()
                except Exception:
                    pass
            return {"total_tokens": 0, "total_calls": 0, "remaining_tokens": DEFAULT_TOKEN_BUDGET,
                    "budget_limit": DEFAULT_TOKEN_BUDGET, "by_agent": {}}


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

## File: codex_wrapper.py

```python
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
    node_path = find_node()
    codex_js_path = find_codex_js()
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

            subprocess.run(
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
                timeout=timeout,
                shell=False,
                encoding="utf-8",
            )

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
```

## File: gemini_wrapper.py

```python
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
```

## File: vault_sync.py

```python
"""
TetsuyaSynapse (Obsidian Vault) unified sync helper.

v10 base with v12 B-2 fix (VAULT_ROOT.exists() not VAULT_BASE.exists()).

Replaces and consolidates:
- Previous vault_sync.py (v6-v9): structured save methods
- Previous sync_vault.py (pipeline CLI tool): pending sync management

Provides a unified interface for saving Orchestra outputs to the vault.

Vault structure:
  {VAULT_ROOT}/90-Claude/
  +-- sessions/          <- checkpointing saves here
  +-- decisions/         <- Codex review results save here
  +-- learnings/         <- Gemini research results save here
  +-- pipeline/tasks/    <- pipeline task outputs save here

Fallback: ~/.claude/obsidian-sessions/ when vault is unavailable
Pending sync: ~/.claude/obsidian-sessions/pending_sync.txt tracks failed vault writes

Environment variables:
  VAULT_PATH: Override vault root path (default: G:/My Drive/obsidian/TetsuyaSynapse)

Design principles:
- Best-effort: vault save failures never block the main flow
- Dual-write: always save to local cache, optionally to vault
- Pending sync: failed vault writes are tracked and retried via sync_pending()
- Safe filenames: all Windows-forbidden characters sanitized
"""
import json
import logging
import os
import re
import shutil
import unicodedata
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path


# Vault paths (env var override for portability)
_DEFAULT_VAULT = Path("G:/My Drive/obsidian/TetsuyaSynapse")
VAULT_ROOT = Path(os.environ.get("VAULT_PATH", str(_DEFAULT_VAULT)))
VAULT_BASE = VAULT_ROOT / "90-Claude"
LOCAL_CACHE = Path.home() / ".claude" / "obsidian-sessions"
LOG_DIR = Path.home() / ".claude" / "logs"
PENDING_FILE = LOCAL_CACHE / "pending_sync.txt"

# Subdir mapping (carried from sync_vault.py)
TYPE_PATHS = {
    "sessions": "sessions",
    "decisions": "decisions",
    "learnings": "learnings",
    "pipeline": "pipeline/tasks",
}

# Windows reserved filenames
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}

# Logger setup
_logger = None


def _get_logger() -> logging.Logger:
    """Get or create a logger that writes to ~/.claude/logs/vault_sync.log"""
    global _logger
    if _logger is None:
        _logger = logging.getLogger("vault_sync")
        _logger.setLevel(logging.INFO)
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(
                LOG_DIR / "vault_sync.log",
                maxBytes=1_000_000,  # 1MB
                backupCount=3,
                encoding="utf-8",
            )
            handler.setFormatter(
                logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
            )
            _logger.addHandler(handler)
        except Exception:
            pass  # If logging setup fails, logger will just not output
    return _logger


def _vault_available() -> bool:
    """
    Check if the Obsidian vault (Google Drive) is accessible.
    v12 B-2 fix: Check VAULT_ROOT.exists() (not VAULT_BASE.exists()) to avoid
    chicken-egg problem on first run.
    """
    try:
        return VAULT_ROOT.exists()
    except OSError:
        return False


def _ensure_dir(path: Path) -> Path:
    """Create directory if it does not exist."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def _sanitize_filename(name: str) -> str:
    """
    Sanitize a string for use as a Windows filename.

    v7 improvements over v6:
    - Unicode NFKC normalization (e.g. fullwidth chars -> ASCII)
    - ASCII control character removal (0x00-0x1F)

    Full steps:
    1. Unicode NFKC normalization
    2. Remove ASCII control characters (0x00-0x1F)
    3. Remove characters forbidden on Windows: < > : " / \\ | ? *
    4. Replace whitespace with hyphens
    5. Remove leading/trailing dots and spaces
    6. Lowercase
    7. Cap length at 80 characters
    8. Check against Windows reserved names (CON, PRN, AUX, NUL, COM1-9, LPT1-9)
    9. Fallback to 'untitled' if result is empty
    """
    # Step 1: Unicode normalization
    sanitized = unicodedata.normalize("NFKC", name)
    # Step 2: Remove ASCII control characters
    sanitized = re.sub(r"[\x00-\x1f]", "", sanitized)
    # Step 3: Remove forbidden characters
    sanitized = re.sub(r'[<>:"/\\|?*]', "", sanitized)
    # Step 4: Replace whitespace with hyphens
    sanitized = re.sub(r"\s+", "-", sanitized)
    # Step 5: Remove leading/trailing dots and spaces
    sanitized = sanitized.strip(". ")
    # Step 6: Lowercase
    sanitized = sanitized.lower()
    # Step 7: Cap length
    sanitized = sanitized[:80]
    # Step 8: Check reserved names
    name_without_ext = sanitized.split(".")[0].upper()
    if name_without_ext in _WINDOWS_RESERVED:
        sanitized = f"_{sanitized}"
    # Step 9: Fallback
    if not sanitized:
        sanitized = "untitled"
    return sanitized


def _generate_filename(title: str, suffix: str = "") -> str:
    """
    Generate a dated filename: YYYY-MM-DD_HHMMSS_xxxx_slug_suffix.md

    v8 fix: Include HHMMSS to prevent same-day same-title overwrites.
    v9 fix: Append 4-char hex from uuid4 for sub-second uniqueness.
    """
    import uuid
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M%S")
    uid = uuid.uuid4().hex[:4]
    slug = _sanitize_filename(title)
    if suffix:
        return f"{date_str}_{time_str}_{uid}_{slug}_{suffix}.md"
    return f"{date_str}_{time_str}_{uid}_{slug}.md"


def _write_with_fallback(subdir: str, filename: str, content: str) -> str:
    """
    Write to local cache AND vault. Either may fail independently.
    ALL write failures are caught and logged. Never raises.

    v8 fix: Vault write is attempted regardless of local write outcome.
    If local fails but vault succeeds, returns vault path.
    If both fail, tries system temp dir as last resort.

    Returns: path where file was saved (prefers vault), or "" on total failure
    """
    logger = _get_logger()
    local_saved = ""
    vault_saved = ""

    # Try local cache
    try:
        local_dir = _ensure_dir(LOCAL_CACHE / subdir)
        local_path = local_dir / filename
        local_path.write_text(content, encoding="utf-8")
        local_saved = str(local_path)
    except Exception as e:
        logger.error(f"Local cache write failed ({e})")

    # Try vault (regardless of local outcome)
    if _vault_available():
        try:
            vault_dir = _ensure_dir(VAULT_BASE / subdir)
            vault_path = vault_dir / filename
            vault_path.write_text(content, encoding="utf-8")
            vault_saved = str(vault_path)
            logger.info(f"Saved to vault: {vault_path}")
        except Exception as e:
            logger.warning(f"Vault write failed ({e})")
            # v12 B-3: Record pending if local save succeeded
            if local_saved:
                _record_pending(subdir, filename)
    else:
        logger.info("Vault unavailable")
        # Track for pending sync
        if local_saved:
            _record_pending(subdir, filename)

    # Return best available path (prefer vault)
    if vault_saved:
        return vault_saved
    if local_saved:
        return local_saved

    # Last resort: system temp dir
    try:
        import tempfile
        fallback_path = Path(tempfile.gettempdir()) / filename
        fallback_path.write_text(content, encoding="utf-8")
        logger.warning(f"Fell back to temp dir: {fallback_path}")
        return str(fallback_path)
    except Exception as e2:
        logger.error(f"All write attempts failed ({e2})")
        return ""


def _record_pending(subdir: str, filename: str) -> None:
    """Record a failed vault write to pending_sync.txt for later retry."""
    try:
        _ensure_dir(LOCAL_CACHE)
        with open(PENDING_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()}|{subdir}|{filename}\n")
    except Exception:
        pass  # Best-effort


def sync_pending() -> list[str]:
    """
    Retry syncing files that failed vault write.
    Migrated from sync_vault.py.

    Returns: list of successfully synced filenames
    """
    logger = _get_logger()
    if not PENDING_FILE.exists():
        return []

    if not _vault_available():
        logger.info("Vault still unavailable, skipping pending sync")
        return []

    synced = []
    remaining = []

    with open(PENDING_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines:
        parts = line.strip().split("|")
        if len(parts) != 3:
            continue

        timestamp, subdir, filename = parts
        source = LOCAL_CACHE / subdir / filename

        if not source.exists():
            logger.warning(f"Pending source not found: {source}")
            continue

        try:
            vault_dir = _ensure_dir(VAULT_BASE / subdir)
            target = vault_dir / filename
            shutil.copy2(source, target)
            logger.info(f"Pending synced: {filename}")
            synced.append(filename)
        except Exception as e:
            logger.warning(f"Pending sync failed for {filename}: {e}")
            remaining.append(line)

    # Update pending file
    if remaining:
        with open(PENDING_FILE, "w", encoding="utf-8") as f:
            f.writelines(remaining)
    else:
        try:
            PENDING_FILE.unlink()
        except Exception:
            pass

    return synced


def _build_frontmatter(meta: dict) -> str:
    """
    Build YAML frontmatter string with properly quoted values.
    All scalar values are double-quoted to prevent YAML parsing issues
    with special characters like colons, brackets, etc.

    v8 fix: Escape backslashes before quotes. YAML double-quoted scalars
    treat backslash as escape character, so Windows paths like
    C:\\Users\\... would be misinterpreted as C:Users... without escaping.
    """
    lines = ["---"]
    for key, value in meta.items():
        if isinstance(value, list):
            quoted_items = ", ".join(
                f'"{_yaml_escape(str(item))}"' for item in value
            )
            lines.append(f"{key}: [{quoted_items}]")
        elif isinstance(value, bool):
            lines.append(f"{key}: {str(value).lower()}")
        else:
            escaped = _yaml_escape(str(value))
            lines.append(f'{key}: "{escaped}"')
    lines.append("---")
    return "\n".join(lines)


def _yaml_escape(s: str) -> str:
    """
    Escape a string for use inside YAML double-quoted scalars.
    Order matters: backslashes first, then quotes.
    """
    s = s.replace("\\", "\\\\")
    s = s.replace('"', '\\"')
    return s


def save_checkpoint(title: str, summary: str, context: dict) -> str:
    """
    Save a session checkpoint to TetsuyaSynapse.

    Args:
        title: Checkpoint title
        summary: Session summary text
        context: Additional context (current tasks, decisions, etc.)

    Returns: path where file was saved
    """
    now = datetime.now()
    frontmatter = _build_frontmatter({
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "type": "checkpoint",
        "title": title,
        "source": "orchestra-checkpointing",
        "tags": ["auto-generated", "checkpoint", "orchestra"],
    })
    body = f"{frontmatter}\n\n# {title}\n\n## Summary\n\n{summary}\n"
    if context:
        body += f"\n## Context\n\n```json\n{json.dumps(context, ensure_ascii=False, indent=2)}\n```\n"
    filename = _generate_filename(title, "checkpoint")
    return _write_with_fallback("sessions", filename, body)


def save_codex_review(title: str, review_result: dict, plan_context: str = "") -> str:
    """
    Save a Codex review result to TetsuyaSynapse decisions/.

    Args:
        title: Review title (e.g. "Orchestra Plan v5 Review")
        review_result: JSON result from Codex (approved, issues, summary, etc.)
        plan_context: Original plan/code that was reviewed

    Returns: path where file was saved
    """
    now = datetime.now()
    approved = review_result.get("approved", False)
    confidence = review_result.get("confidence", "N/A")
    issues = review_result.get("issues", [])
    summary = review_result.get("summary", "No summary")

    frontmatter = _build_frontmatter({
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "type": "codex-review",
        "title": title,
        "approved": str(approved).lower(),
        "confidence": str(confidence),
        "source": "orchestra-codex-system",
        "tags": ["auto-generated", "codex-review", "orchestra"],
    })

    body = f"{frontmatter}\n\n# {title}\n\n"
    body += f"**Approved**: {approved}\n"
    body += f"**Confidence**: {confidence}/10\n"
    body += f"**Summary**: {summary}\n\n"

    if issues:
        body += "## Issues\n\n"
        for issue in issues:
            severity = issue.get("severity", "unknown")
            desc = issue.get("description", "")
            suggestion = issue.get("suggestion", "")
            body += f"### [{severity.upper()}] {desc}\n\n"
            if suggestion:
                body += f"**Suggestion**: {suggestion}\n\n"

    if plan_context:
        body += f"## Reviewed Content\n\n```\n{plan_context[:2000]}\n```\n"

    body += f"\n## Raw Result\n\n```json\n{json.dumps(review_result, ensure_ascii=False, indent=2)}\n```\n"

    filename = _generate_filename(title, "review")
    return _write_with_fallback("decisions", filename, body)


def save_gemini_research(title: str, query: str, result: str, sources: list = None) -> str:
    """
    Save a Gemini research result to TetsuyaSynapse learnings/.

    Args:
        title: Research title
        query: Original research query
        result: Research result text
        sources: List of source URLs

    Returns: path where file was saved
    """
    now = datetime.now()
    frontmatter = _build_frontmatter({
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "type": "gemini-research",
        "title": title,
        "source": "orchestra-gemini-system",
        "tags": ["auto-generated", "gemini-research", "orchestra"],
    })

    body = f"{frontmatter}\n\n# {title}\n\n"
    body += f"## Query\n\n{query}\n\n"
    body += f"## Result\n\n{result}\n\n"

    if sources:
        body += "## Sources\n\n"
        for src in sources:
            body += f"- {src}\n"

    filename = _generate_filename(title, "research")
    return _write_with_fallback("learnings", filename, body)


def record_review_issues(
    project_dir: str, review_title: str, issues: list[dict]
) -> None:
    """
    Record Codex review issues into Self-Improvement Loop files.

    Converts Codex review issues (severity: critical/high/medium/low)
    to SIL mistakes.md entries. Creates rules for moderate+ severity.

    Args:
        project_dir: Project root path (where notes/ directory lives)
        review_title: Title of the review (e.g. "Orchestra Plan v9 Review")
        issues: List of issue dicts from Codex (severity, description, suggestion)
    """
    if not issues:
        return

    logger = _get_logger()
    notes_dir = Path(project_dir) / "notes"

    try:
        notes_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"Cannot create notes dir ({e})")
        return

    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    date_full = now.strftime("%Y-%m-%d %H:%M")

    # Severity mapping: Codex -> SIL
    severity_map = {
        "critical": "major",
        "high": "major",
        "medium": "moderate",
        "low": "minor",
    }

    mistakes_file = notes_dir / "mistakes.md"
    rules_file = notes_dir / "rules-local.md"

    # Count existing entries for ID numbering
    existing_count = 0
    if mistakes_file.exists():
        existing_count = mistakes_file.read_text(encoding="utf-8").count("## [M-")

    new_mistakes = []
    new_rules = []

    for i, issue in enumerate(issues):
        codex_severity = issue.get("severity", "low")
        sil_severity = severity_map.get(codex_severity, "minor")

        # Skip minor (low) issues - only record moderate+
        if sil_severity == "minor":
            continue

        entry_num = existing_count + len(new_mistakes) + 1
        m_id = f"M-{date_str}-{entry_num:03d}"
        desc = issue.get("description", "")
        suggestion = issue.get("suggestion", "")

        mistake_entry = f"""
## [{m_id}] {date_full} - Codex: {desc[:60]}
- **Category**: syntax
- **Severity**: {sil_severity}
- **Context**: {review_title}
- **What happened**: Codex review flagged: {desc}
- **Root cause**: Detected by automated Codex review
- **Corrective action**: {suggestion if suggestion else 'See Codex suggestion'}
- **Status**: ruled
- **Rule created**: RL-{date_str}-{entry_num:03d}
"""
        new_mistakes.append(mistake_entry)

        # Create rule for moderate+ (immediate rule per SIL policy)
        rule_entry = f"""
## RL-{date_str}-{entry_num:03d}: {desc[:60]}
- **Derived from**: {m_id}
- **Category**: syntax
- **When**: {review_title} related code changes
- **Action**: {suggestion if suggestion else desc}
- **Added**: {now.strftime('%Y-%m-%d')}
"""
        new_rules.append(rule_entry)

    # Append to files (best-effort)
    try:
        if new_mistakes:
            with open(mistakes_file, "a", encoding="utf-8") as f:
                f.writelines(new_mistakes)
        if new_rules:
            with open(rules_file, "a", encoding="utf-8") as f:
                f.writelines(new_rules)
        logger.info(
            f"SIL recorded: {len(new_mistakes)} mistakes, {len(new_rules)} rules"
        )
    except Exception as e:
        logger.warning(f"SIL write failed ({e})")
```

---

## Implementation Checklist

1. Create `~/.claude/lib/` directory
2. Copy each file section above into the corresponding .py file
3. Verify all imports are resolvable (no circular dependencies)
4. Test bootstrap.py separately (should set CLAUDE_PROJECT_DIR)
5. Test context_guard.py separately (should build allowed dirs per-call)
6. Test budget.py file locking (Windows LK_LOCK, 1024 bytes)
7. Test codex_wrapper.call_codex_safe() with a simple query
8. Test gemini_wrapper.call_gemini_safe() (graceful skip if not installed)
9. Test vault_sync.save_checkpoint() (should fall back to local cache if vault unavailable)

---

## Security Notes

All files follow the security policy:
- No `shell=True` (except one-time `npm root -g` in cli_finder.py with no user input)
- All subprocess calls use `shell=False` + argument arrays
- No secrets in logs (context_guard redacts before transmission)
- File locking for inter-process safety (budget.py)
- Directory allowlist enforced (context_guard.py)
- Input via stdin or temp files (never CLI arguments)

---

## End of Plan v18 Library Code
