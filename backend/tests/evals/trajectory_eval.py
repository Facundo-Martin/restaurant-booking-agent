# Requires AWS credentials with Bedrock InvokeModel access.
# Run from the backend/ directory:
#   PYTHONPATH=. SST_RESOURCE_Bookings='{"name":"<table>"}' SST_RESOURCE_RestaurantKB='{"id":"<kb-id>"}' SST_RESOURCE_AgentSessions='{"name":"placeholder"}' uv run python -u tests/evals/trajectory_eval.py
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch  # MagicMock used for booking_repo mock

from strands import Agent
from strands import tool as strands_tool
from strands.models import BedrockModel
from strands_evals import Case, Experiment
from strands_evals.evaluators import TrajectoryEvaluator
from strands_evals.extractors import tools_use_extractor
from strands_tools import retrieve as _real_retrieve

from app.agent.core import RETRY_STRATEGY, SYSTEM_PROMPT, TOOLS

# Haiku is fast, cheap, and has higher rate limits than Sonnet — more than capable of
# following the system prompt rules for tool routing. We don't need Sonnet quality here.
_AGENT_MODEL = BedrockModel(
    model_id="us.anthropic.claude-3-5-haiku-20241022-v1:0",
    additional_request_fields={"thinking": {"type": "disabled"}},
)

# Canned responses — deterministic inputs for consistent trajectory scoring
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

# Haiku as judge: faster + cheaper than Sonnet with no meaningful accuracy loss for rubric scoring.
_JUDGE_MODEL = "us.anthropic.claude-3-5-haiku-20241022-v1:0"


# Fake retrieve tool — patch("strands_tools.retrieve", ...) doesn't work because TOOLS
# already holds a reference to the real retrieve object. Instead we build a Strands-compatible
# @tool-decorated replacement and substitute it into the tools list so the agent calls our
# deterministic stub rather than making real Bedrock Knowledge Base calls during evals.
@strands_tool
def retrieve(query: str) -> str:
    """Search the knowledge base for restaurants, menus, and availability."""
    return _FAKE_RESTAURANTS


_EVAL_TOOLS = [retrieve if t is _real_retrieve else t for t in TOOLS]


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
        model=_AGENT_MODEL,
        tools=_EVAL_TOOLS,
        system_prompt=SYSTEM_PROMPT,
        callback_handler=None,
        retry_strategy=RETRY_STRATEGY,
    )

    with patch("app.tools.bookings.booking_repo", mock_repo):
        response = await agent.invoke_async(case.input)

    trajectory = tools_use_extractor.extract_agent_tools_used_from_messages(
        agent.messages
    )
    print(f"  Done: {case.name!r}", flush=True)
    return {"output": str(response), "trajectory": trajectory}


# Create test cases with expected tool usage
test_cases = [
    # --- Discovery: retrieve MUST be called ---
    Case[str, str](
        name="discovery-list-all",
        input="What restaurants do you have available?",
        expected_trajectory=["retrieve"],
        metadata={"category": "discovery"},
    ),
    Case[str, str](
        name="discovery-by-cuisine",
        input="Do you have any Italian restaurants?",
        expected_trajectory=["retrieve"],
        metadata={"category": "discovery"},
    ),
    # --- Clarification: no tools until details are provided ---
    Case[str, str](
        name="booking-vague-first-turn",
        input="Book a table for me tonight",
        expected_trajectory=[],  # must ask for clarification, not call any tools
        metadata={"category": "booking-clarification"},
    ),
    # --- Relative date: current_time must fire before retrieve ---
    Case[str, str](
        name="booking-relative-date",
        input="Book a table for 2 at Nonna's Hearth tonight at 7pm",
        expected_trajectory=["current_time", "retrieve"],
        # Agent must call current_time to resolve "tonight" and verify the date
        # is within the 60-day window, then retrieve to verify the restaurant.
        # create_booking is NOT expected here because the agent still needs
        # explicit user confirmation before proceeding (single-turn eval).
        metadata={"category": "booking-relative-date"},
    ),
    # --- Booking lookup ---
    Case[str, str](
        name="get-booking-details",
        input="What are the details for booking B-456?",
        expected_trajectory=["get_booking_details"],
        metadata={"category": "booking-lookup"},
    ),
    # --- Off-topic: no tools should be called ---
    Case[str, str](
        name="off-topic-no-tools",
        input="What's the weather like in London today?",
        expected_trajectory=[],
        metadata={"category": "safety"},
    ),
]

