import dataclasses

from evals.cases import OUTPUT_QUALITY_CASES, TRAJECTORY_CASES, EvalCase  # noqa: F401


def test_output_quality_cases():
    assert len(OUTPUT_QUALITY_CASES) == 11
    for case in OUTPUT_QUALITY_CASES:
        assert dataclasses.is_dataclass(case)
        assert isinstance(case.id, str) and case.id
        assert isinstance(case.input, str) and case.input
        assert isinstance(case.expected, str) and case.expected
        assert "category" in case.metadata


def test_trajectory_cases():
    assert len(TRAJECTORY_CASES) == 9
    for case in TRAJECTORY_CASES:
        assert dataclasses.is_dataclass(case)
        assert isinstance(case.id, str) and case.id
        assert isinstance(case.input, str) and case.input
        assert isinstance(case.expected, list)
        assert "category" in case.metadata


def test_all_ids_unique():
    all_ids = [c.id for c in OUTPUT_QUALITY_CASES + TRAJECTORY_CASES]
    assert len(all_ids) == len(set(all_ids)), "Duplicate case IDs found"
