"""DynamoDB tools for managing restaurant bookings."""

from strands import tool

from app.repositories import bookings as booking_repo


@tool
def get_booking_details(booking_id: str, restaurant_name: str) -> dict:
    """Get the details of an existing booking.

    Args:
        booking_id: The unique booking identifier.
        restaurant_name: The name of the restaurant.

    Returns:
        The booking details, or a message if not found.
    """
    booking = booking_repo.get(booking_id, restaurant_name)
    return booking.model_dump() if booking else {"error": f"No booking found with ID {booking_id}"}


@tool
def create_booking(
    restaurant_name: str,
    user_id: str,
    date: str,
    party_size: int,
    special_requests: str | None = None,
) -> dict:
    """Create a new restaurant booking.

    Args:
        restaurant_name: The name of the restaurant.
        user_id: The ID of the user making the booking.
        date: The date of the booking (YYYY-MM-DD).
        party_size: The number of people in the party.
        special_requests: Any special requests or dietary requirements.

    Returns:
        The created booking details including the generated booking_id.
    """
    booking = booking_repo.create(
        restaurant_name=restaurant_name,
        user_id=user_id,
        date=date,
        party_size=party_size,
        special_requests=special_requests,
    )
    return booking.model_dump()


@tool
def delete_booking(booking_id: str, restaurant_name: str) -> str:
    """Delete an existing booking.

    Args:
        booking_id: The unique booking identifier.
        restaurant_name: The name of the restaurant.

    Returns:
        A confirmation message, or an error if the booking was not found.
    """
    deleted = booking_repo.delete(booking_id, restaurant_name)
    if deleted:
        return f"Booking {booking_id} at {restaurant_name} successfully deleted."
    return f"No booking found with ID {booking_id} at {restaurant_name}."
