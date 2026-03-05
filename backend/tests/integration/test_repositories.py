"""Integration tests: DynamoDB repository layer against a real table.

Each test creates its own data (unique UUID from booking_repo.create) and
deletes it in a finally block, so they are safe to run repeatedly against
a shared test-stage table without leaving debris.

Run:
    INTEGRATION_TABLE_NAME=<name> uv run pytest tests/integration/test_repositories.py -v
"""

import pytest

from app.repositories import bookings as booking_repo

pytestmark = pytest.mark.integration

_RESTAURANT = "Integration Test Restaurant"
_USER = "integration-test-user"


def test_create_get_roundtrip(real_table):
    """create then get returns the full booking with matching fields."""
    booking = booking_repo.create(
        restaurant_name=_RESTAURANT,
        user_id=_USER,
        date="2099-01-01",
        party_size=2,
    )
    try:
        fetched = booking_repo.get(booking.booking_id, _RESTAURANT)
        assert fetched is not None
        assert fetched.booking_id == booking.booking_id
        assert fetched.restaurant_name == _RESTAURANT
        assert fetched.party_size == 2
        assert fetched.special_requests is None
    finally:
        booking_repo.delete(booking.booking_id, _RESTAURANT)


def test_create_with_special_requests(real_table):
    """special_requests round-trips correctly."""
    booking = booking_repo.create(
        restaurant_name=_RESTAURANT,
        user_id=_USER,
        date="2099-01-02",
        party_size=4,
        special_requests="Gluten-free menu please",
    )
    try:
        fetched = booking_repo.get(booking.booking_id, _RESTAURANT)
        assert fetched is not None
        assert fetched.special_requests == "Gluten-free menu please"
    finally:
        booking_repo.delete(booking.booking_id, _RESTAURANT)


def test_get_nonexistent_returns_none(real_table):
    """get returns None for a booking that was never created."""
    assert booking_repo.get("does-not-exist-integration", _RESTAURANT) is None


def test_delete_existing(real_table):
    """delete returns True when the item exists and removes it."""
    booking = booking_repo.create(
        restaurant_name=_RESTAURANT,
        user_id=_USER,
        date="2099-01-03",
        party_size=2,
    )
    assert booking_repo.delete(booking.booking_id, _RESTAURANT) is True
    assert booking_repo.get(booking.booking_id, _RESTAURANT) is None


def test_delete_nonexistent_returns_false(real_table):
    """delete returns False when the item does not exist."""
    assert booking_repo.delete("does-not-exist-integration", _RESTAURANT) is False


def test_delete_is_idempotent(real_table):
    """Second delete on the same key returns False — not an error."""
    booking = booking_repo.create(
        restaurant_name=_RESTAURANT,
        user_id=_USER,
        date="2099-01-04",
        party_size=2,
    )
    assert booking_repo.delete(booking.booking_id, _RESTAURANT) is True
    assert booking_repo.delete(booking.booking_id, _RESTAURANT) is False
