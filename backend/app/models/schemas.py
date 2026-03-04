"""Pydantic models for API request/response validation."""

from typing import Literal

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str | None = None  # populated once correlation ID middleware is added


class ErrorResponse(BaseModel):
    """Consistent error envelope returned by all HTTP error handlers and SSE error events."""

    error: ErrorDetail


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
