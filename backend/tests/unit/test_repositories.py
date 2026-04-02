"""Unit tests for the DynamoDB booking repository."""

import importlib

import pytest

from app.repositories import bookings as booking_repo


def test_repository_import_does_not_initialize_dynamodb(monkeypatch):
    """Importing the repository must not create a DynamoDB client eagerly."""

    def fail_on_resource(*_args, **_kwargs):
        raise AssertionError("boto3.resource should not be called during import")

    monkeypatch.setattr("boto3.resource", fail_on_resource)

    importlib.reload(booking_repo)


@pytest.mark.usefixtures("dynamodb_table")
def test_get_returns_none_when_not_found():
    """Getting a missing booking should return None."""
    assert booking_repo.get("nonexistent-id") is None


@pytest.mark.usefixtures("dynamodb_table")
def test_create_and_get_roundtrip():
    """Creating a booking should persist it and allow a round-trip fetch."""
    booking = booking_repo.create(
        restaurant_name="Nonna's Hearth",
        user_id="user-1",
        date="2026-03-01",
        party_size=2,
    )

    fetched = booking_repo.get(booking.booking_id)

    assert fetched is not None
    assert fetched.booking_id == booking.booking_id
    assert fetched.restaurant_name == "Nonna's Hearth"
    assert fetched.party_size == 2
    assert fetched.special_requests is None


@pytest.mark.usefixtures("dynamodb_table")
def test_create_with_special_requests():
    """Optional special requests should be stored with the booking."""
    booking = booking_repo.create(
        restaurant_name="Bistro Parisienne",
        user_id="user-2",
        date="2026-03-15",
        party_size=4,
        special_requests="Gluten-free menu please",
    )

    fetched = booking_repo.get(booking.booking_id)

    assert fetched is not None
    assert fetched.special_requests == "Gluten-free menu please"


@pytest.mark.usefixtures("dynamodb_table")
def test_create_generates_unique_ids():
    """Each created booking should receive a distinct generated ID."""
    b1 = booking_repo.create(
        restaurant_name="Ember & Vine", user_id="u1", date="2026-03-01", party_size=2
    )
    b2 = booking_repo.create(
        restaurant_name="Ember & Vine", user_id="u2", date="2026-03-02", party_size=4
    )

    assert b1.booking_id != b2.booking_id


@pytest.mark.usefixtures("dynamodb_table")
def test_delete_existing_booking():
    """Deleting an existing booking should remove it and report success."""
    booking = booking_repo.create(
        restaurant_name="The Coastal Bloom",
        user_id="user-3",
        date="2026-04-10",
        party_size=3,
    )

    assert booking_repo.delete(booking.booking_id) is True
    assert booking_repo.get(booking.booking_id) is None


@pytest.mark.usefixtures("dynamodb_table")
def test_delete_nonexistent_booking():
    """Deleting a missing booking should report False."""
    assert booking_repo.delete("nonexistent-id") is False


@pytest.mark.usefixtures("dynamodb_table")
def test_delete_is_idempotent():
    """Deleting the same booking twice should succeed once and then return False."""
    booking = booking_repo.create(
        restaurant_name="Rice & Spice",
        user_id="user-4",
        date="2026-05-01",
        party_size=2,
    )

    assert booking_repo.delete(booking.booking_id) is True
    assert booking_repo.delete(booking.booking_id) is False
