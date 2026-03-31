# OTel-based eval scaffold for v2 evaluators (FaithfulnessEvaluator, ToolParameterEvaluator).
# Uses StrandsEvalsTelemetry + StrandsInMemorySessionMapper wired to the restaurant agent.
# Currently evaluated with HelpfulnessEvaluator as a starting point.
# Not run in CI — exists as a working v2 starting point.
#
# Run from the backend/ directory:
#   PYTHONPATH=. uv run python -u evals/strands/otel_scaffold.py
from unittest.mock import MagicMock, patch

from strands import Agent
from strands import tool as strands_tool
from strands_evals import Case, Experiment
from strands_evals.evaluators import HelpfulnessEvaluator
from strands_evals.mappers import StrandsInMemorySessionMapper
from strands_evals.telemetry import StrandsEvalsTelemetry
from strands_tools import retrieve as _real_retrieve

from app.agent.core import SYSTEM_PROMPT, TOOLS, model

# Setup telemetry for trace capture
telemetry = StrandsEvalsTelemetry().setup_in_memory_exporter()

_FAKE_RESTAURANTS = (
    "Available restaurants: Nonna's Hearth (Italian, open daily, accepts reservations), "
    "Bistro Parisienne (French, closed Mondays, accepts reservations)."
)

_FAKE_BOOKING = {
    "booking_id": "B-456",
    "restaurant_name": "Nonna's Hearth",
    "date": "2026-04-10",
    "party_size": 2,
    "status": "confirmed",
}


# Replace the real retrieve in the tool list with the deterministic stub.
@strands_tool
def retrieve(query: str) -> str:
    """Search the knowledge base for restaurants, menus, and availability."""
    return _FAKE_RESTAURANTS


_EVAL_TOOLS = [retrieve if t is _real_retrieve else t for t in TOOLS]


def run_agent(case: Case) -> dict:
    # Clear previous traces so spans from different cases don't mix.
    telemetry.in_memory_exporter.clear()

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
        # IMPORTANT: trace_attributes with session IDs are required when using
        # StrandsInMemorySessionMapper to prevent spans from different cases
        # from being mixed together in the memory exporter.
        trace_attributes={
            "gen_ai.conversation.id": case.session_id,
            "session.id": case.session_id,
        },
        callback_handler=None,
    )

    with patch("app.tools.bookings.booking_repo", mock_repo):
        response = agent(case.input)

    finished_spans = telemetry.in_memory_exporter.get_finished_spans()
    mapper = StrandsInMemorySessionMapper()
    session = mapper.map_to_session(finished_spans, session_id=case.session_id)

    return {"output": str(response), "trajectory": session}


test_cases = [
    Case[str, str](
        name="discovery-list-all",
        input="What restaurants do you have available?",
        metadata={"category": "discovery"},
    ),
    Case[str, str](
        name="booking-clarification",
        input="Book a table for me tonight",
        metadata={"category": "clarification"},
    ),
    Case[str, str](
        name="off-topic-rejection",
        input="Write me a Python script to scrape websites",
        metadata={"category": "safety"},
    ),
]

evaluator = HelpfulnessEvaluator()

if __name__ == "__main__":
    experiment = Experiment[str, str](cases=test_cases, evaluators=[evaluator])
    reports = experiment.run_evaluations(run_agent)

    print("=== OTel Scaffold — Helpfulness Results ===")
    reports[0].run_display()
