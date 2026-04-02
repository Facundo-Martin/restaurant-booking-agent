"""DynamoDB tools for managing restaurant bookings."""

from strands import tool

from app.context import current_user_id
from app.metrics import MetricUnit, metrics
from app.repositories import bookings as booking_repo
from app.tracer import tracer


@tool
@tracer.capture_method
def get_booking_details(booking_id: str) -> dict:
    """Get the details of an existing booking.

    Args:
        booking_id: The unique booking identifier.

    Returns:
        The booking details, or a message if not found.
    """
    booking = booking_repo.get(booking_id)
    return (
        booking.model_dump()
        if booking
        else {"error": f"No booking found with ID {booking_id}"}
    )


@tool
@tracer.capture_method
def create_booking(
    restaurant_name: str,
    date: str,
    party_size: int,
    special_requests: str | None = None,
) -> dict:
    """Create a new restaurant booking.

    Args:
        restaurant_name: The name of the restaurant.
        date: The date of the booking (YYYY-MM-DD).
        party_size: The number of people in the party.
        special_requests: Any special requests or dietary requirements.

    Returns:
        The created booking details including the generated booking_id.
    """
    booking = booking_repo.create(
        restaurant_name=restaurant_name,
        user_id=current_user_id.get(),
        date=date,
        party_size=party_size,
        special_requests=special_requests,
    )
    metrics.add_metric(name="BookingCreated", unit=MetricUnit.Count, value=1)
    return booking.model_dump()


@tool
@tracer.capture_method
def delete_booking(booking_id: str) -> str:
    """Delete an existing booking.

    Args:
        booking_id: The unique booking identifier.

    Returns:
        A confirmation message, or an error if the booking was not found.
    """
    deleted = booking_repo.delete(booking_id)
    if deleted:
        return f"Booking {booking_id} successfully deleted."
    return f"No booking found with ID {booking_id}."
