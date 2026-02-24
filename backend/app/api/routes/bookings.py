"""REST endpoints for direct booking management."""

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import Booking
from app.repositories import bookings as booking_repo

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.get("/{booking_id}", response_model=Booking)
async def get_booking(
    booking_id: str,
    restaurant_name: str = Query(..., description="Required — part of the composite key"),
) -> Booking:
    """Retrieve a booking by ID.

    restaurant_name is required as a query parameter because DynamoDB's
    composite key requires both booking_id (hash) and restaurant_name (range).
    """
    booking = booking_repo.get(booking_id, restaurant_name)
    if not booking:
        raise HTTPException(status_code=404, detail=f"Booking {booking_id} not found.")
    return booking


@router.delete("/{booking_id}", status_code=204)
async def delete_booking(
    booking_id: str,
    restaurant_name: str = Query(..., description="Required — part of the composite key"),
) -> None:
    """Delete a booking by ID.

    restaurant_name is required as a query parameter because DynamoDB's
    composite key requires both booking_id (hash) and restaurant_name (range).
    """
    deleted = booking_repo.delete(booking_id, restaurant_name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Booking {booking_id} not found.")
