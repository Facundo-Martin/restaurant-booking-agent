"""Integration tests: HTTP layer against the real deployed test stage.

Run:
    INTEGRATION_API_URL=https://... \\
    INTEGRATION_CHAT_URL=https://... \\
    uv run pytest tests/integration/test_api.py -v
"""

import json

import httpx
import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health_returns_200(api_url):
    """Deployed health endpoint returns 200 with ok status."""
    response = httpx.get(f"{api_url}/health", timeout=10.0)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["dependencies"]["dynamodb"] == "ok"
    assert "bedrock" in body["not_checked"]


def test_health_has_security_headers(api_url):
    """Security headers are present on every response."""
    response = httpx.get(f"{api_url}/health", timeout=10.0)
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"


# ---------------------------------------------------------------------------
# Chat stream
# ---------------------------------------------------------------------------


def test_chat_stream_terminates_with_done(chat_url):
    """POST /chat always ends with a done event regardless of content."""
    payload = {"messages": [{"role": "user", "content": "Hi"}]}
    last_type = None

    with httpx.Client(timeout=60.0) as client:
        with client.stream("POST", f"{chat_url}/chat", json=payload) as response:
            assert response.status_code == 200
            for line in response.iter_lines():
                if line.startswith("data:"):
                    raw = line[6:].strip()
                    if raw:
                        last_type = json.loads(raw).get("type")

    assert last_type == "done"


def test_chat_rejects_oversized_message(chat_url):
    """A message body exceeding 4 096 characters is rejected with 422."""
    oversized = {"messages": [{"role": "user", "content": "x" * 4097}]}
    response = httpx.post(f"{chat_url}/chat", json=oversized, timeout=10.0)
    assert response.status_code == 422


def test_chat_rejects_missing_messages(chat_url):
    """Omitting the messages field returns 422."""
    response = httpx.post(f"{chat_url}/chat", json={}, timeout=10.0)
    assert response.status_code == 422
