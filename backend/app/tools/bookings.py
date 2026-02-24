"""DynamoDB tools for managing restaurant bookings."""

import uuid

import boto3
from strands import tool

from app.config import TABLE_NAME

# Initialized once per cold start — reused across all warm invocations.
# Never initialize boto3 clients inside tool functions.
_table = boto3.resource("dynamodb").Table(TABLE_NAME)


@tool
def get_booking_details(booking_id: str, restaurant_name: str) -> dict:
    """Get the details of an existing booking.

    Args:
        booking_id: The unique booking identifier.
        restaurant_name: The name of the restaurant.

    Returns:
        The booking details, or a message if not found.
    """
    response = _table.get_item(
        Key={"booking_id": booking_id, "restaurant_name": restaurant_name}
    )
    return response.get("Item", {"error": f"No booking found with ID {booking_id}"})


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
    item: dict = {
        "booking_id": str(uuid.uuid4()),
        "restaurant_name": restaurant_name,
        "user_id": user_id,
        "date": date,
        "party_size": party_size,
    }
    if special_requests:
        item["special_requests"] = special_requests

    _table.put_item(Item=item)
    return item


@tool
def delete_booking(booking_id: str, restaurant_name: str) -> str:
    """Delete an existing booking.

    Args:
        booking_id: The unique booking identifier.
        restaurant_name: The name of the restaurant.

    Returns:
        A confirmation message, or an error if the booking was not found.
    """
    try:
        _table.delete_item(
            Key={"booking_id": booking_id, "restaurant_name": restaurant_name},
            ConditionExpression="attribute_exists(booking_id)",
        )
        return f"Booking {booking_id} at {restaurant_name} successfully deleted."
    except _table.meta.client.exceptions.ConditionalCheckFailedException:
        return f"No booking found with ID {booking_id} at {restaurant_name}."
