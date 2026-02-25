"""DynamoDB data access layer for bookings.

All raw boto3 calls and DynamoDB key strings live here.
Callers receive typed Booking objects — never raw dicts.
"""

import uuid

import boto3

from app.config import TABLE_NAME
from app.models.schemas import Booking

# Single client shared by both the REST routes and the Strands agent tools.
# Initialized once per cold start — never inside a function.
_table = boto3.resource("dynamodb").Table(TABLE_NAME)


def get(booking_id: str, restaurant_name: str) -> Booking | None:
    """Fetch a booking by composite key. Returns None if not found."""
    response = _table.get_item(
        Key={"booking_id": booking_id, "restaurant_name": restaurant_name}
    )
    item = response.get("Item")
    return Booking.model_validate(item) if item else None


def create(
    restaurant_name: str,
    user_id: str,
    date: str,
    party_size: int,
    special_requests: str | None = None,
) -> Booking:
    """Persist a new booking and return it with the generated ID."""
    booking = Booking(
        booking_id=str(uuid.uuid4()),
        restaurant_name=restaurant_name,
        user_id=user_id,
        date=date,
        party_size=party_size,
        special_requests=special_requests,
    )
    _table.put_item(Item=booking.model_dump(exclude_none=True))
    return booking


def delete(booking_id: str, restaurant_name: str) -> bool:
    """Delete a booking. Returns True if deleted, False if not found."""
    try:
        _table.delete_item(
            Key={"booking_id": booking_id, "restaurant_name": restaurant_name},
            ConditionExpression="attribute_exists(booking_id)",
        )
        return True
    except _table.meta.client.exceptions.ConditionalCheckFailedException:
        return False
