"""Unit tests for all FastAPI routes.

The agent and repository are mocked so no AWS calls are made.
"""

import json
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import Booking

client = TestClient(app)

_SAMPLE_BOOKING = Booking(
    booking_id="abc-123",
    restaurant_name="Nonna's Hearth",
    user_id="user-1",
    date="2026-03-01",
    party_size=2,
)

_VALID_CHAT_BODY = {"messages": [{"role": "user", "content": "Hi"}]}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_agent(events: list[dict]) -> MagicMock:
    """Return a mock Agent *class* whose instances yield ``events`` from stream_async.

    Patches ``app.api.routes.chat.Agent`` — the class imported in the route module.
    When the route calls ``Agent(...)``, the mock returns a configured instance
    whose ``stream_async`` is an async generator that yields the given events.
    """

    async def _stream(_message: str):
        for event in events:
            yield event

    instance = MagicMock()
    instance.stream_async = _stream
    return MagicMock(return_value=instance)


def collect_sse_events(response) -> list[dict]:
    """Parse ``data:`` lines from a streaming TestClient response into dicts."""
    events = []
    for line in response.iter_lines():
        if line.startswith("data:"):
            payload = line[6:].strip()  # strip "data: " prefix
            if payload:
                events.append(json.loads(payload))
    return events


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------


def test_security_headers_present():
    """Every response must carry the standard security headers."""
    response = client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-xss-protection"] == "1; mode=block"


def test_correlation_id_returned():
    """X-Request-ID echoed in response when provided; generated when absent."""
    response = client.get("/health", headers={"X-Request-ID": "test-id-123"})
    assert response.headers["x-request-id"] == "test-id-123"

    response = client.get("/health")
    assert "x-request-id" in response.headers


# ---------------------------------------------------------------------------
# GET /bookings/{booking_id}
# ---------------------------------------------------------------------------


def test_get_booking_found():
    with patch("app.repositories.bookings.get", return_value=_SAMPLE_BOOKING):
        response = client.get("/bookings/abc-123?restaurant_name=Nonna%27s+Hearth")

    assert response.status_code == 200
    assert response.json()["booking_id"] == "abc-123"


def test_get_booking_not_found():
    with patch("app.repositories.bookings.get", return_value=None):
        response = client.get("/bookings/missing?restaurant_name=Any")

    assert response.status_code == 404


def test_get_booking_missing_restaurant_name():
    response = client.get("/bookings/abc-123")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /bookings/{booking_id}
# ---------------------------------------------------------------------------


def test_delete_booking_success():
    with patch("app.repositories.bookings.delete", return_value=True):
        response = client.delete("/bookings/abc-123?restaurant_name=Nonna%27s+Hearth")

    assert response.status_code == 204


def test_delete_booking_not_found():
    with patch("app.repositories.bookings.delete", return_value=False):
        response = client.delete("/bookings/missing?restaurant_name=Any")

    assert response.status_code == 404


def test_delete_booking_missing_restaurant_name():
    response = client.delete("/bookings/abc-123")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------


def test_chat_text_delta():
    """Text tokens are forwarded as text-delta events; stream ends with done."""
    mock_agent = make_mock_agent([{"data": "Hello"}, {"data": "!"}])

    with patch("app.api.routes.chat.Agent", mock_agent):
        with client.stream("POST", "/chat", json=_VALID_CHAT_BODY) as response:
            assert response.status_code == 200
            events = collect_sse_events(response)

    types = [e["type"] for e in events]
    assert types == ["text-delta", "text-delta", "done"]
    assert events[0]["delta"] == "Hello"
    assert events[1]["delta"] == "!"


def test_chat_tool_cycle():
    """Full tool cycle: tool-call-start then tool-result then done."""
    mock_agent = make_mock_agent([
        {
            "message": {
                "role": "assistant",
                "content": [{"toolUse": {"toolUseId": "t-1", "name": "get_booking_details", "input": {"booking_id": "abc"}}}],
            }
        },
        {
            "message": {
                "role": "user",
                "content": [{"toolResult": {"toolUseId": "t-1", "status": "success", "content": [{"text": "Found it"}]}}],
            }
        },
        {"data": "Your booking is confirmed."},
    ])

    with patch("app.api.routes.chat.Agent", mock_agent):
        with client.stream("POST", "/chat", json=_VALID_CHAT_BODY) as response:
            events = collect_sse_events(response)

    types = [e["type"] for e in events]
    assert types == ["tool-call-start", "tool-result", "text-delta", "done"]
    assert events[0]["toolCallId"] == "t-1"
    assert events[0]["toolName"] == "get_booking_details"
    assert events[1]["toolCallId"] == "t-1"
    assert events[1]["toolName"] == "get_booking_details"


