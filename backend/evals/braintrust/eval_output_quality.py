# backend/evals/braintrust/eval_output_quality.py
"""Braintrust offline eval — output quality (clarification, safety, hallucination).

Runs all output-quality test cases through the booking agent and scores each
response with the LLM-as-judge scorer (Bedrock Haiku).

Credentials are loaded automatically from backend/.env by the braintrust CLI.
Copy backend/.env.example → backend/.env and fill in values before running.

Run (from backend/ directory):
    # Push results to Braintrust:
    uv run braintrust eval evals/braintrust/eval_output_quality.py

    # Local iteration — no upload:
    uv run braintrust eval --no-send-logs evals/braintrust/eval_output_quality.py
"""

import dataclasses
import os
from unittest.mock import MagicMock, patch

from braintrust import Eval
from strands import Agent
from strands import tool as strands_tool
from strands_tools import retrieve as _real_retrieve

from app.agent.core import RETRY_STRATEGY, SYSTEM_PROMPT, TOOLS, model
from evals.cases import OUTPUT_QUALITY_CASES
from evals.scorers.output_quality_scorer import booking_output_quality_scorer

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
        model=model,
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
    # Cap concurrency — each case is a Bedrock converse_stream call and Haiku
    # judge call; too many parallel calls saturate Bedrock rate limits.
    max_concurrency=2,
    metadata={
        "eval_type": "output-quality",
        "commit": os.environ.get("GITHUB_SHA", "local"),
    },
)
