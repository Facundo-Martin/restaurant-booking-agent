"""Shared scorers for booking operations (Reservations, Cancellations, Updates).

These scorers will be reused across multiple booking-related features.
Built as parameterized, reusable functions.
"""

from braintrust import Score


def user_confirmation_required(output: str, trace: dict, **kwargs) -> Score:
    """
    Check: Did agent ask for user confirmation before action?

    Applies to: Reservations, Cancellations, Updates

    Returns: 1.0 if confirmation asked, 0.0 otherwise
    """
    # Implementation in Phase 3 (when booking operations are implemented)
    pass


def correct_tool_called(
    output: str, trace: dict, expected_tool: str, **kwargs
) -> Score:
    """
    Check: Did agent call the expected tool?

    Applies to: Reservations (create_booking), Cancellations (delete_booking), Updates (update_booking)

    Args:
        expected_tool: Name of tool (parameterized)

    Returns: 1.0 if correct tool called, 0.0 otherwise
    """
    # Implementation in Phase 3 (when booking operations are implemented)
    pass


__all__ = ["user_confirmation_required", "correct_tool_called"]
