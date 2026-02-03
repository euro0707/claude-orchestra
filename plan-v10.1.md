---
type: verify
timestamp: 2026-02-04 08:00:00
review_request: true
version: 10.1
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
---

# Claude Code Orchestra Integration Plan v10.1

## Overview

Upgrade the existing Claude Code + Codex 2-agent system to a Claude Code + Codex + Gemini 3-agent system using the Orchestra framework.

## Decisions Made

- Hooks: Replace with Orchestra hooks (remove permission_translator, keep session_parser)
- Gemini CLI: Integrate (3-agent system)
- Rules: All 7 rules
- Skills: All 12 skills
- Agents: general-purpose.md
- TetsuyaSynapse: Integrate Orchestra outputs (checkpointing, Codex reviews, Gemini research) with existing vault sync

## Environment

- OS: Windows 11
- Shell: Git Bash (MSYS2) inside Claude Code, PowerShell/CMD for normal terminal
- Python 3.13 (Windows native)
  - Absolute path: `C:\Users\skyeu\AppData\Local\Programs\Python\Python313\python.exe`
- Node.js: npm global packages at `C:\Users\skyeu\AppData\Roaming\npm\`
- Codex CLI v0.92.0
  - codex.cmd: `C:\Users\skyeu\AppData\Roaming\npm\codex.cmd`
  - Node entry point: `C:\Users\skyeu\AppData\Roaming\npm\node_modules\@openai\codex\bin\codex.js`
- Existing .claude/ structure: commands/, scripts/ with existing skills/scripts
- TetsuyaSynapse Vault: `G:\My Drive\obsidian\TetsuyaSynapse`
  - Existing sync: claude_session_parser.py (Stop hook), sync_vault.py, watch_session.py, sync-sessions.ps1
  - Vault structure: `90-Claude/{sessions,decisions,learnings,pipeline/tasks}/`
  - Local cache fallback: `~/.claude/obsidian-sessions/`
  - Known issue: Google Drive path encoding (Japanese chars) in PowerShell

---

## Review History

### v2 Review (6 medium) -> v3 Changes

| # | v2 Issue | v3 Fix |
|---|---------|--------|
| 1 | codex_wrapper.py in hooks/lib/ unreachable from call_codex.py | Moved shared lib to `~/.claude/lib/` |
| 2 | shell=True command injection risk | `shutil.which()` + `shell=False` policy |
| 3 | commands/ vs skills/ name collision | `sc:` prefix naming convention |
| 4 | Hook execution order not guaranteed | Orchestrator scripts |
| 5 | Arbitrary Python execution security risk | stdin-based input, shell=True eliminated |
| 6 | cmd.exe /c does not solve non-TTY issue | `--json` + stdout parsing as fallback |

### v3 Review (1 high, 2 medium, 2 low) -> v4 Changes

| # | Severity | v3 Issue | v4 Fix |
|---|----------|---------|--------|
| 1 | high | shutil.which returns codex.cmd; shell=False cannot run .cmd (WinError 193) | Execute codex.js directly via node |
| 2 | medium | codex exec stdin (-) support unverified | Temp file as primary method |
| 3 | medium | Non-TTY fallback stages unverified; CREATE_NEW_CONSOLE incompatible with capture_output | Concrete verification steps and fallback criteria |
| 4 | low | sys.path.insert might be forgotten in scripts | bootstrap.py introduced |
| 5 | low | sc: prefix is convention only | agent-router.py validation |

### v4 Review (2 medium, 1 low) -> v5 Changes

| # | Severity | v4 Issue | v5 Fix |
|---|----------|---------|--------|
| 1 | medium | CODEX_JS path hardcoded to default npm prefix; breaks with nvm/custom prefix | Dynamic resolution via `npm root -g` + env var `CODEX_JS` override |
| 2 | medium | codex_wrapper.py snippet has `finally` indentation error and syntax issues | Complete rewrite with verified syntax |
| 3 | low | plan.md has encoding issues (mojibake) | Rewritten in ASCII-safe format with clear section headers |

### v5 Review (1 high, 2 medium, 1 low) -> v6 Changes

| # | Severity | v5 Issue | v6 Fix |
|---|----------|---------|--------|
| 1 | high | `_generate_filename()` does not sanitize Windows-invalid characters (`:`, `<>`, `"`, `/`, `\`, `\|`, `?`, `*`). Titles like "Plan: [name]" will fail | Added `_sanitize_filename()` with full Windows forbidden char removal, reserved name check, length cap |
| 2 | medium | `_write_with_fallback()` vault write can raise exception, contradicting best-effort policy | Wrapped vault write in try/except, always returns local cache path on failure, logs error to `~/.claude/logs/` |
| 3 | medium | `codex_wrapper.call_codex()` passes prompt as CLI argument, violating security policy and risking Windows 8191-char command-line limit | Stage 1 now uses temp file for prompt (not CLI args). All stages pass prompt via file, not command line |
| 4 | low | `codex_wrapper.py` `finally` block appears truncated in plan text | Full complete code shown in v6 with explicit finally blocks |

### v6 Review (2 medium, 2 low) -> v7 Changes

| # | Severity | v6 Issue | v7 Fix |
|---|----------|---------|--------|
| 1 | medium | Stage 2 fallback example still passes prompt as CLI argument, contradicting v6 policy | Stage 2 code updated to use stdin via `-` (consistent with Stage 1). No stage uses CLI args for prompt. |
| 2 | medium | Local cache write failure (disk full, permissions) can raise and block hooks | Local cache write wrapped in try/except. Returns empty string on total failure. Error logged. |
| 3 | low | `_build_frontmatter()` emits unquoted YAML scalars. Titles with `:` or special chars break parsing | All scalar values wrapped in double quotes in frontmatter output |
| 4 | low | `_sanitize_filename()` missing ASCII control char removal and Unicode normalization | Added `unicodedata.normalize("NFKC", ...)` and control char strip (0x00-0x1F) |

