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
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1024)
        except Exception:
            pass
    else:
        import fcntl
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


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
    v17 H-3: Returns permissive fallback on lock/I/O failure (best-effort).
    """
    with _lock:
        fh = None
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
    """Record a completed agent call (token usage only)."""
    with _lock:
        fh = None
        try:
            state, fh = _load_state_locked()
            state["total_tokens"] += tokens_used
            state["calls"].append({
                "agent": agent,
                "tokens": tokens_used,
                "duration_ms": duration_ms,
                "timestamp": time.time(),
            })
            _save_state_locked(state, fh)
        except Exception:
            if fh is not None:
                try:
                    _file_unlock(fh)
                    fh.close()
                except Exception:
                    pass


def acquire_slot(agent: str) -> bool:
    """Try to acquire a concurrency slot for an agent call."""
    with _lock:
        fh = None
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
    """Release a concurrency slot after agent call completes."""
    with _lock:
        fh = None
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
    """Reset budget state for a new session."""
    with _lock:
        fh = None
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
    """Get session budget summary."""
    with _lock:
        fh = None
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
