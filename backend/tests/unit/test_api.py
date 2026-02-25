"""Unit tests for all FastAPI routes.

The agent and repository are mocked so no AWS calls are made.
"""

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


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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


def test_chat_success():
    mock_agent = MagicMock(return_value="Hello! How can I help?")
    with patch("app.api.routes.chat.get_agent", return_value=mock_agent):
        response = client.post("/chat", json={"message": "Hello", "session_id": "s1"})

    assert response.status_code == 200
    data = response.json()
    assert data["response"] == "Hello! How can I help?"
    assert data["session_id"] == "s1"


def test_chat_no_session_id():
    mock_agent = MagicMock(return_value="Response without session")
    with patch("app.api.routes.chat.get_agent", return_value=mock_agent):
        response = client.post("/chat", json={"message": "Hi"})

    assert response.status_code == 200
    assert response.json()["session_id"] is None


def test_chat_missing_message():
    response = client.post("/chat", json={"session_id": "s1"})
    assert response.status_code == 422
