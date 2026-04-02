"""Tests for the EvalMetadata class."""

import pytest

from evals.braintrust.config import (
    BRAINTRUST_PROJECT,
    EVAL_AGENT_MODEL_ID,
    EVAL_JUDGE_MODEL_ID,
    OUTPUT_QUALITY_DATASET,
    OUTPUT_QUALITY_SCORER_VERSION,
    SYSTEM_PROMPT_SLUG,
)
from evals.braintrust.manifest import EvalMetadata


def _make_metadata(**overrides) -> EvalMetadata:
    defaults = dict(
        project_name=BRAINTRUST_PROJECT,
        dataset_name=OUTPUT_QUALITY_DATASET,
        prompt_slug=SYSTEM_PROMPT_SLUG,
        agent_model_id=EVAL_AGENT_MODEL_ID,
        scorer_version=OUTPUT_QUALITY_SCORER_VERSION,
        commit="abc1234",
    )
    defaults.update(overrides)
    return EvalMetadata(**defaults)


def test_to_metadata_returns_all_fields():
    meta = _make_metadata().to_metadata()
    assert set(meta.keys()) == {
        "project_name",
        "dataset_name",
        "prompt_slug",
        "agent_model_id",
        "scorer_version",
        "commit",
        "dataset_version",
        "prompt_version",
        "prompt_environment",
        "judge_model_id",
    }


def test_optional_fields_default_to_none():
    meta = _make_metadata().to_metadata()
    assert meta["dataset_version"] is None
    assert meta["prompt_version"] is None
    assert meta["prompt_environment"] is None
    assert meta["judge_model_id"] is None


def test_optional_fields_are_included_when_provided():
    meta = _make_metadata(
        dataset_version="1000196924432228046",
        prompt_version="5878bd218351fb8e",
        prompt_environment="development",
        judge_model_id=EVAL_JUDGE_MODEL_ID,
    ).to_metadata()
    assert meta["dataset_version"] == "1000196924432228046"
    assert meta["prompt_version"] == "5878bd218351fb8e"
    assert meta["prompt_environment"] == "development"
    assert meta["judge_model_id"] == EVAL_JUDGE_MODEL_ID


def test_to_metadata_is_stable_across_calls():
    m = _make_metadata()
    assert m.to_metadata() == m.to_metadata()


def test_is_frozen():
    m = _make_metadata()
    with pytest.raises((AttributeError, TypeError)):
        m.commit = "mutated"  # type: ignore[misc]


def test_accepts_int_dataset_version():
    m = _make_metadata(dataset_version=42)
    assert m.to_metadata()["dataset_version"] == 42


def test_scorer_version_constant_is_not_empty():
    assert OUTPUT_QUALITY_SCORER_VERSION != ""


def test_model_id_constants_are_not_empty():
    assert EVAL_AGENT_MODEL_ID != ""
    assert EVAL_JUDGE_MODEL_ID != ""
