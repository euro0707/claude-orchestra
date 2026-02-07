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
