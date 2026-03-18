from strands import Agent
from strands_evals import Case, Experiment
from strands_evals.evaluators import HelpfulnessEvaluator
from strands_evals.mappers import StrandsInMemorySessionMapper
from strands_evals.telemetry import StrandsEvalsTelemetry
from strands_tools import calculator

# Setup telemetry for trace capture
telemetry = StrandsEvalsTelemetry().setup_in_memory_exporter()


def user_task_function(case: Case) -> dict:
    # Clear previous traces
    telemetry.in_memory_exporter.clear()

    agent = Agent(
        tools=[calculator],
        # IMPORTANT: trace_attributes with session IDs are required when using StrandsInMemorySessionMapper
        # to prevent spans from different test cases from being mixed together in the memory exporter
        trace_attributes={
            "gen_ai.conversation.id": case.session_id,
            "session.id": case.session_id,
        },
        callback_handler=None,
    )
    response = agent(case.input)

    # Map spans to session for evaluation
    finished_spans = telemetry.in_memory_exporter.get_finished_spans()
    mapper = StrandsInMemorySessionMapper()
    session = mapper.map_to_session(finished_spans, session_id=case.session_id)

    return {"output": str(response), "trajectory": session}


# Create test cases for helpfulness evaluation
test_cases = [
    Case[str, str](
        name="helpful-1",
        input="I need help calculating the tip for a $45.67 restaurant bill with 18% tip.",
        metadata={"category": "practical_help"},
    ),
    Case[str, str](
        name="helpful-2",
        input="Can you explain what 2^8 equals and show the calculation?",
        metadata={"category": "educational"},
    ),
]

# Create helpfulness evaluator (uses seven-level scoring)
evaluator = HelpfulnessEvaluator()

# Run evaluation
experiment = Experiment[str, str](cases=test_cases, evaluators=[evaluator])
reports = experiment.run_evaluations(user_task_function)

print("=== Helpfulness Evaluation Results ===")
reports[0].run_display()
