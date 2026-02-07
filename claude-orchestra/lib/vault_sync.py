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