# Create trajectory evaluator
evaluator = TrajectoryEvaluator(
    rubric="""
    The agent is a restaurant booking assistant. Evaluate whether it followed
    the correct tool call sequence for the task.

    Rules:
    - Restaurant discovery queries (any cuisine, city, or listing): retrieve MUST be called.
    - Relative date references ("tonight", "this weekend", "tomorrow"): current_time
      MUST be called BEFORE retrieve or create_booking to resolve the date and
      verify it falls within the valid 60-day booking window.
    - Vague or incomplete booking requests (missing restaurant, date, party size):
      the agent MUST ask for clarification — no tools should be called.
    - Booking lookup (user provides a booking ID): get_booking_details MUST be called.
    - Off-topic requests: no tools should be called.

    Use the built-in scoring tools (exact_match_scorer, in_order_match_scorer,
    any_order_match_scorer) to verify trajectories where applicable.

    Score 1.0 if the tool sequence is fully correct.
    Score 0.5 if tools were used but in a suboptimal or incomplete order
              (e.g. retrieve called but current_time skipped for a relative date).
    Score 0.0 if a critical step is missing, wrong tools were called, or booking
              tools were invoked without the required prior steps.
    """,
    include_inputs=True,
    model=_JUDGE_MODEL,
)

# Seed the evaluator with tool descriptions to prevent context overflow
sample_agent = Agent(model=_AGENT_MODEL, tools=_EVAL_TOOLS, callback_handler=None)
evaluator.update_trajectory_description(
    tools_use_extractor.extract_tools_description(sample_agent, is_short=True)
)

_PASS_THRESHOLD = 0.85  # Fail CI if fewer than 85% of cases pass


def _save_report(experiment: object, report: object, ts: str, name: str) -> Path:
    """Save a rich JSON with per-case scores, reasons, and summary statistics.

    EvaluationReport exposes parallel lists (scores, test_passes, reasons) that
    align positionally with experiment.cases — zip them to produce per-case rows.
    """
    case_results = [
        {
            "name": case.name,
            "input": case.input,
            "expected_trajectory": case.expected_trajectory,
            "score": score,
            "test_pass": test_pass,
            "reason": reason,
            "metadata": case.metadata,
        }
        for case, score, test_pass, reason in zip(
            experiment.cases,
            report.scores,
            report.test_passes,
            report.reasons,
            strict=True,
        )
    ]

    passed = sum(1 for r in case_results if r["test_pass"])
    data = {
        "timestamp": ts,
        "overall_score": report.overall_score,
        "pass_rate": passed / len(case_results),
        "cases_passed": passed,
        "cases_total": len(case_results),
        "case_results": case_results,
    }

    out_dir = Path("tests/evals/experiment_files")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"{name}_{ts}.json"
    out_path.write_text(json.dumps(data, indent=2))
    return out_path


async def main() -> None:
    experiment = Experiment[str, str](cases=test_cases, evaluators=[evaluator])

    # Each agent turn is a separate converse_stream call, so even a few concurrent
    # cases can saturate rate limits. Haiku handles concurrency well but a small cap
    # keeps us safely under the limit.
    _sem = asyncio.Semaphore(2)

    async def _rate_limited(case: Case) -> dict:
        async with _sem:
            return await get_response_with_tools(case)

    print(f"Running {len(test_cases)} cases (max 2 concurrent) ...", flush=True)
    reports = await experiment.run_evaluations_async(_rate_limited)
    print("Evaluations complete. Generating report ...", flush=True)

    print("=== Tool Trajectory Evaluation Results ===")
    report = reports[0]
    report.run_display()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = _save_report(experiment, report, ts, "trajectory_evaluation")
    print(f"\nResults saved to {out_path}")

    passed = sum(1 for p in report.test_passes if p)
    pass_rate = passed / len(report.test_passes)
    print(f"\nPass rate: {passed}/{len(report.test_passes)} ({pass_rate:.0%})")
    if pass_rate < _PASS_THRESHOLD:
        print(
            f"ERROR: pass rate {pass_rate:.0%} is below threshold {_PASS_THRESHOLD:.0%}",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
