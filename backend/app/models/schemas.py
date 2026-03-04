"""Pydantic models for API request/response validation."""

from typing import Literal

from pydantic import BaseModel, Field

from app.config import (
    BOOKING_MAX_SPECIAL_REQUESTS_LENGTH,
    CHAT_MAX_MESSAGE_LENGTH,
    CHAT_MAX_MESSAGES,
)


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
    content: str = Field(
        max_length=CHAT_MAX_MESSAGE_LENGTH,
        description="Message text. Maximum 4 096 characters.",
        examples=["What restaurants do you have downtown?"],
    )


class ChatApiRequest(BaseModel):
    """Request body for POST /chat."""

    messages: list[ChatApiMessage] = Field(
        max_length=CHAT_MAX_MESSAGES,
        description="Conversation history. Maximum 50 messages.",
    )


class Booking(BaseModel):
    """A restaurant reservation record."""

    booking_id: str
    restaurant_name: str
    user_id: str
    date: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Reservation date in YYYY-MM-DD format.",
        examples=["2026-06-15"],
    )
    party_size: int = Field(
        ge=1,
        le=20,
        description="Number of guests. Between 1 and 20.",
        examples=[2],
    )
    special_requests: str | None = Field(
        default=None,
        max_length=BOOKING_MAX_SPECIAL_REQUESTS_LENGTH,
        description="Optional dietary or seating notes. Maximum 500 characters.",
    )
