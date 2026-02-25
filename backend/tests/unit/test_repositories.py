"""Unit tests for the DynamoDB booking repository."""

from app.repositories import bookings as booking_repo


def test_get_returns_none_when_not_found(dynamodb_table):
    assert booking_repo.get("nonexistent-id", "Any Restaurant") is None


def test_create_and_get_roundtrip(dynamodb_table):
    booking = booking_repo.create(
        restaurant_name="Nonna's Hearth",
        user_id="user-1",
        date="2026-03-01",
        party_size=2,
    )

    fetched = booking_repo.get(booking.booking_id, "Nonna's Hearth")

    assert fetched is not None
    assert fetched.booking_id == booking.booking_id
    assert fetched.restaurant_name == "Nonna's Hearth"
    assert fetched.party_size == 2
    assert fetched.special_requests is None


def test_create_with_special_requests(dynamodb_table):
    booking = booking_repo.create(
        restaurant_name="Bistro Parisienne",
        user_id="user-2",
        date="2026-03-15",
        party_size=4,
        special_requests="Gluten-free menu please",
    )

    fetched = booking_repo.get(booking.booking_id, "Bistro Parisienne")

    assert fetched is not None
    assert fetched.special_requests == "Gluten-free menu please"


def test_create_generates_unique_ids(dynamodb_table):
    b1 = booking_repo.create(restaurant_name="Ember & Vine", user_id="u1", date="2026-03-01", party_size=2)
    b2 = booking_repo.create(restaurant_name="Ember & Vine", user_id="u2", date="2026-03-02", party_size=4)

    assert b1.booking_id != b2.booking_id


def test_delete_existing_booking(dynamodb_table):
    booking = booking_repo.create(
        restaurant_name="The Coastal Bloom",
        user_id="user-3",
        date="2026-04-10",
        party_size=3,
    )

    assert booking_repo.delete(booking.booking_id, "The Coastal Bloom") is True
    assert booking_repo.get(booking.booking_id, "The Coastal Bloom") is None


def test_delete_nonexistent_booking(dynamodb_table):
    assert booking_repo.delete("nonexistent-id", "Any Restaurant") is False


def test_delete_is_idempotent(dynamodb_table):
    booking = booking_repo.create(
        restaurant_name="Rice & Spice",
        user_id="user-4",
        date="2026-05-01",
        party_size=2,
    )

    assert booking_repo.delete(booking.booking_id, "Rice & Spice") is True
    assert booking_repo.delete(booking.booking_id, "Rice & Spice") is False
