"""Tests for dataset preflight helpers."""

from unittest.mock import MagicMock, call, patch

import pytest

from evals.braintrust.datasets import assert_case_count_matches, load_dataset


def _mock_dataset(rows: list) -> MagicMock:
    """Return a mock braintrust.Dataset that iterates over rows."""
    ds = MagicMock()
    ds.__iter__ = MagicMock(return_value=iter(rows))
    return ds


# ---------------------------------------------------------------------------
# load_dataset
# ---------------------------------------------------------------------------


def test_load_dataset_returns_dataset_and_rows():
    rows = [{"id": "a"}, {"id": "b"}]
    mock_ds = _mock_dataset(rows)

    with patch(
        "evals.braintrust.datasets.braintrust.init_dataset", return_value=mock_ds
    ) as mock_init:
        dataset, returned_rows = load_dataset("MyProject", "my-dataset", version=None)

    assert dataset is mock_ds
    assert returned_rows == rows
    mock_init.assert_called_once_with(
        project="MyProject", name="my-dataset", version=None
    )


def test_load_dataset_forwards_version():
    mock_ds = _mock_dataset([{"id": "x"}])

    with patch(
        "evals.braintrust.datasets.braintrust.init_dataset", return_value=mock_ds
    ) as mock_init:
        load_dataset("P", "D", version="42")

    assert mock_init.call_args == call(project="P", name="D", version="42")


def test_load_dataset_raises_on_empty_dataset():
    mock_ds = _mock_dataset([])

    with patch(
        "evals.braintrust.datasets.braintrust.init_dataset", return_value=mock_ds
    ):
        with pytest.raises(RuntimeError, match="empty"):
            load_dataset("P", "empty-dataset", version=None)


def test_load_dataset_error_message_contains_dataset_name():
    mock_ds = _mock_dataset([])

    with patch(
        "evals.braintrust.datasets.braintrust.init_dataset", return_value=mock_ds
    ):
        with pytest.raises(RuntimeError, match="my-special-dataset"):
            load_dataset("P", "my-special-dataset", version=None)


# ---------------------------------------------------------------------------
# assert_case_count_matches
# ---------------------------------------------------------------------------


def test_assert_case_count_passes_when_counts_match():
    rows = [1, 2, 3]
    cases = ["a", "b", "c"]
    # Should not raise
    assert_case_count_matches(rows, cases, "test-dataset")


def test_assert_case_count_raises_when_rows_exceed_cases():
    with pytest.raises(RuntimeError, match="test-dataset"):
        assert_case_count_matches([1, 2, 3], ["a", "b"], "test-dataset")


def test_assert_case_count_raises_when_cases_exceed_rows():
    with pytest.raises(RuntimeError, match="test-dataset"):
        assert_case_count_matches([1], ["a", "b", "c"], "test-dataset")


def test_assert_case_count_error_shows_both_counts():
    with pytest.raises(RuntimeError, match="3") as exc_info:
        assert_case_count_matches([1, 2, 3], ["a"], "ds")
    assert "1" in str(exc_info.value)