### v7 Review (3 medium, 1 low) -> v8 Changes

| # | Severity | v7 Issue | v8 Fix |
|---|----------|---------|--------|
| 1 | medium | Step 0 Test 2 still passes prompt as CLI argument (`"What is 1+1?"`) which contradicts the no-CLI-arg-prompt policy | Test 2 rewritten to pass prompt via stdin (`input=` parameter + `-` flag), consistent with all other stages |
| 2 | medium | `_write_with_fallback()` returns `""` after local+temp failures without attempting vault write, even if vault is available | Restructured: vault write attempted regardless of local outcome. If vault succeeds but local failed, vault path returned. |
| 3 | low | `_build_frontmatter()` escapes quotes but not backslashes; YAML double-quoted scalars treat `\` as escape, breaking Windows paths | Added backslash escaping (`\\` -> `\\\\`) before quote escaping. Applied to list items too. |
| 4 | medium | `_generate_filename()` uses date+slug only; repeated saves with same title on same day overwrite prior files | Added `HHMMSS` time component to filename: `YYYY-MM-DD_HHMMSS_slug_suffix.md` |

### v8 Review (approved, 2 low) -> v9 Changes

| # | Severity | v8 Issue | v9 Fix |
|---|----------|---------|--------|
| 1 | low | HHMMSS has 1-second granularity; multiple saves in same second (hooks + manual) can still collide | Appended 4-char hex from `uuid4()` after HHMMSS: `YYYY-MM-DD_HHMMSS_a1b2_slug_suffix.md` |
| 2 | low | Test 2 and Test 3 are now identical (both stdin via `-`); Stage 2 behavior (`-o` temp file) is never exercised | Test 3 replaced with `-o` temp file test to validate Stage 2 fallback path |

### v9 Review (approved, 5 medium + 5 low) -> v10 Changes

| # | Severity | v9 Issue | v10 Fix |
|---|----------|---------|---------|
| M-1 | medium | settings.json hook schema mismatch (missing `hooks` sub-array and `type` field) | Corrected to match current schema: `hooks: [{type: "command", command: "..."}]` |
| M-2 | medium | call_codex.py integration scope unclear (review_gate, prompt templates, etc.) | call_codex.py refactored to thin CLI wrapper. review_gate removed, issues routed to SIL via `record_review_issues()` |
| M-3 | medium | sync_vault.py vs vault_sync.py naming confusion and role overlap | Consolidated into vault_sync.py with env var override + pending_sync. sync_vault.py removed |
| M-4 | medium | gemini_wrapper.py completely undefined | Full code added: `find_gemini()`, `call_gemini()`, graceful skip pattern |
| M-5 | medium | 12 skills have no file structure definition | Standard layout defined (`prompt.md` per skill), template example added |
| L-1 | low | manual_fallback leaks prompt fragment in `manual_command` field | Prompt fragment removed, generic command only |
| L-2 | low | Vault path `マイドライブ` vs `My Drive` mismatch | Resolved via `VAULT_PATH` env var override in M-3 |
| L-3 | low | Orchestrator timeout 30s vs Codex timeout 300s mismatch | Per-script `HOOK_TIMEOUTS` dict: lint=30s, Codex-calling scripts=300s |
| L-4 | low | No log rotation for vault_sync.log | Changed to `RotatingFileHandler` (1MB, 3 backups) |
| L-5 | low | permission_translator.py removal not explicitly stated | Added explicit note: removed (redundant with Claude Code native Japanese) |

### v10 Codex Review (not approved, 1 high + 5 medium + 3 low) -> v10.1 Changes

| # | Severity | v10 Issue | v10.1 Fix |
|---|----------|----------|-----------|
| H-1 | high | gemini_wrapper uses `-p` CLI arg, exposing prompt in process list | Changed to stdin via temp file (same policy as codex_wrapper) |
| M-1 | medium | Stage 2 missing CREATE_NEW_CONSOLE | Added `creationflags=subprocess.CREATE_NEW_CONSOLE`, removed capture_output |
| M-2 | medium | `-o` stated unreliable but Stage 2 depends on it | Added note: Stage 2 gated on Test 3 result; skipped if Test 3 fails |
| M-3 | medium | get_prompt_template/parse_json_from_output not in codex_wrapper code | parse_json_from_output added with regex fallback; get_prompt_template stays in call_codex.py (mode-specific) |
| M-4 | medium | No path allowlisting in load_context | Added ALLOWED_BASE check: only reads under ~/.claude/ |
| M-5 | medium | pending_sync only on vault unavailable, not on vault write error | pending_sync now recorded on both vault unavailable AND vault write exception (if local exists) |
| L-1 | low | Step 0 tests hardcode codex.js path | Tests now use resolve_codex_js() matching runtime resolution |
| L-2 | low | sys.argv[2] unguarded in call_codex wrapper | Noted: use argparse with required/optional args (in M-4 path validation section) |
| L-3 | low | agent-router early-return not implemented | Added concrete gate: skip prompts < 10 chars, cache skills dir listing |

---

## Step 0: Codex CLI Windows Compatibility Fix

### Discovered Problems (4)

#### Problem 1: Python subprocess cannot find codex command
- Root cause: Windows Python subprocess cannot resolve `.cmd` wrappers
- Error: `FileNotFoundError: [WinError 2]`
- v5 fix: Execute `codex.js` directly via `node`. Never use `codex.cmd`.

#### Problem 2: `codex exec -o <path>` does not create output file
- Root cause: Likely Codex 0.92.0 Windows bug
- v5 fix: Do not rely on `-o`. Use `--json` + stdout as primary method.

#### Problem 3: codex exec produces no stdout/stderr (non-TTY)
- Root cause: Codex CLI TUI design skips output in non-TTY environments
- v5 fix: Staged fallback with concrete verification (see below)

#### Problem 4: Git Bash (MSYS2) vs Windows CMD path mismatch
- Root cause: `/c/Users/...` vs `C:\Users\...`
- v5 fix: pathlib everywhere, absolute python path in settings.json

### Pre-Implementation Verification (3 tests)

Run these BEFORE any implementation to determine Codex CLI behavior.
Note: Tests use `find_codex_js()` logic (CODEX_JS env var -> default path -> npm root -g)
to match runtime resolution. Hardcoded paths below are for reference only.

```python
# Helper: resolve codex.js path (same logic as codex_wrapper.py)
import os, shutil, subprocess
from pathlib import Path

