"""Pydantic models for API request/response validation."""

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Incoming chat message from the user."""

    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    """Agent response returned to the user."""

    response: str
    session_id: str | None = None


class Booking(BaseModel):
    """A restaurant reservation record."""

    booking_id: str
    restaurant_name: str
    user_id: str
    date: str
    party_size: int
    special_requests: str | None = None
