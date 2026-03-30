# backend/evals/braintrust/eval_trajectory.py
"""Braintrust offline eval — tool trajectory (tool routing correctness).

The task function returns both the agent's text response and the actual tool
trajectory (list of tool names called). The trajectory scorer then compares
actual vs. expected deterministically — no LLM call, no cost.

Credentials are loaded automatically from backend/.env by the braintrust CLI.
Copy backend/.env.example → backend/.env and fill in values before running.

Run (from backend/ directory):
    # Push results to Braintrust:
    uv run braintrust eval evals/braintrust/eval_trajectory.py

    # Local iteration — no upload:
    uv run braintrust eval --no-send-logs evals/braintrust/eval_trajectory.py
"""

import dataclasses
import os
from unittest.mock import MagicMock, patch

from braintrust import Eval
from strands import Agent
from strands import tool as strands_tool
from strands_evals.extractors import tools_use_extractor
from strands_tools import retrieve as _real_retrieve

from app.agent.core import RETRY_STRATEGY, SYSTEM_PROMPT, TOOLS, model
from evals.cases import TRAJECTORY_CASES
from evals.scorers.trajectory_scorer import trajectory_scorer

# ---------------------------------------------------------------------------
# Canned tool responses
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


_EVAL_TOOLS = [retrieve if t is _real_retrieve else t for t in TOOLS]


# ---------------------------------------------------------------------------
# Task function
# ---------------------------------------------------------------------------


async def run_agent_with_trajectory(input: str) -> dict:  # noqa: A002
    """Run the booking agent and return both the response and the tool trajectory."""
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

    actual_trajectory = tools_use_extractor.extract_agent_tools_used_from_messages(
        agent.messages
    )
    return {"output": str(response), "trajectory": actual_trajectory}


# ---------------------------------------------------------------------------
# Eval — cases sourced from evals/cases.py (single source of truth)
# Adapter: drop 'id' — Braintrust assigns its own record IDs
# ---------------------------------------------------------------------------

_experiment_name = f"trajectory-{os.environ.get('GITHUB_SHA', 'local')[:8]}"

Eval(
    "Restaurant Booking — Trajectory",
    data=[
        {k: v for k, v in dataclasses.asdict(c).items() if k != "id"}
        for c in TRAJECTORY_CASES
    ],
    task=run_agent_with_trajectory,
    scores=[trajectory_scorer],
    experiment_name=_experiment_name,
    max_concurrency=2,
    metadata={
        "eval_type": "trajectory",
        "commit": os.environ.get("GITHUB_SHA", "local"),
    },
)
