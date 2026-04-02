from evals.braintrust.config import (
    BRAINTRUST_PROJECT,
    OUTPUT_QUALITY_DATASET,
    SYSTEM_PROMPT_SLUG,
    TRAJECTORY_DATASET,
)


def test_braintrust_project_name_is_canonical():
    assert BRAINTRUST_PROJECT == "Restaurant Booking Agent"


def test_braintrust_dataset_names_are_stable():
    assert OUTPUT_QUALITY_DATASET == "restaurant-agent-output-quality"
    assert TRAJECTORY_DATASET == "restaurant-agent-trajectory"


def test_braintrust_prompt_slug_is_stable():
    assert SYSTEM_PROMPT_SLUG == "restaurant-booking-agent-system"
