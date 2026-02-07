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
    # Generic private keys (v20 Phase1-H1: match entire BEGIN...END block, not just header)
    re.compile(r'-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----', re.DOTALL),
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
    re.compile(r'\.env(\.\w+)*$'),  # P4-1: match .env.production.local etc.
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
        # CM-2 fix: Default to "1" (fail closed) when env var is unset
        strict_origin = os.environ.get("ORCHESTRA_STRICT_ORIGIN", "1") == "1"
        if strict_origin:
            _audit_log("blocked_strict_origin",
                       f"source_files not provided, ORCHESTRA_STRICT_ORIGIN=1, policy={policy}")
            raise ContextGuardError(
                "ORCHESTRA_STRICT_ORIGIN is enabled. source_files must be provided "
                "for all content sent to external agents."
            )
        # v20 Phase1-M1: Under default "redact" policy with unknown origin,
        # still scan content for secrets (Step 5/6 below handle this).
        # Log warning that allowlist/blocked-file checks are skipped.
        _audit_log("unknown_origin",
                   f"No source_files provided, policy={policy}. "
                   "File allowlist/blocklist checks skipped. "
                   "Set ORCHESTRA_CONSENT_POLICY=require_allowlist or provide source_files.")

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
