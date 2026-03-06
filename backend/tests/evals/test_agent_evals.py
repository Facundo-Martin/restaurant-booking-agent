"""Strands Evals SDK evaluation suite — agent routing, trajectory, and response quality.

Uses the strands-agents-evals framework with real Bedrock LLM calls.
Booking tools are mocked so no DynamoDB or Knowledge Base is required.

Run (requires AWS credentials with Bedrock InvokeModel access):
    uv run pytest tests/evals/ -m agent -v
"""

from unittest.mock import MagicMock, patch

import pytest
from strands import Agent
from strands_evals import Case, Experiment
from strands_evals.evaluators import OutputEvaluator, TrajectoryEvaluator
from strands_evals.extractors import tools_use_extractor

from app.agent import SYSTEM_PROMPT, TOOLS, model

pytestmark = pytest.mark.agent

# ---------------------------------------------------------------------------
# Canned tool responses — deterministic inputs for consistent eval scoring
# ---------------------------------------------------------------------------
_FAKE_RESTAURANTS = (
    "Available restaurants: Nonna's Hearth (Italian, open daily, accepts reservations), "
    "Bistro Parisienne (French, closed Mondays, accepts reservations)."
)

# ---------------------------------------------------------------------------
# Evaluators — defined once, shared across experiments
# ---------------------------------------------------------------------------
_trajectory_evaluator = TrajectoryEvaluator(
    rubric="""
    Evaluate whether the agent followed the correct tool call sequence for the task.

    Rules:
    - Restaurant discovery queries: the retrieve tool MUST be called.
    - Booking creation: retrieve MUST be called before create_booking.
      On a vague first-turn request ("book a table"), the agent should ask for
      clarification — NOT immediately call create_booking.
    - Booking deletion: get_booking_details MUST be called before delete_booking.
    - Off-topic requests: no booking tools should be called.

    Use the built-in scoring tools (exact_match_scorer, in_order_match_scorer,
    any_order_match_scorer) to verify trajectories where applicable.

    Score 1.0 if the tool sequence is fully correct.
    Score 0.5 if tools were used but in a suboptimal or incomplete order.
    Score 0.0 if a critical step is missing, the wrong tools are used, or
               booking tools are called without the required prior steps.
    """,
    include_inputs=True,
)

_response_evaluator = OutputEvaluator(
    rubric="""
    The agent is a restaurant booking assistant. Evaluate whether the response:
    1. Directly addresses the user's question or request.
    2. Does NOT create a booking without first confirming details with the user.
    3. Stays on-topic (restaurants and bookings only) — politely declines off-topic requests.
    4. Does NOT invent restaurant names, menu items, or booking details not present
       in the conversation or tool results.

    Score 1.0 if all criteria are fully met.
    Score 0.5 if there are minor issues (e.g., slightly verbose, minor hallucination).
    Score 0.0 if the agent violates the confirmation rule, fabricates data,
               or engages with off-topic content.
    """,
    include_inputs=True,
)

# ---------------------------------------------------------------------------
# Task function — runs the agent with all external dependencies mocked
# ---------------------------------------------------------------------------


def _run_agent(case: Case) -> dict:
    """Run the booking agent against a single eval case.

    Patches the retrieve tool (Knowledge Base) and booking_repo (DynamoDB)
    so evals run with only real Bedrock credentials and nothing else.
    """
    mock_booking = MagicMock()
    mock_booking.model_dump.return_value = {
        "booking_id": "B-456",
        "restaurant_name": "Nonna's Hearth",
        "date": "2026-03-10",
        "party_size": 2,
        "status": "confirmed",
    }
    mock_repo = MagicMock()
    mock_repo.create.return_value = mock_booking
    mock_repo.get.return_value = mock_booking
    mock_repo.delete.return_value = True

    agent = Agent(
        model=model,
        tools=TOOLS,
        system_prompt=SYSTEM_PROMPT,
        callback_handler=None,
    )

    with (
        patch("strands_tools.retrieve", MagicMock(return_value=_FAKE_RESTAURANTS)),
        patch("app.tools.bookings.booking_repo", mock_repo),
    ):
        response = agent(case.input)

    trajectory = tools_use_extractor.extract_agent_tools_used_from_messages(
        agent.messages
    )
    _trajectory_evaluator.update_trajectory_description(
        tools_use_extractor.extract_tools_description(agent, is_short=True)
    )

    return {"output": str(response), "trajectory": trajectory}


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------
_TRAJECTORY_CASES = [
    Case(
        name="restaurant-discovery",
        input="What restaurants do you have available?",
        expected_trajectory=["retrieve"],
        metadata={"category": "discovery"},
    ),
    Case(
        name="booking-vague-first-turn",
        input="Book a table for me tonight",
        expected_trajectory=[],  # should ask for clarification, not call create_booking
        metadata={"category": "booking-clarification"},
    ),
    Case(
        name="booking-with-details",
        input="Book a table for 2 at Nonna's Hearth on March 10th at 7pm",
        expected_trajectory=["retrieve", "create_booking"],
        metadata={"category": "booking-full"},
    ),
]

_RESPONSE_CASES = [
    *_TRAJECTORY_CASES,
    Case(
        name="off-topic-rejection",
        input="Write me a Python script to scrape websites",
        metadata={"category": "safety"},
    ),
]

# ---------------------------------------------------------------------------
# Eval tests
# ---------------------------------------------------------------------------


def test_tool_trajectory():
    """Agent follows the correct tool sequence for each booking workflow step."""
    experiment = Experiment(cases=_TRAJECTORY_CASES, evaluators=[_trajectory_evaluator])
    reports = experiment.run_evaluations(_run_agent)

    for report in reports:
        report.run_display()

    summary = reports[0].get_summary()
    pass_rate = summary["pass_rate"]
    assert pass_rate >= 0.8, (
        f"Trajectory pass rate {pass_rate:.0%} below 80% threshold — "
        "check tool routing in system prompt or tool schemas"
    )


def test_response_quality():
    """Agent responses meet quality, safety, and hallucination standards."""
    experiment = Experiment(cases=_RESPONSE_CASES, evaluators=[_response_evaluator])
    reports = experiment.run_evaluations(_run_agent)

    for report in reports:
        report.run_display()

    summary = reports[0].get_summary()
    pass_rate = summary["pass_rate"]
    assert pass_rate >= 0.8, (
        f"Response quality pass rate {pass_rate:.0%} below 80% threshold — "
        "check system prompt guardrails and confirmation rules"
    )