def resolve_codex_js():
    env = os.environ.get("CODEX_JS")
    if env and Path(env).exists():
        return env
    default = Path.home() / "AppData/Roaming/npm/node_modules/@openai/codex/bin/codex.js"
    if default.exists():
        return str(default)
    npm = shutil.which("npm")
    if npm:
        r = subprocess.run([npm, "root", "-g"], capture_output=True, text=True, shell=True, timeout=10)
        if r.stdout.strip():
            c = Path(r.stdout.strip()) / "@openai/codex/bin/codex.js"
            if c.exists():
                return str(c)
    raise FileNotFoundError("codex.js not found")

node = shutil.which("node")
codex_js = resolve_codex_js()
```

```
Test 1: Does node direct execution work?
> python -c "...resolve_codex_js()...; r=subprocess.run([node, codex_js, '--version'], capture_output=True, text=True); print(r.stdout, r.stderr)"

Test 2: Does codex exec return stdout (prompt via stdin)?
> python -c "...resolve_codex_js()...; r=subprocess.run([node, codex_js, 'exec', '--full-auto', '--json', '-'], input='What is 1+1?', capture_output=True, text=True, timeout=60); print('stdout:', repr(r.stdout[:500])); print('stderr:', repr(r.stderr[:500]))"

Test 3: Does -o temp file output work (Stage 2 validation)?
> python -c "...resolve_codex_js()...; out=os.path.join(tempfile.gettempdir(),'codex_test_out.md'); r=subprocess.run([node, codex_js, 'exec', '--full-auto', '-o', out, '-'], input='What is 1+1?', text=True, timeout=60); exists=os.path.exists(out); size=os.path.getsize(out) if exists else 0; print('file exists:', exists, 'size:', size)"
```

### Staged Fallback for Non-TTY (Problem 3)

| Stage | Method | Success Criteria | Notes |
|-------|--------|-----------------|-------|
| 1 | `node codex.js exec --json --no-alt-screen` + capture_output | stdout is non-empty | Primary method |
| 2 | CREATE_NEW_CONSOLE + temp file output (`-o`) | Temp file exists and non-empty | Do NOT use capture_output (incompatible) |
| 3 | winpty / conpty wrapper | stdout is non-empty | Only if stages 1-2 both fail |
| Final | Manual execution fallback | User runs in separate terminal | Always available |

Stage 2 detail: Since `CREATE_NEW_CONSOLE` and `capture_output=True` are incompatible, results are retrieved via temp file. Prompt is passed via stdin (never CLI args):
```python
# Write prompt to temp file
prompt_file = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
prompt_file.write(prompt)
prompt_file.close()

# Output temp file
output_file = tempfile.NamedTemporaryFile(suffix=".md", delete=False)
output_path = output_file.name
output_file.close()

# Read prompt and pass via stdin using "-"
with open(prompt_file.name, "r", encoding="utf-8") as f:
    prompt_text = f.read()
subprocess.run(
    [node_path, codex_js_path, "exec", "--full-auto", "-o", output_path, "-"],
    input=prompt_text,
    creationflags=subprocess.CREATE_NEW_CONSOLE,
    shell=False,
    encoding="utf-8",
)
result = Path(output_path).read_text(encoding="utf-8")
os.unlink(output_path)
os.unlink(prompt_file.name)
```

---

### Shared Library: ~/.claude/lib/

```
C:\Users\skyeu\.claude\lib\
+-- __init__.py
+-- bootstrap.py        # Common init for all hooks/scripts
+-- codex_wrapper.py    # Codex CLI invocation wrapper
+-- gemini_wrapper.py   # Gemini CLI invocation wrapper
+-- vault_sync.py       # TetsuyaSynapse unified sync (replaces sync_vault.py)
+-- path_utils.py       # Windows/Git Bash path normalization
```

#### vault_sync.py (v10 - unified sync, replaces sync_vault.py)

```python
"""
TetsuyaSynapse (Obsidian Vault) unified sync helper.

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
    """Check if the Obsidian vault (Google Drive) is accessible."""
    try:
        return VAULT_BASE.exists()
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
            # Track for pending sync (only if local copy exists to retry from)
            if local_saved:
                _record_pending(subdir, filename)
    else:
        logger.info("Vault unavailable")
        # Track for pending sync (only if local copy exists to retry from)
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

#### bootstrap.py

```python
"""
Common bootstrap for all hooks/scripts.
Each script adds 2 lines at the top:

    import sys; sys.path.insert(0, str(__import__('pathlib').Path.home() / ".claude" / "lib"))
    import bootstrap  # noqa: F401

After that, direct imports work:
    from codex_wrapper import call_codex
    from path_utils import normalize_path
