"""Unit tests for eval scorers.

trajectory_scorer — pure deterministic function, no mocking needed.
booking_output_quality_scorer — mocks _invoke_judge to avoid Bedrock calls.
"""

from unittest.mock import patch

from evals.scorers.output_quality_scorer import (
    _has_explicit_verdict,
    _parse_verdict,
    booking_output_quality_scorer,
)
from evals.scorers.trajectory_scorer import _normalise_trajectory, trajectory_scorer

# ---------------------------------------------------------------------------
# _normalise_trajectory
# ---------------------------------------------------------------------------


class TestNormaliseTrajectory:
    def test_list_of_strings_passthrough(self):
        assert _normalise_trajectory(["retrieve", "create_booking"]) == [
            "retrieve",
            "create_booking",
        ]

    def test_list_of_dicts_extracts_name(self):
        """Braintrust tools_use_extractor returns list[dict] — extract 'name' key."""
        raw = [
            {
                "name": "retrieve",
                "input": {"query": "q"},
                "is_error": False,
                "tool_result": "r",
            },
            {
                "name": "create_booking",
                "input": {},
                "is_error": False,
                "tool_result": "b",
            },
        ]
        assert _normalise_trajectory(raw) == ["retrieve", "create_booking"]

    def test_mixed_list(self):
        """Handles a mix of dicts and bare strings (defensive)."""
        raw = [{"name": "retrieve"}, "create_booking"]
        assert _normalise_trajectory(raw) == ["retrieve", "create_booking"]

    def test_empty_list(self):
        assert _normalise_trajectory([]) == []

    def test_non_list_returns_empty(self):
        assert _normalise_trajectory(None) == []
        assert _normalise_trajectory("retrieve") == []


# ---------------------------------------------------------------------------
# trajectory_scorer
# ---------------------------------------------------------------------------


class TestTrajectoryScorer:
    def _score(self, actual: list, expected: list[str]) -> float:
        result = trajectory_scorer(
            input="test input",
            output={"output": "response", "trajectory": actual},
            expected=expected,
        )
        assert result["name"] == "TrajectoryMatch"
        return result["score"]

    def test_exact_match(self):
        assert (
            self._score(["retrieve", "create_booking"], ["retrieve", "create_booking"])
            == 1.0
        )

    def test_exact_match_dict_trajectory(self):
        """Braintrust-style list[dict] trajectory — normalised to list[str] before comparison."""
        raw = [
            {"name": "retrieve", "input": {}, "is_error": False, "tool_result": ""},
            {
                "name": "create_booking",
                "input": {},
                "is_error": False,
                "tool_result": "",
            },
        ]
        assert self._score(raw, ["retrieve", "create_booking"]) == 1.0

    def test_exact_match_empty(self):
        """No tools expected and none called — off-topic or clarification case."""
        assert self._score([], []) == 1.0

    def test_tools_fired_when_none_expected(self):
        assert self._score(["retrieve"], []) == 0.0

    def test_correct_relative_order_with_extras(self):
        """Expected tools present in order, but extra tools also fired."""
        assert (
            self._score(
                ["current_time", "retrieve", "create_booking"],
                ["current_time", "create_booking"],
            )
            == 0.75
        )

    def test_wrong_order(self):
        assert (
            self._score(["create_booking", "retrieve"], ["retrieve", "create_booking"])
            == 0.5
        )

    def test_missing_required_tool(self):
        assert self._score(["retrieve"], ["retrieve", "create_booking"]) == 0.0

    def test_completely_wrong_tools(self):
        assert (
            self._score(["get_booking_details"], ["retrieve", "create_booking"]) == 0.0
        )

    def test_non_dict_output_treated_as_empty(self):
        """If task returns a non-dict, trajectory defaults to []."""
        result = trajectory_scorer(
            input="x", output="plain string", expected=["retrieve"]
        )
        assert result["score"] == 0.0

    def test_metadata_present(self):
        result = trajectory_scorer(input="x", output={"trajectory": []}, expected=[])
        assert "reason" in result["metadata"]


# ---------------------------------------------------------------------------
# _has_explicit_verdict
# ---------------------------------------------------------------------------


class TestHasExplicitVerdict:
    def test_true_with_verdict_prefix(self):
        assert _has_explicit_verdict("reasoning\nVERDICT: Y") is True

    def test_true_case_insensitive(self):
        assert _has_explicit_verdict("verdict: n") is True

    def test_false_bare_letter_only(self):
        """Bare letter fallback is NOT an explicit verdict."""
        assert _has_explicit_verdict("All good.\nY") is False

    def test_false_empty(self):
        assert _has_explicit_verdict("") is False

    def test_false_garbled_output(self):
        assert (
            _has_explicit_verdict("declines the web for web scrwith boundary") is False
        )


