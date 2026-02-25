"""Unit tests for the Strands booking tool functions.

The @tool decorator adds agent metadata but keeps the function callable
with its original signature, so we test them as regular functions and
mock the repository layer underneath.
"""

from unittest.mock import patch

from app.models.schemas import Booking
from app.tools.bookings import create_booking, delete_booking, get_booking_details

_SAMPLE_BOOKING = Booking(
    booking_id="abc-123",
    restaurant_name="Nonna's Hearth",
    user_id="user-1",
    date="2026-03-01",
    party_size=2,
)


def test_get_booking_details_found():
    with patch("app.repositories.bookings.get", return_value=_SAMPLE_BOOKING):
        result = get_booking_details(booking_id="abc-123", restaurant_name="Nonna's Hearth")

    assert result["booking_id"] == "abc-123"
    assert result["party_size"] == 2


def test_get_booking_details_not_found():
    with patch("app.repositories.bookings.get", return_value=None):
        result = get_booking_details(booking_id="missing", restaurant_name="Any")

    assert "error" in result


def test_create_booking():
    with patch("app.repositories.bookings.create", return_value=_SAMPLE_BOOKING):
        result = create_booking(
            restaurant_name="Nonna's Hearth",
            user_id="user-1",
            date="2026-03-01",
            party_size=2,
        )

    assert result["booking_id"] == "abc-123"
    assert result["restaurant_name"] == "Nonna's Hearth"


def test_delete_booking_success():
    with patch("app.repositories.bookings.delete", return_value=True):
        result = delete_booking(booking_id="abc-123", restaurant_name="Nonna's Hearth")

    assert "successfully deleted" in result


def test_delete_booking_not_found():
    with patch("app.repositories.bookings.delete", return_value=False):
        result = delete_booking(booking_id="missing", restaurant_name="Any")

    assert "No booking found" in result
