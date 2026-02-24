"""Strands agent factory for the restaurant booking assistant."""

import os

from strands import Agent
from strands.models import BedrockModel
from strands_tools import current_time, retrieve

from app.config import KB_ID
from app.tools.bookings import create_booking, delete_booking, get_booking_details

# The retrieve tool reads KNOWLEDGE_BASE_ID from the environment.
# Set it once at module load so it's available before the agent is created.
os.environ["KNOWLEDGE_BASE_ID"] = KB_ID

SYSTEM_PROMPT = """You are a helpful restaurant booking assistant. You help users:
- Discover restaurants and browse menus using your knowledge base
- Make, view, and cancel reservations

Always confirm booking details with the user before creating a reservation.
When a user asks about restaurants or menus, use the retrieve tool to search
the knowledge base. Use current_time when date context is needed.
"""

# Cached at module level — created once per cold start, reused on warm invocations.
# BedrockModel is stateless; there is no reason to recreate it per request.
_agent = Agent(
    model=BedrockModel(
        model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
        additional_request_fields={"thinking": {"type": "disabled"}},
    ),
    system_prompt=SYSTEM_PROMPT,
    tools=[retrieve, current_time, get_booking_details, create_booking, delete_booking],
)


def get_agent() -> Agent:
    """Return the module-level cached agent instance."""
    return _agent
