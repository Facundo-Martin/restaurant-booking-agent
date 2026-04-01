# backend/evals/braintrust/eval_output_quality.py
"""Braintrust offline eval — output quality (clarification, safety, hallucination).

Runs all output-quality test cases through the booking agent and scores each
response with the LLM-as-judge scorer (Bedrock Haiku).

Copy backend/.env.example → backend/.env and fill in values, then run:

Run (from repo root — recommended):
    pnpm eval:braintrust:quality

Run (from backend/ directory):
    # --env-file handles BRAINTRUST_API_KEY auth and SST_RESOURCE_* stubs:
    uv run braintrust eval --env-file .env evals/braintrust/eval_output_quality.py

    # Local iteration — no upload:
    uv run braintrust eval --env-file .env --no-send-logs evals/braintrust/eval_output_quality.py
"""

import dataclasses
import os
from unittest.mock import MagicMock, patch

from braintrust import Eval
from dotenv import load_dotenv
from strands import Agent
from strands import tool as strands_tool
from strands.models import BedrockModel
from strands_tools import retrieve as _real_retrieve

# Load SST resource stubs from .env before importing app modules.
# The braintrust CLI runs this file in its own process; SST_RESOURCE_* vars
# must be present in os.environ before app.config is imported.
load_dotenv()

from app.agent.core import RETRY_STRATEGY, SYSTEM_PROMPT, TOOLS  # noqa: E402
from evals.cases import OUTPUT_QUALITY_CASES  # noqa: E402
from evals.scorers.output_quality_scorer import (  # noqa: E402
    booking_output_quality_scorer,
)

# Haiku: higher Bedrock throughput limits than Sonnet 3.7, still follows system
# prompt rules reliably. Output-quality cases test behavioral compliance, not
# generation quality differences between model tiers.
_AGENT_MODEL = BedrockModel(
    model_id="us.anthropic.claude-3-5-haiku-20241022-v1:0",
    # temperature=0 for deterministic responses — without it the agent
    # inconsistently skips current_time, guesses the date from training
    # context, and mis-validates the 60-day booking window.
    temperature=0,
    additional_request_fields={"thinking": {"type": "disabled"}},
)

# ---------------------------------------------------------------------------
# Canned tool responses — deterministic, no real Knowledge Base calls
# ---------------------------------------------------------------------------
_FAKE_RESTAURANTS = (
    "Available restaurants: Nonna's Hearth (Italian, open daily, accepts reservations), "
    "Bistro Parisienne (French, closed Mondays, accepts reservations), "
    "Sakura Garden (Japanese, open daily, accepts reservations)."
)
_FAKE_BOOKING = {
    "booking_id": "B-456",
    "restaurant_name": "Nonna's Hearth",
    "date": "2026-03-20",
    "party_size": 2,
    "status": "confirmed",
}


@strands_tool
def retrieve(query: str) -> str:
    """Search the knowledge base for restaurants, menus, and availability."""
    return _FAKE_RESTAURANTS


# Replace the real retrieve in the tool list with the deterministic stub.
_EVAL_TOOLS = [retrieve if t is _real_retrieve else t for t in TOOLS]


# ---------------------------------------------------------------------------
# Task function
# ---------------------------------------------------------------------------


async def run_agent(input: str) -> str:  # noqa: A002
    """Run the booking agent with mocked external dependencies, return response."""
    mock_booking = MagicMock()
    mock_booking.model_dump.return_value = _FAKE_BOOKING
    mock_repo = MagicMock()
    mock_repo.create.return_value = mock_booking
    mock_repo.get.return_value = mock_booking
    mock_repo.delete.return_value = True

    agent = Agent(
        model=_AGENT_MODEL,
        tools=_EVAL_TOOLS,
        system_prompt=SYSTEM_PROMPT,
        callback_handler=None,
        retry_strategy=RETRY_STRATEGY,
    )

    with patch("app.tools.bookings.booking_repo", mock_repo):
        response = await agent.invoke_async(input)

    return str(response)


# ---------------------------------------------------------------------------
# Eval — cases sourced from evals/cases.py (single source of truth)
# Adapter: drop 'id' — Braintrust assigns its own record IDs
# ---------------------------------------------------------------------------

_experiment_name = f"output-quality-{os.environ.get('GITHUB_SHA', 'local')[:8]}"

Eval(
    "Restaurant Booking — Output Quality",
    data=[
        {k: v for k, v in dataclasses.asdict(c).items() if k != "id"}
        for c in OUTPUT_QUALITY_CASES
    ],
    task=run_agent,
    scores=[booking_output_quality_scorer],
    experiment_name=_experiment_name,
    max_concurrency=2,
    metadata={
        "eval_type": "output-quality",
        "commit": os.environ.get("GITHUB_SHA", "local"),
    },
)
