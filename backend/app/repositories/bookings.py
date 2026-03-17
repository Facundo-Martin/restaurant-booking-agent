"""DynamoDB data access layer for bookings.

All raw boto3 calls and DynamoDB key strings live here.
Callers receive typed Booking objects — never raw dicts.
"""

import uuid

import boto3
from boto3.dynamodb.conditions import Key

from app.config import TABLE_NAME
from app.models.schemas import Booking

# Single client shared by both the REST routes and the Strands agent tools.
# Initialized once per cold start — never inside a function.
_table = boto3.resource("dynamodb").Table(TABLE_NAME)


def get(booking_id: str, restaurant_name: str | None = None) -> Booking | None:
    """Fetch a booking by booking_id.

    If restaurant_name is provided uses get_item (exact key lookup).
    Otherwise falls back to query on the partition key alone — useful when
    the caller only knows the booking ID.
    """
    if restaurant_name is not None:
        response = _table.get_item(
            Key={"booking_id": booking_id, "restaurant_name": restaurant_name}
        )
        item = response.get("Item")
    else:
        response = _table.query(KeyConditionExpression=Key("booking_id").eq(booking_id))
        items = response.get("Items", [])
        item = items[0] if items else None
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


def ping() -> None:
    """Lightweight DynamoDB reachability check — raises on any error."""
    _table.meta.client.describe_table(TableName=TABLE_NAME)