# ---------------------------------------------------------------------------
# _parse_verdict
# ---------------------------------------------------------------------------


class TestParseVerdict:
    def test_verdict_y(self):
        assert _parse_verdict("some reasoning\nVERDICT: Y") == "Y"

    def test_verdict_n(self):
        assert _parse_verdict("some reasoning\nVERDICT: N") == "N"

    def test_verdict_p(self):
        assert _parse_verdict("some reasoning\nVERDICT: P") == "P"

    def test_case_insensitive(self):
        assert _parse_verdict("verdict: y") == "Y"

    def test_extra_whitespace(self):
        assert _parse_verdict("VERDICT:  Y") == "Y"

    def test_fallback_bare_letter_y(self):
        """No VERDICT: prefix — fall back to bare letter at end of text."""
        assert _parse_verdict("All criteria met.\nY") == "Y"

    def test_fallback_bare_letter_n(self):
        assert _parse_verdict("Criteria violated.\nN") == "N"

    def test_fallback_default_n_on_no_match(self):
        """Unrecognisable output defaults conservatively to N."""
        assert _parse_verdict("Unable to determine.") == "N"


# ---------------------------------------------------------------------------
# booking_output_quality_scorer (mocked judge)
# ---------------------------------------------------------------------------


class TestBookingOutputQualityScorer:
    def _run(self, verdict_text: str, **kwargs) -> dict:
        with patch(
            "evals.scorers.output_quality_scorer._invoke_judge",
            return_value=verdict_text,
        ):
            return booking_output_quality_scorer(
                input=kwargs.get("input", "Book me a table"),
                output=kwargs.get("output", "Sure, which restaurant?"),
                expected=kwargs.get("expected", "Should ask for details"),
            )

    def test_score_y(self):
        result = self._run("All good.\nVERDICT: Y")
        assert result["score"] == 1.0
        assert result["name"] == "BookingOutputQuality"
        assert result["metadata"]["verdict"] == "Y"

    def test_score_p(self):
        result = self._run("Partial compliance.\nVERDICT: P")
        assert result["score"] == 0.5

    def test_score_n(self):
        result = self._run("Rule violated.\nVERDICT: N")
        assert result["score"] == 0.0

    def test_reasoning_captured_in_metadata(self):
        result = self._run("Detailed reasoning here.\nVERDICT: Y")
        assert "reasoning" in result["metadata"]
        assert "Detailed reasoning" in result["metadata"]["reasoning"]

    def test_reasoning_truncated_at_1000_chars(self):
        long_reasoning = "x" * 2000 + "\nVERDICT: Y"
        result = self._run(long_reasoning)
        assert len(result["metadata"]["reasoning"]) <= 1000

    def test_non_string_output_coerced(self):
        """Output dict (e.g. from trajectory eval) is coerced to str."""
        result = self._run("VERDICT: Y", output={"text": "hello"})
        assert result["score"] == 1.0

    def test_missing_expected_uses_placeholder(self):
        """No expected → scorer still runs without KeyError."""
        with patch(
            "evals.scorers.output_quality_scorer._invoke_judge",
            return_value="VERDICT: Y",
        ):
            result = booking_output_quality_scorer(input="hi", output="hello")
        assert result["score"] == 1.0

    def test_retry_on_missing_explicit_verdict(self):
        """If the first judge response has no VERDICT: line, scorer retries once."""
        garbled = "declines the web for web scrwith boundary politely"
        good = "All criteria met.\nVERDICT: Y"
        with patch(
            "evals.scorers.output_quality_scorer._invoke_judge",
            side_effect=[garbled, good],
        ) as mock_judge:
            result = booking_output_quality_scorer(input="x", output="y")
        assert mock_judge.call_count == 2
        assert result["score"] == 1.0

    def test_no_retry_when_explicit_verdict_present(self):
        """No retry when judge includes explicit VERDICT: line on first call."""
        with patch(
            "evals.scorers.output_quality_scorer._invoke_judge",
            return_value="VERDICT: Y",
        ) as mock_judge:
            booking_output_quality_scorer(input="x", output="y")
        assert mock_judge.call_count == 1

    def test_retry_uses_second_verdict_even_if_also_fallback(self):
        """After retry, whatever _parse_verdict extracts from the second response is used."""
        garbled1 = "no verdict here"
        garbled2 = "still no verdict\nN"  # bare letter — fallback path
        with patch(
            "evals.scorers.output_quality_scorer._invoke_judge",
            side_effect=[garbled1, garbled2],
        ):
            result = booking_output_quality_scorer(input="x", output="y")
        assert result["score"] == 0.0  # bare N → 0.0