"""
import sys
from pathlib import Path

_lib_dir = str(Path(__file__).parent)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)
```

#### gemini_wrapper.py (v10 - Gemini CLI integration)

```python
"""
Gemini CLI wrapper for Orchestra integration.

Design:
- Graceful skip when Gemini CLI is not installed
- shell=False strictly enforced
- Prompt via stdin (same policy as codex_wrapper.py)
- Returns structured dict for consistent handling
"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def find_gemini() -> str | None:
    """
    Resolve Gemini CLI executable path.
    Returns None if not installed (graceful skip).
    """
    path = shutil.which("gemini")
    if path:
        return path
    return None


def call_gemini(query: str, timeout: int = 120) -> dict:
    """
    Call Gemini CLI and return results.

    Prompt is passed via stdin to avoid CLI arg length limits.
    If Gemini CLI is not installed, returns graceful skip result.

    Args:
        query: Research query or prompt to send
        timeout: Timeout in seconds (default 120)

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

    try:
        # Prompt via stdin using temp file (same policy as codex_wrapper)
        prompt_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        )
        prompt_file.write(query)
        prompt_file.close()

        try:
            with open(prompt_file.name, "r", encoding="utf-8") as f:
                prompt_text = f.read()
        finally:
            pass  # cleanup below

        result = subprocess.run(
            [gemini_path],
            input=prompt_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            shell=False,
        )

        # Cleanup temp file
        try:
            os.unlink(prompt_file.name)
        except OSError:
            pass
        if result.stdout.strip():
            # Try JSON parse first
            try:
                parsed = json.loads(result.stdout)
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
```

#### codex_wrapper.py (v6 - all prompts via temp file, complete code)

```python
"""
Codex CLI wrapper for Windows environments.

v6 design:
- Execute codex.js directly via node (never use codex.cmd)
- shell=False strictly enforced
- Dynamic codex.js path resolution (CODEX_JS env -> default npm -> npm root -g)
- ALL prompts passed via temp file (never CLI args) to avoid:
  - Windows 8191-char command-line limit
  - Process list exposure of prompt content
  - Shell escaping issues
- --json + stdout parsing as primary output method
- Staged fallback: stdout -> temp file output -> manual execution
"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def find_node() -> str:
    """Resolve node executable path."""
    path = shutil.which("node")
    if path:
        return path
    raise FileNotFoundError("Node.js not found. Install Node.js first.")


def find_codex_js() -> str:
    """
    Resolve codex.js path with multiple strategies.

    Resolution order:
    1. CODEX_JS environment variable (user override)
    2. Default npm global path
    3. Dynamic resolution via `npm root -g`
    """
    # Strategy 1: Environment variable override
    env_path = os.environ.get("CODEX_JS")
    if env_path and Path(env_path).exists():
        return env_path

    # Strategy 2: Default npm global path
    default_path = (
        Path.home()
        / "AppData"
        / "Roaming"
        / "npm"
        / "node_modules"
        / "@openai"
        / "codex"
        / "bin"
        / "codex.js"
    )
    if default_path.exists():
        return str(default_path)

    # Strategy 3: Dynamic resolution via npm root -g
    try:
        npm_path = shutil.which("npm")
        if npm_path:
            result = subprocess.run(
                [npm_path, "root", "-g"],
                capture_output=True,
                text=True,
                timeout=10,
                shell=True,  # npm.cmd requires shell on Windows
                encoding="utf-8",
            )
            if result.stdout.strip():
                candidate = (
                    Path(result.stdout.strip())
                    / "@openai"
                    / "codex"
                    / "bin"
                    / "codex.js"
                )
                if candidate.exists():
                    return str(candidate)
    except Exception:
        pass

    raise FileNotFoundError(
        "Codex CLI not found. Install with: npm install -g @openai/codex\n"
        "Or set CODEX_JS environment variable to the path of codex.js"
    )


