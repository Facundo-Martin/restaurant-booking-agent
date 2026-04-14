"""Tests for Braintrust config constants — stable identifiers and version strings."""

from evals.braintrust.config import (
    BRAINTRUST_PROJECT,
    EVAL_AGENT_MODEL_ID,
    EVAL_JUDGE_MODEL_ID,
    OUTPUT_QUALITY_DATASET,
    OUTPUT_QUALITY_SCORER_VERSION,
    SYSTEM_PROMPT_SLUG,
    TRAJECTORY_DATASET,
    TRAJECTORY_SCORER_VERSION,
    WORKFLOW_SCORER_VERSION,
)


def test_braintrust_project_name_is_canonical():
    assert BRAINTRUST_PROJECT == "Restaurant Booking Agent"


def test_braintrust_dataset_names_are_stable():
    assert OUTPUT_QUALITY_DATASET == "restaurant-agent-output-quality"
    assert TRAJECTORY_DATASET == "restaurant-agent-trajectory"


def test_braintrust_prompt_slug_is_stable():
    assert SYSTEM_PROMPT_SLUG == "restaurant-booking-agent-system"


def test_model_ids_are_not_empty():
    assert EVAL_AGENT_MODEL_ID != ""
    assert EVAL_JUDGE_MODEL_ID != ""


def test_scorer_versions_are_not_empty():
    assert OUTPUT_QUALITY_SCORER_VERSION != ""
    assert TRAJECTORY_SCORER_VERSION != ""
    assert WORKFLOW_SCORER_VERSION != ""
