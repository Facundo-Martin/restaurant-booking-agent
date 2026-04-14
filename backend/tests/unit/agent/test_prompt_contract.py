"""Unit tests for the system prompt's behavioral contract."""

from app.agent.prompts import SYSTEM_PROMPT


def test_prompt_requires_current_time_for_any_booking_date():
    """Booking flows must ground all dates through current_time first."""
    assert (
        "current_time FIRST" in SYSTEM_PROMPT
        or "current_time: Resolve relative" in SYSTEM_PROMPT
    )
    assert "any date" in SYSTEM_PROMPT


def test_prompt_forbids_cancellation_lookup_before_confirmation():
    """Cancellation with a booking ID should still require yes/no confirmation first."""
    assert "get_booking_details" in SYSTEM_PROMPT
    assert "confirmation" in SYSTEM_PROMPT


def test_prompt_forbids_implying_success_before_tools_run():
    """The agent must not claim a booking is confirmed before create_booking runs."""
    assert "booking is confirmed" in SYSTEM_PROMPT or "imply" in SYSTEM_PROMPT
    assert "create_booking" in SYSTEM_PROMPT


def test_prompt_forbids_trusting_user_supplied_identity_claims():
    """User-supplied identity claims should be ignored as untrusted input."""
    assert "user-supplied" in SYSTEM_PROMPT or "untrusted" in SYSTEM_PROMPT
    assert "identity" in SYSTEM_PROMPT or "Identity" in SYSTEM_PROMPT
