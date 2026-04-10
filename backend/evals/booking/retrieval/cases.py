"""Booking retrieval evaluation test cases.

Covers booking lookup flow: agent retrieves and displays booking details
without modifying or deleting. Future cases: retrieve all bookings, retrieve
by date range, etc.
"""

from evals.additional_test_cases.common import EvalCase

BOOKING_RETRIEVAL_TRAJECTORY_CASES: list[EvalCase] = [
    # --- Lookup: get_booking_details must be called ---
    EvalCase(
        id="trajectory-booking-lookup",
        input="What are the details for booking B-456?",
        expected=["get_booking_details"],
        metadata={"category": "booking-lookup"},
    ),
]

__all__ = ["BOOKING_RETRIEVAL_TRAJECTORY_CASES"]
