from strands import Agent
from strands_evals import Case, Experiment
from strands_evals.evaluators import OutputEvaluator


# Define your task function
def get_response(case: Case) -> str:
    print(f"  Running case: {case.name!r} ...", flush=True)
    agent = Agent(
        system_prompt="You are a helpful assistant that provides accurate information.",
        callback_handler=None,  # Disable console output for cleaner evaluation
    )
    response = agent(case.input)
    print(f"  Done: {case.name!r}", flush=True)
    return str(response)


# Create test cases
test_cases = [
    Case[str, str](
        name="knowledge-1",
        input="What is the capital of France?",
        expected_output="The capital of France is Paris.",
        metadata={"category": "knowledge"},
    ),
    Case[str, str](
        name="knowledge-2",
        input="What is 2 + 2?",
        expected_output="4",
        metadata={"category": "math"},
    ),
    Case[str, str](
        name="reasoning-1",
        input="If it takes 5 machines 5 minutes to make 5 widgets, how long does it take 100 machines to make 100 widgets?",
        expected_output="5 minutes",
        metadata={"category": "reasoning"},
    ),
]

# Create evaluator with custom rubric
evaluator = OutputEvaluator(
    rubric="""
    Evaluate the response based on:
    1. Accuracy - Is the information factually correct?
    2. Completeness - Does it fully answer the question?
    3. Clarity - Is it easy to understand?

    Score 1.0 if all criteria are met excellently.
    Score 0.5 if some criteria are partially met.
    Score 0.0 if the response is inadequate or incorrect.
    """,
    include_inputs=True,
)

# Create and run experiment
experiment = Experiment[str, str](cases=test_cases, evaluators=[evaluator])
print(f"Running {len(test_cases)} cases ...", flush=True)
reports = experiment.run_evaluations(get_response)
print("Evaluations complete. Generating report ...", flush=True)

# Display results
print("=== Basic Output Evaluation Results ===")
reports[0].run_display()

# Save experiment for later analysis
experiment.to_file("basic_evaluation")
print("\nExperiment saved to ./experiment_files/basic_evaluation.json")
