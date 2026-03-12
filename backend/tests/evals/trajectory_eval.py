# Requires AWS credentials with Bedrock InvokeModel access.
# Run from the backend/ directory:
#   PYTHONPATH=. SST_RESOURCE_Bookings='{"name":"<table>"}' SST_RESOURCE_RestaurantKB='{"id":"<kb-id>"}' \
#   uv run python -u tests/evals/trajectory_eval.py
import asyncio
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

from strands import Agent
from strands_evals import Case, Experiment
from strands_evals.evaluators import TrajectoryEvaluator
from strands_evals.extractors import tools_use_extractor

from app.agent.core import SYSTEM_PROMPT, TOOLS, model

# Canned KB response — deterministic input for consistent trajectory scoring
_FAKE_RESTAURANTS = (
    "Available restaurants: Nonna's Hearth (Italian, open daily, accepts reservations), "
    "Bistro Parisienne (French, closed Mondays, accepts reservations), "
    "Sakura Garden (Japanese, open daily, accepts reservations)."
)

_FAKE_BOOKING = {
    "booking_id": "B-456",
    "restaurant_name": "Nonna's Hearth",
    "date": "2026-03-10",
    "party_size": 2,
    "status": "confirmed",
}


# Define async task function — cases run concurrently via run_evaluations_async
async def get_response_with_tools(case: Case) -> dict:
    print(f"  Running case: {case.name!r} ...", flush=True)

    mock_booking = MagicMock()
    mock_booking.model_dump.return_value = _FAKE_BOOKING
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
        response = await agent.invoke_async(case.input)

    trajectory = tools_use_extractor.extract_agent_tools_used_from_messages(
        agent.messages
    )

    print(f"  Done: {case.name!r}", flush=True)
    return {"output": str(response), "trajectory": trajectory}


# TODO: add absolute-date validation case once system prompt rule 2 is verified in prod.
# Example: input="Book for March 5th at 7pm for 2", expected_trajectory=["current_time"]
# The agent should call current_time to check if March 5th is in the valid 60-day window,
# then reject or proceed accordingly. Needs a real deployment date to set a stable fixed date.

# Create test cases with expected tool usage
test_cases = [
    Case[str, str](
        name="restaurant-discovery-all",
        input="What restaurants do you have available?",
        expected_trajectory=["retrieve"],
        metadata={"category": "discovery"},
    ),
    Case[str, str](
        name="restaurant-discovery-by-cuisine",
        input="Do you have any Italian restaurants?",
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

# Haiku as judge: faster + cheaper than Sonnet with no meaningful accuracy loss for rubric scoring.
_JUDGE_MODEL = "us.anthropic.claude-3-5-haiku-20241022-v1:0"

# Create trajectory evaluator
evaluator = TrajectoryEvaluator(
    rubric="""
    The agent is a restaurant booking assistant. Evaluate whether it followed
    the correct tool call sequence for the task.

    Rules:
    - Restaurant discovery queries (any cuisine, city, or listing): retrieve MUST be called.
    - Booking creation: retrieve MUST be called before create_booking.
      On a vague first-turn request ("book a table for me tonight"),
      the agent should ask for clarification — NOT call create_booking immediately.
    - Off-topic requests: no tools should be called.

    Use the built-in scoring tools (exact_match_scorer, in_order_match_scorer,
    any_order_match_scorer) to verify trajectories where applicable.

    Score 1.0 if the tool sequence is fully correct.
    Score 0.5 if tools were used but in a suboptimal or incomplete order.
    Score 0.0 if a critical step is missing or booking tools are called without
               the required prior steps.
    """,
    include_inputs=True,
    model=_JUDGE_MODEL,
)

# Seed the evaluator with tool descriptions to prevent context overflow
sample_agent = Agent(model=model, tools=TOOLS, callback_handler=None)
evaluator.update_trajectory_description(
    tools_use_extractor.extract_tools_description(sample_agent, is_short=True)
)

_PASS_THRESHOLD = 0.85  # Fail CI if fewer than 85% of cases pass


async def main() -> None:
    experiment = Experiment[str, str](cases=test_cases, evaluators=[evaluator])
    print(f"Running {len(test_cases)} cases concurrently ...", flush=True)
    reports = await experiment.run_evaluations_async(get_response_with_tools)
    print("Evaluations complete. Generating report ...", flush=True)

    print("=== Tool Trajectory Evaluation Results ===")
    report = reports[0]
    report.run_display()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    experiment.to_file(f"trajectory_evaluation_{ts}")
    print(f"\nExperiment saved to ./experiment_files/trajectory_evaluation_{ts}.json")

    passed = sum(1 for r in report.results if r.test_pass)
    pass_rate = passed / len(report.results)
    print(f"\nPass rate: {passed}/{len(report.results)} ({pass_rate:.0%})")
    if pass_rate < _PASS_THRESHOLD:
        print(
            f"ERROR: pass rate {pass_rate:.0%} is below threshold {_PASS_THRESHOLD:.0%}",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
