"""E2E 6.5: Budget enforcement with multiple agents.

Integration tests for cross-module budget behavior: slot + budget + summary
interactions, multi-agent session lifecycle, and state persistence across
operations. Unit-level tests are in test_budget.py.
"""
import pytest

import budget
from budget import (
    check_budget,
    record_call,
    acquire_slot,
    release_slot,
    get_summary,
    reset_session,
)


class TestMultiAgentSessionLifecycle:
    """6.5: Full session lifecycle with multiple agents using budget + slots."""

    def test_full_session_flow(self, mock_budget_file):
        """Simulate a multi-agent session: acquire → record → check → release → summary."""
        # Phase 1: Two agents start work
        assert acquire_slot("codex") is True
        assert acquire_slot("gemini") is True
        assert acquire_slot("extra") is False  # max_concurrent=2

        # Phase 2: Agents consume budget
        record_call("codex", 100000, 500)
        record_call("gemini", 50000, 300)

        # Phase 3: Budget check reflects both agents
        result = check_budget(estimated_tokens=1000)
        assert result["allowed"] is False  # at max concurrent
        assert result["remaining"] == 350000
        assert result["active_calls"] == 2

        # Phase 4: One agent finishes
        release_slot()
        result = check_budget(estimated_tokens=1000)
        assert result["allowed"] is True  # below max concurrent now
        assert result["active_calls"] == 1

        # Phase 5: New agent takes the slot
        assert acquire_slot("codex-2") is True
        record_call("codex", 200000, 400)

        # Phase 6: Summary reflects full session
        summary = get_summary()
        assert summary["total_tokens"] == 350000
        assert summary["total_calls"] == 3
        assert summary["remaining_tokens"] == 150000
        assert summary["by_agent"]["codex"]["calls"] == 2
        assert summary["by_agent"]["codex"]["tokens"] == 300000
        assert summary["by_agent"]["gemini"]["calls"] == 1
        assert summary["by_agent"]["gemini"]["tokens"] == 50000


class TestBudgetExhaustionAndRecovery:
    """6.5: Budget exhaustion blocks new calls, reset recovers."""

    def test_exhaust_then_reset_recovers(self, mock_budget_file):
        # Exhaust budget
        record_call("codex", 250000)
        record_call("gemini", 250000)

        # Should be blocked
        result = check_budget(estimated_tokens=1)
        assert result["allowed"] is False
        assert result["remaining"] == 0

        # Reset restores full capacity
        reset_session()
        result = check_budget(estimated_tokens=1000)
        assert result["allowed"] is True
        assert result["remaining"] == 500000

        # Slots also reset
        assert acquire_slot("a1") is True
        assert acquire_slot("a2") is True


class TestSlotBudgetInteraction:
    """6.5: Slot state and budget state interact correctly."""

    def test_slot_count_reflected_in_budget_check(self, mock_budget_file):
        """check_budget reports active_calls from slot state."""
        acquire_slot("agent-1")
        result = check_budget(estimated_tokens=0)
        assert result["active_calls"] == 1
        assert result["allowed"] is True  # 1 < max_concurrent=2

        acquire_slot("agent-2")
        result = check_budget(estimated_tokens=0)
        assert result["active_calls"] == 2
        assert result["allowed"] is False  # at max

        release_slot()
        release_slot()
        result = check_budget(estimated_tokens=0)
        assert result["active_calls"] == 0
        assert result["allowed"] is True

    def test_exact_budget_boundary(self, mock_budget_file):
        """Budget at exact limit blocks, one token under allows."""
        record_call("codex", 499999)
        result = check_budget(estimated_tokens=1)
        assert result["allowed"] is True
        assert result["remaining"] == 1

        record_call("codex", 1)
        result = check_budget(estimated_tokens=1)
        assert result["allowed"] is False
        assert result["remaining"] == 0


class TestResetClearsAllState:
    """6.5: reset_session clears both budget and slot state atomically."""

    def test_reset_clears_slots_and_budget(self, mock_budget_file):
        # Build up state
        acquire_slot("a1")
        acquire_slot("a2")
        record_call("codex", 400000)

        # Verify state is accumulated
        summary = get_summary()
        assert summary["total_tokens"] == 400000
        result = check_budget(estimated_tokens=0)
        assert result["active_calls"] == 2

        # Reset clears everything
        reset_session()

        summary = get_summary()
        assert summary["total_tokens"] == 0
        assert summary["total_calls"] == 0
        assert summary["remaining_tokens"] == 500000
        assert summary["by_agent"] == {}

        result = check_budget(estimated_tokens=0)
        assert result["active_calls"] == 0

        # New slots available
        assert acquire_slot("b1") is True
        assert acquire_slot("b2") is True
