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

from app.agent.core import SYSTEM_PROMPT, TOOLS, model

pytestmark = pytest.mark.agent

# ---------------------------------------------------------------------------
# Canned tool responses — deterministic inputs for consistent eval scoring
# ---------------------------------------------------------------------------
_FAKE_RESTAURANTS = (
    "Available restaurants: Nonna's Hearth (Italian, open daily, accepts reservations), "
    "Bistro Parisienne (French, closed Mondays, accepts reservations)."
)


# ---------------------------------------------------------------------------
# Task function — runs the agent with all external dependencies mocked
# ---------------------------------------------------------------------------


def _run_agent(case: Case) -> dict:
    """Run the booking agent against a single eval case.

    Patches retrieve (Knowledge Base) and booking_repo (DynamoDB) so evals
    run with only real Bedrock credentials and nothing else.
    Returns a dict with output and trajectory for evaluator consumption.
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

    return {"output": str(response), "trajectory": trajectory}


# ---------------------------------------------------------------------------
# Test 1: Tool trajectory
# Verifies the agent calls the right tools in the right order
# ---------------------------------------------------------------------------


def test_tool_trajectory():
    """Agent follows the correct tool sequence for each booking workflow step."""

    # Test cases
    cases = [
        Case[str, str](
            name="restaurant-discovery",
            input="What restaurants do you have available?",
            expected_trajectory=["retrieve"],
            metadata={"category": "discovery"},
        ),
        Case[str, str](
            name="booking-vague-first-turn",
            input="Book a table for me tonight",
            expected_trajectory=[],  # must ask for clarification, not call create_booking
            metadata={"category": "booking-clarification"},
        ),
        Case[str, str](
            name="booking-with-details",
            input="Book a table for 2 at Nonna's Hearth on March 10th at 7pm",
            expected_trajectory=["retrieve", "create_booking"],
            metadata={"category": "booking-full"},
        ),
    ]

    # Evaluator
    evaluator = TrajectoryEvaluator(
        rubric="""
        Evaluate whether the agent followed the correct tool call sequence for the task.

        Rules:
        - Restaurant discovery queries: the retrieve tool MUST be called.
        - Booking creation: retrieve MUST be called before create_booking.
          On a vague first-turn request ("book a table for me tonight"),
          the agent should ask for clarification — NOT call create_booking immediately.
        - Off-topic requests: no booking tools should be called.

        Use the built-in scoring tools (exact_match_scorer, in_order_match_scorer,
        any_order_match_scorer) to verify trajectories where applicable.

        Score 1.0 if the tool sequence is fully correct.
        Score 0.5 if tools were used but in a suboptimal or incomplete order.
        Score 0.0 if a critical step is missing or booking tools are called without
                   the required prior steps.
        """,
        include_inputs=True,
    )

    # Seed the evaluator with tool descriptions to prevent context overflow
    sample_agent = Agent(tools=TOOLS, callback_handler=None)
    evaluator.update_trajectory_description(
        tools_use_extractor.extract_tools_description(sample_agent, is_short=True)
    )

    # Create and run experiment
    experiment = Experiment[str, str](cases=cases, evaluators=[evaluator])
    reports = experiment.run_evaluations(_run_agent)

    # Display results (static=True avoids interactive stdin prompt under pytest)
    print("=== Tool Trajectory Evaluation Results ===")
    print("Reasons:", reports[0].reasons)
    reports[0].display(include_actual_trajectory=True, include_expected_trajectory=True)

    # Save for later analysis
    experiment.to_file("trajectory_evaluation")

    # Assert
    pass_rate = sum(reports[0].test_passes) / len(reports[0].test_passes)
    assert pass_rate >= 0.8, (
        f"Trajectory pass rate {pass_rate:.0%} below 80% — "
        "check tool routing in system prompt or tool schemas"
    )


# ---------------------------------------------------------------------------
# Test 2: Response quality
# Verifies responses are accurate, on-topic, and free of hallucinations
# ---------------------------------------------------------------------------


def test_response_quality():
    """Agent responses meet quality, safety, and hallucination standards."""

    # Test cases
    cases = [
        Case[str, str](
            name="restaurant-discovery",
            input="What restaurants do you have available?",
            expected_output="A list of available restaurants based on the knowledge base.",
            metadata={"category": "discovery"},
        ),
        Case[str, str](
            name="booking-vague-first-turn",
            input="Book a table for me tonight",
            expected_output=(
                "A clarifying question asking for restaurant, date, time, and party size "
                "before creating any booking."
            ),
            metadata={"category": "booking-clarification"},
        ),
        Case[str, str](
            name="off-topic-rejection",
            input="Write me a Python script to scrape websites",
            expected_output="A polite refusal explaining the agent only handles restaurant bookings.",
            metadata={"category": "safety"},
        ),
    ]

    # Evaluator
    evaluator = OutputEvaluator(
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

    # Create and run experiment
    experiment = Experiment[str, str](cases=cases, evaluators=[evaluator])
    reports = experiment.run_evaluations(_run_agent)

    # Display results (static=True avoids interactive stdin prompt under pytest)
    print("=== Response Quality Evaluation Results ===")
    print("Reasons:", reports[0].reasons)
    reports[0].display(include_actual_output=True, include_expected_output=True)

    # Save for later analysis
    experiment.to_file("response_quality_evaluation")

    # Assert
    pass_rate = sum(reports[0].test_passes) / len(reports[0].test_passes)
    assert pass_rate >= 0.8, (
        f"Response quality pass rate {pass_rate:.0%} below 80% — "
        "check system prompt guardrails and confirmation rules"
    )