def _write_prompt_file(prompt: str) -> str:
    """Write prompt to a temp file and return the path. Caller must delete."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".txt",
        delete=False,
        dir=tempfile.gettempdir(),
        encoding="utf-8",
    )
    tmp.write(prompt)
    tmp.close()
    return tmp.name


def _cleanup_file(path: str) -> None:
    """Safely delete a temp file."""
    if path:
        try:
            os.unlink(path)
        except OSError:
            pass


def call_codex(mode: str, context: str, timeout: int = 300) -> dict:
    """
    Call Codex CLI and return results.

    All prompts are passed via temp file to avoid CLI arg length limits
    and process-list exposure. The temp file path is passed to
    `codex exec` as the prompt argument (Codex reads it as a file path
    or we pipe via stdin with `-`).

    Staged fallback:
    1. node codex.js exec --json (prompt via stdin from file) -> parse stdout
    2. If stdout empty -> temp file output via -o
    3. If all fail -> return manual execution command

    Args:
        mode: Operation mode (verify, review, opinion, diff, architecture)
        context: Content to send to Codex
        timeout: Timeout in seconds (default 300)

    Returns:
        dict with keys: success, method, and mode-specific results
    """
    node_path = find_node()
    codex_js_path = find_codex_js()
    prompt = f"[mode: {mode}]\n{context}"

    # Write prompt to temp file for all stages
    prompt_file = _write_prompt_file(prompt)

    try:
        # --- Stage 1: --json + stdout capture (prompt via stdin) ---
        try:
            with open(prompt_file, "r", encoding="utf-8") as f:
                prompt_text = f.read()
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
                input=prompt_text,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                shell=False,
            )
            if result.stdout.strip():
                try:
                    parsed = json.loads(result.stdout)
                    return {"success": True, "method": "stdout", **parsed}
                except json.JSONDecodeError:
                    return {
                        "success": True,
                        "method": "stdout_raw",
                        "raw_output": result.stdout,
                    }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "timeout", "method": "stdout"}
        except Exception:
            pass  # Fall through to stage 2

        # --- Stage 2: CREATE_NEW_CONSOLE + temp file output via -o ---
        # Note: -o is known to be unreliable on Windows 0.92.0 (Problem 2).
        # This stage is gated on Test 3 result. If Test 3 fails during
        # pre-implementation verification, skip Stage 2 and go to Stage 3.
        # CREATE_NEW_CONSOLE provides a real TTY; capture_output is NOT used
        # (incompatible with CREATE_NEW_CONSOLE).
        output_path = None
        try:
            out_tmp = tempfile.NamedTemporaryFile(
                suffix=".md", delete=False, dir=tempfile.gettempdir()
            )
            output_path = out_tmp.name
            out_tmp.close()

            with open(prompt_file, "r", encoding="utf-8") as f:
                prompt_text = f.read()
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
                input=prompt_text,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                timeout=timeout,
                shell=False,
                encoding="utf-8",
            )

            output_file = Path(output_path)
            if output_file.exists() and output_file.stat().st_size > 0:
                content = output_file.read_text(encoding="utf-8")
                try:
                    parsed = json.loads(content)
                    return {"success": True, "method": "tempfile", **parsed}
                except json.JSONDecodeError:
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
            _cleanup_file(output_path)

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

    finally:
        _cleanup_file(prompt_file)
```

Note on `npm root -g` (Strategy 3): `shell=True` is used ONLY for `npm.cmd` resolution (npm itself is a .cmd wrapper on Windows). This is a one-time path resolution call with no user input interpolation, so injection risk is minimal. All subsequent Codex calls use `shell=False`.

#### Each hook's import template (2 lines)

```python
import sys; sys.path.insert(0, str(__import__('pathlib').Path.home() / ".claude" / "lib"))
import bootstrap  # noqa: F401
```

Line 1 is identical across all hooks (copy-paste template). Line 2 activates the shared library. After these 2 lines, `from codex_wrapper import call_codex` works.

---

## Step 1: Gemini CLI Check

Verify Gemini CLI installation. If not installed, provide guidance. All hooks/skills handle Gemini absence gracefully (`shutil.which("gemini")` check before any call).

---

## Step 2: Hooks (8 scripts + 2 orchestrators + settings.json)

### New files in `~/.claude/hooks/`

| File | Role | Hook Event |
|------|------|-----------|
| `agent-router.py` | Route to Codex/Gemini + sc: validation | UserPromptSubmit |
| `check-codex-before-write.py` | Suggest Codex review before complex edits | PreToolUse (Write\|Edit) |
| `check-codex-after-plan.py` | Suggest Codex review after planning | PostToolUse (Task) |
| `lint-on-save.py` | Auto ruff/ty on Python save | Via orchestrator |
| `log-cli-tools.py` | Log Codex/Gemini CLI calls to JSONL | Via orchestrator |
| `post-implementation-review.py` | Suggest Codex review on 3+ files or 100+ lines | Via orchestrator |
| `post-test-analysis.py` | Suggest Codex debug on test failure | Via orchestrator |
| `suggest-gemini-research.py` | Suggest Gemini for research queries | PreToolUse (WebSearch\|WebFetch) |
| `post-write-orchestrator.py` | Sequence: lint-on-save -> post-implementation-review | PostToolUse (Write\|Edit) |
| `post-bash-orchestrator.py` | Sequence: post-test-analysis -> log-cli-tools | PostToolUse (Bash) |

### agent-router.py sc: validation (dynamic scan)

```python
def validate_skill_prefix(user_input: str) -> str | None:
    """
    Validate skill namespace. Dynamically scans ~/.claude/skills/ directory
    instead of hardcoded list (v5 improvement over v4).
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
```

### Orchestrator design

```python
# post-write-orchestrator.py
"""
Execute Write|Edit post-processing in guaranteed order:
1. lint-on-save.py (lint fixes first)
2. post-implementation-review.py (review after lint)

Design:
- Each sub-script is independently runnable (idempotent)
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
    "post-test-analysis.py": 300,
    "log-cli-tools.py": 10,
}
DEFAULT_TIMEOUT = 30


def run_hook(script_name: str, stdin_data: str) -> dict:
    """Run a sub-hook and return results."""
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
    stdin_data = sys.stdin.read()
    results = []
    results.append(run_hook("lint-on-save.py", stdin_data))
    results.append(run_hook("post-implementation-review.py", stdin_data))
    print(json.dumps({"orchestrator": "post-write", "results": results}))


if __name__ == "__main__":
    main()
```

### Windows conventions (all hooks)

- All hooks start with 2-line import template
- Temp files: `tempfile.gettempdir()`
- Log path: `pathlib.Path.home() / ".claude" / "logs"`
- Command existence: `shutil.which()`, graceful skip if absent
- Codex calls: via `codex_wrapper.py`
- Encoding: explicit `utf-8`

### settings.json (v10 - schema fix)

Existing hooks merged with new Orchestra hooks.
- Stop hook (session_parser): preserved
- PermissionRequest hook (permission_translator.py): REMOVED — Windows toast notification is redundant with Claude Code's native Japanese language support

```json
{
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

## Step 3: Rules (7 new files)

Create `~/.claude/rules/` with:

| File | Content | Customization |
|------|---------|--------------|
| `codex-delegation.md` | Codex delegation criteria | Align with existing delegate-codex |
| `gemini-delegation.md` | Gemini delegation criteria | As-is |
| `coding-principles.md` | Coding principles | As-is |
| `dev-environment.md` | Dev environment toolchain | Adjust for user env (uv/ruff/ty) |
| `language.md` | Language selection rules | As-is |
| `security.md` | Security practices | Merge with existing CLAUDE.md security |
| `testing.md` | Testing policy (TDD, AAA, 80% coverage) | As-is |

---

## Step 4: Skills (12 skills)

Create in `~/.claude/skills/`.

### Naming Convention
- skills/: invoke with `sc:` prefix (`/sc:plan`, `/sc:tdd`)
- commands/: no prefix (`/delegate-codex`)
- `agent-router.py` dynamically validates namespace (v5: directory scan, not hardcoded)

| Skill | Role | Relation to Existing |
|-------|------|---------------------|
| `startproject/` | 6-stage project bootstrap | New |
| `checkpointing/` | Session state persistence + TetsuyaSynapse auto-save | Integrates with save/save-to-vault via vault_sync.py |
| `plan/` | Structured planning | New |
| `tdd/` | TDD cycle execution | New |
| `codex-system/` | Codex CLI integration | Encompasses delegate-codex |
| `gemini-system/` | Gemini CLI integration | New |
| `design-tracker/` | Design tracking | New |
| `init/` | Initialization utilities | New |
| `research-lib/` | Research library | New |
| `simplify/` | Code simplification | New |
| `update-design/` | Design updates | New |
| `update-lib-docs/` | Library doc updates | New |

### Skill directory structure (v10)

Each skill follows this standard layout:
```
~/.claude/skills/{skill-name}/
+-- prompt.md       # Main skill prompt (required)
```

Example: `checkpointing/prompt.md`
```markdown
---
name: checkpointing
description: Session state persistence with TetsuyaSynapse auto-save
trigger: /sc:checkpointing
---

# Checkpointing

Save current session state to TetsuyaSynapse vault.

## Actions

1. Gather current session context (active tasks, recent decisions, open questions)
2. Generate summary
3. Call vault_sync.save_checkpoint(title, summary, context)
4. Report saved path to user

## Integration

- Vault target: 90-Claude/sessions/
- Fallback: ~/.claude/obsidian-sessions/sessions/
- Uses: vault_sync.py (shared lib)
```

### Existing skill coexistence
- `delegate-codex.md`: Keep (direct CLI invocation)
- `CODEX_PROMPTS.md`: Keep (prompt templates)
- `save-to-vault.md`: Keep (manual vault save). checkpointing/ extends this with auto-save.

### TetsuyaSynapse integration per skill

| Skill | Vault Integration |
|-------|------------------|
| `checkpointing/` | Calls `vault_sync.save_checkpoint()` on each checkpoint. Saves to `90-Claude/sessions/` |
| `codex-system/` | Calls `vault_sync.save_codex_review()` after each Codex review. Saves to `90-Claude/decisions/` |
| `gemini-system/` | Calls `vault_sync.save_gemini_research()` after each research. Saves to `90-Claude/learnings/` |
| `plan/` | On plan approval, saves plan + review history to `90-Claude/decisions/` via `save_codex_review()` |
| `design-tracker/` | Saves design decisions to `90-Claude/decisions/` |
| Other skills | No direct vault integration (session-level capture by existing session_parser) |

---

## Step 5: Agents

Create `~/.claude/agents/general-purpose.md`. Define sub-agent behavior (context retention, Codex/Gemini direct invocation, bullet-point summary returns).

---

## Step 6: Directory Structure

New directories:
```
~/.claude/
+-- lib/                (shared library)
|   +-- __init__.py
|   +-- bootstrap.py
|   +-- codex_wrapper.py
|   +-- gemini_wrapper.py
|   +-- path_utils.py
+-- hooks/              (10 Python scripts)
+-- rules/              (7 MD files)
+-- skills/             (12 directories)
+-- agents/             (1 MD file)
+-- logs/               (CLI output logs)
+-- docs/
    +-- research/       (Gemini research results)
```

Existing (modified):
```
+-- commands/
|   +-- scripts/pipeline/
|       +-- call_codex.py      (refactored: thin CLI wrapper, see Step 7)
|       +-- sync_vault.py      (REMOVED: consolidated into lib/vault_sync.py)
|       +-- save_context.py    (unchanged)
+-- scripts/            (claude_session_parser.py, etc.)
+-- pipeline/           (context/current/)
+-- projects/           (per-project settings)
```

---

## Step 7: call_codex.py Refactor (v10)

Refactor `~/.claude/commands/scripts/pipeline/call_codex.py` into a thin CLI wrapper.

### What moves to codex_wrapper.py (shared lib)
- `parse_json_from_output()` — regex JSON extraction added to codex_wrapper.
  codex_wrapper.call_codex() already tries json.loads; this adds regex fallback
  for cases where Codex output contains JSON embedded in other text.
  ```python
  def parse_json_from_output(output: str) -> dict | None:
      """Extract JSON from Codex output, handling embedded JSON in text."""
      # Try direct parse first
      try:
          return json.loads(output)
      except json.JSONDecodeError:
          pass
      # Regex fallback for JSON block in mixed output
      match = re.search(r'\{[\s\S]*\}', output)
      if match:
          try:
              return json.loads(match.group())
          except json.JSONDecodeError:
              pass
      return None
  ```
- Subprocess call logic (already in codex_wrapper with Windows fixes)

### What stays in call_codex.py (NOT moved)
- `get_prompt_template()` — mode-specific prompt content belongs with the CLI tool,
  not in the generic wrapper. codex_wrapper is mode-agnostic.

### What moves to vault_sync.py (shared lib)
- `log_decision()` — replaced by `save_codex_review()` + `record_review_issues()`

### What stays in call_codex.py (thin CLI wrapper)
- `main()` — CLI argument parsing (use argparse with required/optional args)
- `load_context()` — file-based context loading with path validation:
  ```python
  ALLOWED_BASE = Path.home() / ".claude"

  def load_context(mode: str) -> Optional[str]:
      context_file = (CONTEXT_DIR / f"{mode}.md").resolve()
      # Security: only read files under ~/.claude/
      if not str(context_file).startswith(str(ALLOWED_BASE)):
          raise ValueError(f"Path outside allowed directory: {context_file}")
      ...
  ```
- `ensure_dirs()` — directory creation

### What is removed
- `review_gate()` — interactive `input()` loop is incompatible with hooks.
  Review issues are now recorded via `vault_sync.record_review_issues()` into
  Self-Improvement Loop (notes/mistakes.md + rules-local.md), enabling
  automated learning without manual loop.

### Refactored call flow
```python
import sys; sys.path.insert(0, str(__import__('pathlib').Path.home() / ".claude" / "lib"))
import bootstrap  # noqa: F401
from codex_wrapper import call_codex
from vault_sync import save_codex_review, record_review_issues

def main():
    mode = sys.argv[1]
    context = load_context(mode) or sys.argv[2]

    result = call_codex(mode, context)

    # Save to vault (decisions/)
    save_codex_review(f"Codex {mode}", result, context[:2000])

    # Record issues to Self-Improvement Loop (notes/)
    issues = result.get("issues", [])
    if issues:
        record_review_issues(str(Path.cwd()), f"Codex {mode}", issues)

    return 0 if result.get("success") else 1
```

### Additional changes
1. Eliminate all `.cmd` invocations
2. Explicit `encoding="utf-8"`
3. All paths via `pathlib.Path`

---

## Step 8: CLAUDE.md Update (project-level)

Update project CLAUDE.md for 3-agent system:
- Multi-agent architecture description (Claude Code / Codex / Gemini)
- Context management golden rule (delegate 10+ lines to sub-agent)
- Document structure (docs/, logs/)
- Keep existing TetsuyaSynapse integration

Note: Global `~/.claude/CLAUDE.md` is NOT modified.

---

## Step 9: TetsuyaSynapse Integration (v5 addition)

### Overview

Integrate Orchestra outputs with the existing TetsuyaSynapse (Obsidian Vault) sync system. The existing infrastructure (session_parser, sync_vault, watch_session) handles session-level capture. This step adds **structured output capture** for Codex reviews, Gemini research, and checkpointing.

### Existing System (unchanged)

| Component | Role | Trigger |
|-----------|------|---------|
| `claude_session_parser.py` | Incremental JSONL parse, daily session files | Stop hook |
| `sync_vault.py` | Pipeline context sync to vault | Manual / script |
| `watch_session.py` | Real-time .jsonl monitoring daemon | Filesystem events |
| `sync-sessions.ps1` | Windows Task Scheduler sync | Scheduled task |
| `save-to-vault.md` | Manual vault save command | User invocation |

These continue to operate as-is. The new integration adds a **parallel output path** for structured data.

### New Integration Points

#### 1. checkpointing/ skill -> sessions/

When the user invokes `/sc:checkpointing` or the system creates an automatic checkpoint:

```
checkpointing/ skill
    -> vault_sync.save_checkpoint(title, summary, context)
    -> writes to 90-Claude/sessions/YYYY-MM-DD_title_checkpoint.md
    -> fallback: ~/.claude/obsidian-sessions/sessions/
```

Content format:
```markdown
---
date: 2026-01-31
time: 07:30:00
type: checkpoint
title: "Orchestra integration checkpoint"
source: orchestra-checkpointing
tags: [auto-generated, checkpoint, orchestra]
---

# Orchestra integration checkpoint

## Summary
[Session summary]

## Context
[Current tasks, decisions, open questions as JSON]
```

#### 2. Codex review results -> decisions/

When `call_codex.py` or `codex-system/` skill completes a review:

```
codex_wrapper.call_codex(mode="verify", context=plan)
    -> result = {...}
    -> vault_sync.save_codex_review(title, result, plan_context)
    -> writes to 90-Claude/decisions/YYYY-MM-DD_title_review.md
    -> fallback: ~/.claude/obsidian-sessions/decisions/
```

This also applies to:
- `check-codex-after-plan.py` hook (automatic review after planning)
- `post-implementation-review.py` hook (automatic review after large changes)
- Manual `/sc:codex-system` invocations

#### 3. Gemini research results -> learnings/

When `gemini-system/` skill or `suggest-gemini-research.py` hook completes research:

```
gemini_wrapper.call_gemini(query=...)
    -> result = {...}
    -> vault_sync.save_gemini_research(title, query, result, sources)
    -> writes to 90-Claude/learnings/YYYY-MM-DD_title_research.md
    -> fallback: ~/.claude/obsidian-sessions/learnings/
```

#### 4. Plan approval -> decisions/

When a plan passes Codex review (approved: true) in `plan/` skill:

```
plan/ skill
    -> Codex review approved
    -> vault_sync.save_codex_review("Plan: [name] - APPROVED", result, plan_text)
    -> writes to 90-Claude/decisions/
```

### Integration with call_codex.py

Modify `call_codex.py` (Step 7) to auto-save review results:

```python
# In call_codex.py, after receiving Codex result:
from vault_sync import save_codex_review

def call_codex(mode, custom_context=None, iteration=1):
    # ... existing logic ...
    result = ...  # Codex result

    # Auto-save to TetsuyaSynapse
    if mode in ("verify", "review", "architecture"):
        try:
            save_codex_review(
                title=f"Codex {mode} - iteration {iteration}",
                review_result=result,
                plan_context=context[:2000] if context else "",
            )
        except Exception:
            pass  # Vault save is best-effort, never block main flow

    return result
```

### Integration with hooks

Hooks that trigger Codex review also save results:

```python
# In post-implementation-review.py (called via post-write-orchestrator):
from vault_sync import save_codex_review

def on_review_complete(review_result, changed_files):
    save_codex_review(
        title=f"Implementation review - {len(changed_files)} files",
        review_result=review_result,
        plan_context="\n".join(changed_files),
    )
```

### Data Flow with TetsuyaSynapse

```
Orchestra Components              TetsuyaSynapse Vault
===================              ===================

checkpointing/ skill  ------>  90-Claude/sessions/
                                  YYYY-MM-DD_*_checkpoint.md

codex-system/ skill   ------>  90-Claude/decisions/
call_codex.py                     YYYY-MM-DD_*_review.md
check-codex-after-plan.py
post-implementation-review.py

gemini-system/ skill  ------>  90-Claude/learnings/
suggest-gemini-research.py        YYYY-MM-DD_*_research.md

plan/ skill (approved) ----->  90-Claude/decisions/
                                  YYYY-MM-DD_*_review.md

session_parser.py     ------>  90-Claude/sessions/
(existing, unchanged)             YYYY-MM-DD_auto.md
```

### Vault Accessibility Handling

The existing system already handles Google Drive unavailability:
- `vault_sync.py` checks `_vault_available()` before every write
- Falls back to `~/.claude/obsidian-sessions/{subdir}/`
- Existing `sync-sessions.ps1` has 5-minute startup wait for Google Drive
- No changes needed to offline fallback behavior

### Known Issue: Japanese Path Encoding

The existing PowerShell sync script has encoding issues with the Japanese path (`G:\My Drive\obsidian\...`). The new `vault_sync.py` uses Python's `pathlib.Path` which handles Unicode correctly. No additional workaround needed for the Python-side integration.

---

## Implementation Order

(Updated with Step 9)

1. Pre-implementation verification (3 tests from Step 0)
2. Create directories (lib, hooks, rules, skills, agents, logs, docs)
3. Create bootstrap.py + shared libraries (`~/.claude/lib/` including vault_sync.py)
4. Create codex_wrapper.py (adjust based on test results)
5. Create vault_sync.py (TetsuyaSynapse integration helper)
6. Fix call_codex.py (add vault auto-save)
7. Create orchestrator scripts (post-write, post-bash)
8. Create 8 hook scripts (with vault save integration where applicable)
9. Create 7 rule files
10. Create 1 agent file
11. Create 12 skill directories with files (checkpointing/codex-system/gemini-system with vault integration)
12. Update settings.json
13. Update CLAUDE.md (project-level)
14. Verification:
    - Re-run Step 0 tests
    - Hook firing tests
    - Vault save test: trigger a Codex review and verify file appears in 90-Claude/decisions/
    - Checkpoint test: invoke /sc:checkpointing and verify file in 90-Claude/sessions/
    - Fallback test: disconnect Google Drive and verify local cache saves work

---

## Risk Assessment

### High Risk
- Codex CLI non-TTY output: Staged fallback handles this. Pre-implementation tests determine actual behavior before coding.

### Medium Risk
- Hook execution performance: agent-router.py fires on every prompt. Mitigations:
  - Early-return: skip prompts shorter than 10 chars (single words, "yes", "no", etc.)
  - Cache skills directory listing (invalidate on file modification time change)
  - Example gate in agent-router.py:
    ```python
    user_input = data.get("user_input", "").strip()
    if len(user_input) < 10:
        sys.exit(0)  # No output = allow, skip processing
    ```
- uv/ruff/ty not installed: `shutil.which()` check, skip if absent.
- Existing settings.json merge: Must merge, not overwrite.
- Vault write frequency: Codex reviews and checkpoints may generate many files. Rate-limit or deduplicate to avoid vault clutter.
- Google Drive sync timing: vault_sync writes may not appear in Obsidian immediately if Google Drive is slow to sync.

### Low Risk (resolved in v2-v4)
- Shared library import: bootstrap.py + 2-line template
- .cmd execution: Bypassed entirely via node codex.js
- shell=True security: Eliminated (except one-time npm root -g)
- Hook execution order: Orchestrator pattern
- commands/skills collision: sc: prefix + dynamic directory scan validation

---

## Security Policy

1. shell=False strictly enforced for all subprocess calls (exception: `npm root -g` for one-time path resolution with no user input)
2. External input via temp files (not command-line arguments)
3. Path validation: only read files under `~/.claude/`
4. Python absolute path in settings.json (prevent MSYS python confusion)
5. No secrets in logs: log-cli-tools.py excludes env vars that may contain API keys
6. Input size limit: hooks check stdin data size before JSON parsing

---

## Review Request (v9)

Please verify the v8 review fixes are adequate:

### v8 Fix Verification
1. **Filename sub-second uniqueness**: `_generate_filename()` now appends a 4-char hex UUID after HHMMSS: `YYYY-MM-DD_HHMMSS_xxxx_slug_suffix.md`. This provides collision resistance even for multiple saves within the same second. Is this sufficient?
2. **Test 3 Stage 2 validation**: Test 3 replaced with `-o` temp file output test that validates Stage 2 fallback behavior (file creation, size, content). Test 2 validates Stage 1 (stdout via stdin). Are the three tests now sufficiently distinct to cover all stages?

### Continued Verification (carried from v8)
3. **CLI-arg prompt elimination**: Confirmed eliminated in v8. Any remaining instances?
4. **Vault write independence**: `_write_with_fallback()` attempts vault regardless of local outcome (v8 fix). Any concerns?
5. **YAML escaping**: `_yaml_escape()` handles backslashes and quotes (v8 fix). Any edge cases?
6. **TetsuyaSynapse integration**: Any remaining concerns?
7. **Overall maturity**: Are there any remaining blockers that prevent implementation?
