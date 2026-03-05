"""Prompt regression tests — agent routing and confirmation behaviour.

These tests call agent.stream_async() directly with real Bedrock — no HTTP
layer is involved. Booking tools are patched to return canned data so no real
DynamoDB or Knowledge Base is required; the retrieve tool is patched for the
same reason. What we are testing is the LLM's routing decisions given the
system prompt and tool schemas.

Failures here signal that a model version bump or system-prompt edit has
changed the agent's behaviour in a way that affects users.

Run (requires AWS credentials with Bedrock InvokeModel access):
    uv run pytest tests/integration/test_agent.py -v
"""

from unittest.mock import MagicMock, patch

import pytest
from strands import Agent

from app.agent import SYSTEM_PROMPT, TOOLS, model

pytestmark = pytest.mark.agent

_FAKE_RESTAURANTS = (
    "Available restaurants: Nonna's Hearth (Italian), Bistro Parisienne (French)."
)


def _tool_names(events: list) -> list[str]:
    """Return the names of all tools the model decided to invoke."""
    names = []
    for event in events:
        msg = event.get("message", {})
        if msg.get("role") == "assistant":
            for block in msg.get("content", []):
                if "toolUse" in block:
                    names.append(block["toolUse"]["name"])
    return names


async def test_restaurant_query_calls_retrieve():
    """A question about available restaurants must trigger the retrieve tool.

    If this fails after a model or prompt change, the agent is no longer
    routing restaurant-discovery queries to the Knowledge Base.
    """
    agent = Agent(model=model, tools=TOOLS, system_prompt=SYSTEM_PROMPT)

    mock_retrieve = MagicMock(return_value=_FAKE_RESTAURANTS)
    with patch("strands_tools.retrieve", mock_retrieve):
        events = [e async for e in agent.stream_async("What restaurants do you have?")]

    assert "retrieve" in _tool_names(events), (
        "Agent did not call retrieve — check system prompt and tool schema"
    )


async def test_create_booking_not_called_without_confirmation():
    """Agent must not call create_booking on a bare first-turn booking request.

    The system prompt requires the agent to confirm booking details with the
    user before creating a reservation. A vague 'book a table' message should
    produce a clarifying question, not an immediate create_booking call.

    If this fails, the system prompt's confirmation instruction has been lost
    or overridden by the model.
    """
    agent = Agent(model=model, tools=TOOLS, system_prompt=SYSTEM_PROMPT)

    events = [e async for e in agent.stream_async("Book a table for me tonight")]

    assert "create_booking" not in _tool_names(events), (
        "Agent called create_booking without confirmation — system prompt may have regressed"
    )
