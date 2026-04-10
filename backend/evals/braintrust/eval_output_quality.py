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

from app.agent.core import RETRY_STRATEGY, TOOLS  # noqa: E402
from app.agent.prompt_loader import load_system_prompt_bundle  # noqa: E402
from evals.config.braintrust.config import (  # noqa: E402
    BRAINTRUST_PROJECT,
    EVAL_AGENT_MODEL_ID,
    EVAL_JUDGE_MODEL_ID,
    OUTPUT_QUALITY_DATASET,
    OUTPUT_QUALITY_SCORER_VERSION,
)
from evals.config.braintrust.datasets import (  # noqa: E402
    assert_case_count_matches,
    load_dataset,
)
from evals.config.braintrust.manifest import EvalMetadata  # noqa: E402
from evals.config.braintrust.scorers.output_quality_scorer import (  # noqa: E402
    booking_output_quality_scorer,
)
from evals.discovery.cases import OUTPUT_QUALITY_CASES  # noqa: E402

# ---------------------------------------------------------------------------
# Dataset — always latest, guarded against empty results and case drift
# ---------------------------------------------------------------------------
_dataset, _rows = load_dataset(BRAINTRUST_PROJECT, OUTPUT_QUALITY_DATASET, version=None)
assert_case_count_matches(_rows, OUTPUT_QUALITY_CASES, OUTPUT_QUALITY_DATASET)

# ---------------------------------------------------------------------------
# Agent model
# ---------------------------------------------------------------------------
# Haiku: higher Bedrock throughput limits than Sonnet 3.7, still follows system
# prompt rules reliably. Output-quality cases test behavioral compliance, not
# generation quality differences between model tiers.
_AGENT_MODEL = BedrockModel(
    model_id=EVAL_AGENT_MODEL_ID,
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

# Load the prompt once for the entire eval run so all cases use the same snapshot.
_PROMPT_BUNDLE = load_system_prompt_bundle()


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
        system_prompt=_PROMPT_BUNDLE.text,
        callback_handler=None,
        retry_strategy=RETRY_STRATEGY,
    )

    with patch("app.tools.bookings.booking_repo", mock_repo):
        response = await agent.invoke_async(input)

    return str(response)


# ---------------------------------------------------------------------------
# Eval — execute against the managed Braintrust dataset seeded from evals/cases.py
# ---------------------------------------------------------------------------

_commit = os.environ.get("GITHUB_SHA", "local")
_experiment_name = f"output-quality-{_commit[:8]}"

_metadata = EvalMetadata(
    project_name=BRAINTRUST_PROJECT,
    dataset_name=OUTPUT_QUALITY_DATASET,
    prompt_slug=_PROMPT_BUNDLE.slug,
    prompt_version=_PROMPT_BUNDLE.version,
    prompt_environment=_PROMPT_BUNDLE.environment,
    agent_model_id=EVAL_AGENT_MODEL_ID,
    scorer_version=OUTPUT_QUALITY_SCORER_VERSION,
    commit=_commit,
    judge_model_id=EVAL_JUDGE_MODEL_ID,
)

Eval(
    BRAINTRUST_PROJECT,
    data=_dataset,
    task=run_agent,
    scores=[booking_output_quality_scorer],
    experiment_name=_experiment_name,
    max_concurrency=1,
    metadata=_metadata.to_metadata(),
)
