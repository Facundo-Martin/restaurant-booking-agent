from strands import Agent
from strands_evals import Case, Experiment
from strands_evals.evaluators import TrajectoryEvaluator
from strands_evals.extractors import tools_use_extractor
from strands_tools import calculator, current_time


# Define task function that captures tool usage
def get_response_with_tools(case: Case) -> dict:
    print(f"  Running case: {case.name!r} ...", flush=True)
    agent = Agent(
        tools=[calculator, current_time],
        system_prompt="You are a helpful assistant. Use tools when appropriate.",
        callback_handler=None,
    )
    response = agent(case.input)

    # Extract trajectory efficiently to prevent context overflow
    trajectory = tools_use_extractor.extract_agent_tools_used_from_messages(
        agent.messages
    )

    print(f"  Done: {case.name!r}", flush=True)
    return {"output": str(response), "trajectory": trajectory}


# Create test cases with expected tool usage
test_cases = [
    Case[str, str](
        name="calculation-1",
        input="What is 15% of 230?",
        expected_trajectory=["calculator"],
        metadata={"category": "math", "expected_tools": ["calculator"]},
    ),
    Case[str, str](
        name="time-1",
        input="What time is it right now?",
        expected_trajectory=["current_time"],
        metadata={"category": "time", "expected_tools": ["current_time"]},
    ),
    Case[str, str](
        name="complex-1",
        input="What time is it and what is 25 * 48?",
        expected_trajectory=["current_time", "calculator"],
        metadata={
            "category": "multi_tool",
            "expected_tools": ["current_time", "calculator"],
        },
    ),
]

# Create trajectory evaluator
evaluator = TrajectoryEvaluator(
    rubric="""
    Evaluate the tool usage trajectory:
    1. Correct tool selection - Were the right tools chosen for the task?
    2. Proper sequence - Were tools used in a logical order?
    3. Efficiency - Were unnecessary tools avoided?

    Use the built-in scoring tools to verify trajectory matches:
    - exact_match_scorer for exact sequence matching
    - in_order_match_scorer for ordered subset matching
    - any_order_match_scorer for unordered matching

    Score 1.0 if optimal tools used correctly.
    Score 0.5 if correct tools used but suboptimal sequence.
    Score 0.0 if wrong tools used or major inefficiencies.
    """,
    include_inputs=True,
)

# Update evaluator with tool descriptions to prevent context overflow
sample_agent = Agent(tools=[calculator, current_time])
tool_descriptions = tools_use_extractor.extract_tools_description(
    sample_agent, is_short=True
)
evaluator.update_trajectory_description(tool_descriptions)

# Create and run experiment
experiment = Experiment[str, str](cases=test_cases, evaluators=[evaluator])
print(f"Running {len(test_cases)} cases ...", flush=True)
reports = experiment.run_evaluations(get_response_with_tools)
print("Evaluations complete. Generating report ...", flush=True)

# Display results
print("=== Tool Usage Evaluation Results ===")
reports[0].run_display()

# Save experiment
experiment.to_file("trajectory_evaluation")
print("\nExperiment saved to ./experiment_files/trajectory_evaluation.json")
