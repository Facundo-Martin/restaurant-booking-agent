"""Pydantic models for API request/response validation."""

from typing import Literal

from pydantic import BaseModel


class ChatApiMessage(BaseModel):
    """A single message in the conversation history."""

    role: Literal["user", "assistant"]
    content: str


class ChatApiRequest(BaseModel):
    """Request body for POST /chat."""

    messages: list[ChatApiMessage]


class Booking(BaseModel):
    """A restaurant reservation record."""

    booking_id: str
    restaurant_name: str
    user_id: str
    date: str
    party_size: int
    special_requests: str | None = None
