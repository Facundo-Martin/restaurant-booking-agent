"""
Strands Experiment Generation

Run from backend/ directory:
    PYTHONPATH=. uv run python evals/strands/generated_experiment.py

"""

import asyncio

from strands_evals.evaluators import TrajectoryEvaluator
from strands_evals.generators import ExperimentGenerator

# Define tool context
tool_context = """
Available tools:
- retrieve() -> str Retrieving information from Amazon Bedrock Knowledge Bases with optional metadata
- current_time() -> str: Get the current date and time
- get_booking_details(booking_id: str) -> dict: Get the details of an existing booking
- create_booking(
    restaurant_name: str,
    date: str,
    party_size: int,
    special_requests: str | None = None,
) -> dict: create a new restaurant booking
- delete_booking(booking_id: str) -> str: Delete an existing booking
"""


# Generate experiment automatically
async def generate_experiment():
    generator = ExperimentGenerator[str, str](str, str)

    experiment = await generator.from_context_async(
        context=tool_context,
        num_cases=3,
        evaluator=TrajectoryEvaluator,
        task_description="Restaurant concierge/assistant agent",
        num_topics=2,  # Distribute across multiple topics
    )

    # Save generated experiment
    experiment.to_file("generated_experiment")
    print("Generated experiment saved!")

    return experiment


# Run the generator
generated_exp = asyncio.run(generate_experiment())
