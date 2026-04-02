"""Tests for the EvalProvenance typed provenance model."""

import pytest

from evals.braintrust.config import (
    BRAINTRUST_PROJECT,
    EVAL_AGENT_MODEL_ID,
    EVAL_JUDGE_MODEL_ID,
    OUTPUT_QUALITY_DATASET,
    OUTPUT_QUALITY_SCORER_VERSION,
    SYSTEM_PROMPT_SLUG,
)
from evals.braintrust.manifest import EvalProvenance


def _make_provenance(**overrides) -> EvalProvenance:
    defaults = dict(
        project_name=BRAINTRUST_PROJECT,
        dataset_name=OUTPUT_QUALITY_DATASET,
        dataset_version="42",
        prompt_slug=SYSTEM_PROMPT_SLUG,
        prompt_version="7",
        prompt_environment=None,
        agent_model_id=EVAL_AGENT_MODEL_ID,
        judge_model_id=EVAL_JUDGE_MODEL_ID,
        scorer_version=OUTPUT_QUALITY_SCORER_VERSION,
        commit="abc1234",
    )
    defaults.update(overrides)
    return EvalProvenance(**defaults)


def test_to_metadata_returns_all_required_keys():
    provenance = _make_provenance()
    meta = provenance.to_metadata()

    required_keys = {
        "project_name",
        "dataset_name",
        "dataset_version",
        "prompt_slug",
        "prompt_version",
        "prompt_environment",
        "agent_model_id",
        "judge_model_id",
        "scorer_version",
        "commit",
    }
    assert required_keys.issubset(meta.keys())


def test_to_metadata_values_match_fields():
    provenance = _make_provenance(dataset_version=99, prompt_version=3)
    meta = provenance.to_metadata()

    assert meta["dataset_version"] == 99
    assert meta["prompt_version"] == 3
    assert meta["commit"] == "abc1234"


def test_to_metadata_is_stable_across_calls():
    provenance = _make_provenance()
    assert provenance.to_metadata() == provenance.to_metadata()


def test_provenance_is_frozen():
    provenance = _make_provenance()
    with pytest.raises((AttributeError, TypeError)):
        provenance.commit = "mutated"  # type: ignore[misc]


def test_scorer_version_is_not_empty():
    assert OUTPUT_QUALITY_SCORER_VERSION != ""


def test_agent_model_id_is_not_empty():
    assert EVAL_AGENT_MODEL_ID != ""


def test_judge_model_id_is_not_empty():
    assert EVAL_JUDGE_MODEL_ID != ""


def test_provenance_allows_none_judge_for_trajectory_evals():
    provenance = _make_provenance(judge_model_id=None)
    meta = provenance.to_metadata()
    assert meta["judge_model_id"] is None


def test_provenance_allows_int_dataset_version():
    provenance = _make_provenance(dataset_version=1)
    assert provenance.to_metadata()["dataset_version"] == 1


def test_provenance_allows_none_prompt_version_with_environment():
    provenance = _make_provenance(prompt_version=None, prompt_environment="development")
    meta = provenance.to_metadata()
    assert meta["prompt_version"] is None
    assert meta["prompt_environment"] == "development"
