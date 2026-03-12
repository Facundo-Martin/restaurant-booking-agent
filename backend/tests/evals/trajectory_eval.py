# Requires AWS credentials with Bedrock InvokeModel access.
# Run from the backend/ directory:
#   PYTHONPATH=. SST_RESOURCE_Bookings='{"name":"<table>"}' SST_RESOURCE_RestaurantKB='{"id":"<kb-id>"}' \
#   uv run python -u tests/evals/trajectory_eval.py
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


# Define task function that captures tool usage
def get_response_with_tools(case: Case) -> dict:
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
        response = agent(case.input)

    trajectory = tools_use_extractor.extract_agent_tools_used_from_messages(
        agent.messages
    )

    print(f"  Done: {case.name!r}", flush=True)
    return {"output": str(response), "trajectory": trajectory}


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
)

# Seed the evaluator with tool descriptions to prevent context overflow
sample_agent = Agent(model=model, tools=TOOLS, callback_handler=None)
evaluator.update_trajectory_description(
    tools_use_extractor.extract_tools_description(sample_agent, is_short=True)
)

# Create and run experiment
experiment = Experiment[str, str](cases=test_cases, evaluators=[evaluator])
print(f"Running {len(test_cases)} cases ...", flush=True)
reports = experiment.run_evaluations(get_response_with_tools)
print("Evaluations complete. Generating report ...", flush=True)

# Display results
print("=== Tool Trajectory Evaluation Results ===")
reports[0].run_display()

# Save experiment
experiment.to_file("trajectory_evaluation")
print("\nExperiment saved to ./experiment_files/trajectory_evaluation.json")
