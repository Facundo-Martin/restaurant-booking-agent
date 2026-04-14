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
    uv run braintrust eval --env-file .env evals/modules/booking/braintrust/eval_trajectory.py

    # Local iteration — no upload:
    uv run braintrust eval --env-file .env --no-send-logs evals/modules/booking/braintrust/eval_trajectory.py
"""

import os
from unittest.mock import MagicMock, patch

from braintrust import Eval
from dotenv import load_dotenv
from strands import Agent
from strands import tool as strands_tool
from strands.models import BedrockModel
from strands_evals.extractors import tools_use_extractor
from strands_tools import retrieve as _real_retrieve

# Load SST resource stubs from .env before importing app modules.
# The braintrust CLI runs this file in its own process; SST_RESOURCE_* vars
# must be present in os.environ before app.config is imported.
load_dotenv()

from app.agent.core import RETRY_STRATEGY, TOOLS  # noqa: E402
from app.agent.prompt_loader import load_system_prompt_bundle  # noqa: E402
from evals.config.braintrust.config import (  # noqa: E402
    BRAINTRUST_PROJECT,
    EVAL_AGENT_MODEL_ID,
    TRAJECTORY_DATASET,
    TRAJECTORY_SCORER_VERSION,
)
from evals.config.braintrust.datasets import (  # noqa: E402
    assert_case_count_matches,
    load_dataset,
)
from evals.config.braintrust.manifest import EvalMetadata  # noqa: E402
from evals.config.braintrust.scorers.trajectory_scorer import (  # noqa: E402
    trajectory_scorer,
)

# TODO: TRAJECTORY_CASES not yet exported from discovery.cases — placeholder eval
from evals.modules.discovery.cases import (  # noqa: E402
    DISCOVERY_CASES as TRAJECTORY_CASES,
)

# ---------------------------------------------------------------------------
# Dataset — always latest, guarded against empty results and case drift
# ---------------------------------------------------------------------------
_dataset, _rows = load_dataset(BRAINTRUST_PROJECT, TRAJECTORY_DATASET, version=None)
assert_case_count_matches(_rows, TRAJECTORY_CASES, TRAJECTORY_DATASET)

# ---------------------------------------------------------------------------
# Agent model
# ---------------------------------------------------------------------------
# Haiku: higher Bedrock throughput limits than Sonnet 3.7, well-suited for
# tool-routing correctness tests which don't require Sonnet-level reasoning.
_AGENT_MODEL = BedrockModel(
    model_id=EVAL_AGENT_MODEL_ID,
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

# Load the prompt once for the entire eval run so all cases use the same snapshot.
_PROMPT_BUNDLE = load_system_prompt_bundle()


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
        system_prompt=_PROMPT_BUNDLE.text,
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

_commit = os.environ.get("GITHUB_SHA", "local")
_experiment_name = f"trajectory-{_commit[:8]}"

_metadata = EvalMetadata(
    project_name=BRAINTRUST_PROJECT,
    dataset_name=TRAJECTORY_DATASET,
    prompt_slug=_PROMPT_BUNDLE.slug,
    prompt_version=_PROMPT_BUNDLE.version,
    prompt_environment=_PROMPT_BUNDLE.environment,
    agent_model_id=EVAL_AGENT_MODEL_ID,
    scorer_version=TRAJECTORY_SCORER_VERSION,
    commit=_commit,
)

Eval(
    BRAINTRUST_PROJECT,
    data=_dataset,
    task=run_agent_with_trajectory,
    scores=[trajectory_scorer],
    experiment_name=_experiment_name,
    max_concurrency=1,
    metadata=_metadata.to_metadata(),
)
