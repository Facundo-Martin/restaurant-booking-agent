"""DynamoDB data access layer for bookings.

All raw boto3 calls and DynamoDB key strings live here.
Callers receive typed Booking objects — never raw dicts.
"""

import uuid
from typing import Any

import boto3

from app.config import TABLE_NAME
from app.models.schemas import Booking

# Single table handle shared by the REST routes and the Strands agent tools.
# Lazily initialized so imports stay side-effect free in tests and scripts.
_TABLE_HANDLE: Any | None = None


def _get_table():
    """Return the cached DynamoDB table handle, creating it on first use."""
    global _TABLE_HANDLE  # pylint: disable=global-statement
    if _TABLE_HANDLE is None:
        _TABLE_HANDLE = boto3.resource("dynamodb").Table(TABLE_NAME)
    return _TABLE_HANDLE


def get(booking_id: str) -> Booking | None:
    """Fetch a booking by booking_id."""
    response = _get_table().get_item(Key={"booking_id": booking_id})
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
    _get_table().put_item(Item=booking.model_dump(exclude_none=True))
    return booking


def delete(booking_id: str) -> bool:
    """Delete a booking. Returns True if deleted, False if not found."""
    table = _get_table()
    try:
        table.delete_item(
            Key={"booking_id": booking_id},
            ConditionExpression="attribute_exists(booking_id)",
        )
        return True
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return False


def ping() -> None:
    """Lightweight DynamoDB reachability check — raises on any error."""
    _get_table().meta.client.describe_table(TableName=TABLE_NAME)
