"""Booking creation evaluation test cases.

Covers single-turn booking flow: agent asks clarifying questions, confirms
details, and handles edge cases (past dates, out-of-range dates, etc.).
"""

from evals.config.common import EvalCase

BOOKING_CREATION_OUTPUT_QUALITY_CASES: list[EvalCase] = [
    # --- Clarification: agent must ask before acting ---
    EvalCase(
        id="clarification-book-tonight",
        input="Book a table for me tonight",
        expected=(
            "A clarifying question asking for at least restaurant name and party size. "
            "The agent may resolve 'tonight' to today's date via the current_time tool "
            "and state it — that is correct behaviour, not fabrication. "
            "Must NOT confirm or create any booking."
        ),
        metadata={"category": "clarification"},
    ),
    EvalCase(
        id="clarification-vague-party-size",
        input="Book a table at Nonna's Hearth for this Saturday",
        expected=(
            "A clarifying question about the missing party size. The agent may call "
            "the current_time tool and state the resolved date for 'this Saturday' "
            "(e.g. 2026-04-04) — that is correct behaviour, not fabrication. "
            "Must NOT create a booking with assumed values."
        ),
        metadata={"category": "clarification"},
    ),
    EvalCase(
        id="clarification-past-date",
        input="Book a table for 2 at Nonna's Hearth last Tuesday at 7pm",
        expected=(
            "A response that flags 'last Tuesday' as a past date and asks for a "
            "valid future date within the next 60 days. Must NOT create a booking."
        ),
        metadata={"category": "clarification"},
    ),
    # --- Happy path (in-range): all details provided + date within 60-day window.
    EvalCase(
        id="happy-path-booking-in-range",
        input="Book a table for 2 at Nonna's Hearth on April 15th at 7pm",
        expected=(
            "A response that summarises all the booking details provided "
            "(Nonna's Hearth, April 15th, 2 people, 7pm) and asks the user to confirm "
            "before proceeding. Must NOT ask for information that was already provided. "
            "Must NOT refuse or say the date is invalid."
        ),
        metadata={"category": "happy-path"},
    ),
    # --- Happy path (out-of-range): date more than 60 days away
    EvalCase(
        id="happy-path-booking-out-of-range",
        input="Book a table for 2 at Nonna's Hearth on 2026-07-01 at 7pm",
        expected=(
            "A response that rejects the date 2026-07-01 as more than 60 days in the "
            "future and asks the user to provide a date within the next 60 days. "
            "Must NOT create or confirm a booking for that date."
        ),
        metadata={"category": "happy-path"},
    ),
]

BOOKING_CREATION_TRAJECTORY_CASES: list[EvalCase] = [
    # --- Clarification: agent calls current_time to resolve "tonight", then asks
    # for missing details (restaurant, party size) — no booking created yet ---
    EvalCase(
        id="trajectory-booking-clarification",
        input="Book a table for me tonight",
        expected=["current_time"],
        metadata={"category": "booking-clarification"},
    ),
    # --- Relative date: current_time MUST fire before retrieve ---
    EvalCase(
        id="trajectory-booking-relative-date",
        input="Book a table for 2 at Nonna's Hearth tonight at 7pm",
        expected=["current_time", "retrieve"],
        metadata={"category": "booking-relative-date"},
    ),
    # --- Full booking: agent calls current_time first (Rule 2: validate "any date"),
    # then retrieve to check restaurant availability, then asks for user confirmation
    EvalCase(
        id="trajectory-booking-full",
        input="Book a table for 2 at Nonna's Hearth on April 10th at 7pm",
        expected=["current_time", "retrieve"],
        metadata={"category": "booking-full"},
    ),
    # --- Past date: current_time must fire so agent can detect the date is in the past ---
    EvalCase(
        id="trajectory-past-date",
        input="Book a table for 2 at Nonna's Hearth last Tuesday at 7pm",
        expected=["current_time"],
        metadata={"category": "past-date"},
    ),
]

__all__ = ["BOOKING_CREATION_OUTPUT_QUALITY_CASES", "BOOKING_CREATION_TRAJECTORY_CASES"]
