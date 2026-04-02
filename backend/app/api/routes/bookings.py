"""REST endpoints for direct booking management."""

from fastapi import APIRouter

from app.exceptions import AppException
from app.models.schemas import Booking
from app.repositories import bookings as booking_repo

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.get("/{booking_id}", response_model=Booking, operation_id="getBooking")
async def get_booking(booking_id: str) -> Booking:
    """Retrieve a booking by ID."""
    booking = booking_repo.get(booking_id)
    if not booking:
        raise AppException(
            status_code=404,
            code="BOOKING_NOT_FOUND",
            message=f"Booking {booking_id} not found.",
        )
    return booking


@router.delete("/{booking_id}", status_code=204, operation_id="deleteBooking")
async def delete_booking(booking_id: str) -> None:
    """Delete a booking by ID."""
    deleted = booking_repo.delete(booking_id)
    if not deleted:
        raise AppException(
            status_code=404,
            code="BOOKING_NOT_FOUND",
            message=f"Booking {booking_id} not found.",
        )
