# backend/evals/braintrust/eval_trajectory.py
"""Braintrust offline eval — tool trajectory (tool routing correctness).

The task function returns both the agent's text response and the actual tool
trajectory (list of tool names called). The trajectory scorer then compares
actual vs. expected deterministically — no LLM call, no cost.

Copy backend/.env.example → backend/.env and fill in values, then run:

Run (from repo root — recommended):
    pnpm eval:braintrust:trajectory

Run (from backend/ directory):
    # --env-file handles BRAINTRUST_API_KEY auth and SST_RESOURCE_* stubs:
    uv run braintrust eval --env-file .env evals/braintrust/eval_trajectory.py

    # Local iteration — no upload:
    uv run braintrust eval --env-file .env --no-send-logs evals/braintrust/eval_trajectory.py
"""

import os
from unittest.mock import MagicMock, patch

from dotenv import load_dotenv
from strands import Agent
from strands import tool as strands_tool
from strands.models import BedrockModel
from strands_evals.extractors import tools_use_extractor
from strands_tools import retrieve as _real_retrieve

import braintrust
from braintrust import Eval

# Load SST resource stubs from .env before importing app modules.
# The braintrust CLI runs this file in its own process; SST_RESOURCE_* vars
# must be present in os.environ before app.config is imported.
load_dotenv()

from app.agent.core import RETRY_STRATEGY, TOOLS  # noqa: E402
from app.agent.prompt_loader import load_system_prompt  # noqa: E402
from evals.braintrust.config import (  # noqa: E402
    BRAINTRUST_PROJECT,
    TRAJECTORY_DATASET,
)
from evals.scorers.trajectory_scorer import trajectory_scorer  # noqa: E402

# Haiku: higher Bedrock throughput limits than Sonnet 3.7, well-suited for
# tool-routing correctness tests which don't require Sonnet-level reasoning.
_AGENT_MODEL = BedrockModel(
    model_id="us.anthropic.claude-3-5-haiku-20241022-v1:0",
    # temperature=0 for deterministic tool routing — evals must be repeatable.
    temperature=0,
    additional_request_fields={"thinking": {"type": "disabled"}},
)

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


# Replace the real retrieve in the tool list with the deterministic stub.
_EVAL_TOOLS = [retrieve if t is _real_retrieve else t for t in TOOLS]
_DATASET = braintrust.init_dataset(
    project=BRAINTRUST_PROJECT,
    name=TRAJECTORY_DATASET,
)


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
        model=_AGENT_MODEL,
        tools=_EVAL_TOOLS,
        system_prompt=load_system_prompt(),
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
# Eval — execute against the managed Braintrust dataset seeded from evals/cases.py
# ---------------------------------------------------------------------------

_experiment_name = f"trajectory-{os.environ.get('GITHUB_SHA', 'local')[:8]}"

Eval(
    BRAINTRUST_PROJECT,
    data=_DATASET,
    task=run_agent_with_trajectory,
    scores=[trajectory_scorer],
    experiment_name=_experiment_name,
    max_concurrency=1,
    metadata={
        "project_name": BRAINTRUST_PROJECT,
        "dataset_name": TRAJECTORY_DATASET,
        "eval_type": "trajectory",
        "commit": os.environ.get("GITHUB_SHA", "local"),
    },
)
