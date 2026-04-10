"""Booking cancellation evaluation test cases.

Covers cancellation flow: agent must confirm booking ID and user intent before
executing a cancellation. Tests that agent doesn't ask for unnecessary details.
"""

from evals.additional_test_cases.common import EvalCase

BOOKING_CANCELLATION_OUTPUT_QUALITY_CASES: list[EvalCase] = [
    # --- Clarification: agent must ask for booking ID and confirmation ---
    EvalCase(
        id="clarification-cancel-no-id",
        input="Cancel my reservation",
        expected=(
            "A request for the booking ID AND confirmation that the user wants to "
            "cancel, before taking any action. Must NOT attempt a cancellation."
        ),
        metadata={"category": "clarification"},
    ),
    # --- Happy path: booking ID and cancellation intent both provided.
    EvalCase(
        id="happy-path-cancellation",
        input="Cancel booking B-456",
        expected=(
            "A response that acknowledges booking B-456 and asks for a simple "
            "yes/no confirmation before cancelling. "
            "Must NOT ask for the booking ID (already provided). "
            "Must NOT ask for the restaurant name or other details beyond what "
            "Rule 5 requires (booking ID + cancellation intent). "
            "Must NOT say the booking was not found."
        ),
        metadata={"category": "happy-path"},
    ),
]

BOOKING_CANCELLATION_TRAJECTORY_CASES: list[EvalCase] = [
    # --- Cancellation: agent asks the user to confirm before calling delete_booking
    # (Rule 5). No tools fire in a single-turn eval — agent confirms booking ID is
    # provided and asks "are you sure?" directly. ---
    EvalCase(
        id="trajectory-cancellation",
        input="Cancel booking B-456",
        expected=[],
        metadata={"category": "cancellation"},
    ),
]

__all__ = [
    "BOOKING_CANCELLATION_OUTPUT_QUALITY_CASES",
    "BOOKING_CANCELLATION_TRAJECTORY_CASES",
]
