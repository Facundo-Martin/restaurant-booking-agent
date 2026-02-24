"""REST endpoints for direct booking management."""

import boto3
from fastapi import APIRouter, HTTPException, Query

from app.config import TABLE_NAME
from app.models.schemas import Booking

router = APIRouter(prefix="/bookings", tags=["bookings"])

# Module-level client — reused across warm invocations
_table = boto3.resource("dynamodb").Table(TABLE_NAME)


@router.get("/{booking_id}", response_model=Booking)
async def get_booking(
    booking_id: str,
    restaurant_name: str = Query(..., description="Required — part of the composite key"),
) -> Booking:
    """Retrieve a booking by ID.

    restaurant_name is required as a query parameter because DynamoDB's
    composite key requires both booking_id (hash) and restaurant_name (range).
    """
    response = _table.get_item(
        Key={"booking_id": booking_id, "restaurant_name": restaurant_name}
    )
    item = response.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail=f"Booking {booking_id} not found.")
    return item


@router.delete("/{booking_id}", status_code=204)
async def delete_booking(
    booking_id: str,
    restaurant_name: str = Query(..., description="Required — part of the composite key"),
) -> None:
    """Delete a booking by ID.

    restaurant_name is required as a query parameter because DynamoDB's
    composite key requires both booking_id (hash) and restaurant_name (range).
    """
    try:
        _table.delete_item(
            Key={"booking_id": booking_id, "restaurant_name": restaurant_name},
            ConditionExpression="attribute_exists(booking_id)",
        )
    except _table.meta.client.exceptions.ConditionalCheckFailedException:
        raise HTTPException(status_code=404, detail=f"Booking {booking_id} not found.")