def test_chat_tool_error():
    """A tool execution failure emits tool-error, not an exception."""
    mock_agent = make_mock_agent([
        {
            "message": {
                "role": "assistant",
                "content": [{"toolUse": {"toolUseId": "t-2", "name": "create_booking", "input": {}}}],
            }
        },
        {
            "message": {
                "role": "user",
                "content": [{"toolResult": {"toolUseId": "t-2", "status": "error", "content": [{"text": "DynamoDB error"}]}}],
            }
        },
    ])

    with patch("app.api.routes.chat.Agent", mock_agent):
        with client.stream("POST", "/chat", json=_VALID_CHAT_BODY) as response:
            events = collect_sse_events(response)

    types = [e["type"] for e in events]
    assert types == ["tool-call-start", "tool-error", "done"]
    assert events[1]["error"] == "DynamoDB error"


def test_chat_timeout_yields_error_then_done():
    """asyncio.TimeoutError yields a user-friendly timeout error, then done."""

    async def _timeout_stream(_message: str):
        raise TimeoutError()
        yield  # makes this an async generator

    instance = MagicMock()
    instance.stream_async = _timeout_stream
    mock_agent = MagicMock(return_value=instance)

    with patch("app.api.routes.chat.Agent", mock_agent):
        with client.stream("POST", "/chat", json=_VALID_CHAT_BODY) as response:
            assert response.status_code == 200
            events = collect_sse_events(response)

    types = [e["type"] for e in events]
    assert types == ["error", "done"]
    assert "timed out" in events[0]["error"].lower()


def test_chat_exception_yields_error_then_done():
    """An unhandled exception in the stream yields error + done — never a bare 500.

    SSE always returns HTTP 200; errors are signalled in-band via the event type.
    """

    async def _erroring_stream(_message: str):
        raise RuntimeError("Bedrock unavailable")
        yield  # makes this an async generator so the route can iterate it

    instance = MagicMock()
    instance.stream_async = _erroring_stream
    mock_agent = MagicMock(return_value=instance)

    with patch("app.api.routes.chat.Agent", mock_agent):
        with client.stream("POST", "/chat", json=_VALID_CHAT_BODY) as response:
            assert response.status_code == 200
            events = collect_sse_events(response)

    types = [e["type"] for e in events]
    assert types == ["error", "done"]
    # Internal exception message must never leak to the client.
    assert "Bedrock unavailable" not in events[0]["error"]
    assert events[0]["error"] == "An unexpected error occurred."


def test_chat_force_stop_yields_error_then_done():
    """force_stop events are forwarded as error events."""
    mock_agent = make_mock_agent([
        {"force_stop": True, "force_stop_reason": "Token limit exceeded"},
    ])

    with patch("app.api.routes.chat.Agent", mock_agent):
        with client.stream("POST", "/chat", json=_VALID_CHAT_BODY) as response:
            events = collect_sse_events(response)

    types = [e["type"] for e in events]
    assert "error" in types
    assert types[-1] == "done"


def test_chat_missing_messages_field():
    """messages is required — omitting it returns 422."""
    response = client.post("/chat", json={})
    assert response.status_code == 422


def test_chat_message_content_too_long():
    """A message exceeding 4 096 characters is rejected before hitting the agent."""
    oversized = {"messages": [{"role": "user", "content": "x" * 4097}]}
    response = client.post("/chat", json=oversized)
    assert response.status_code == 422


def test_chat_too_many_messages():
    """More than 50 messages in one request is rejected before hitting the agent."""
    msg = {"role": "user", "content": "Hi"}
    too_many = {"messages": [msg] * 51}
    response = client.post("/chat", json=too_many)
    assert response.status_code == 422


def test_chat_done_is_always_last():
    """done is emitted even when the stream produces no other events."""
    mock_agent = make_mock_agent([])

    with patch("app.api.routes.chat.Agent", mock_agent):
        with client.stream("POST", "/chat", json=_VALID_CHAT_BODY) as response:
            events = collect_sse_events(response)

    assert events == [{"type": "done"}]
