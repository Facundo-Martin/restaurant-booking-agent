"""Deterministic trajectory scorer — checks tool-call order without an LLM.

Why custom code instead of LLM-as-judge:
  Tool routing rules are precise and enumerable. An LLM judge adds noise and
  cost without improving accuracy for exact-match comparisons. Custom code is
  cheaper, faster, and more reproducible.

Scoring rubric:
  1.0 — exact match (same tools, same order, nothing extra)
  0.75 — all expected tools present in correct relative order, but extra tools also fired
  0.5 — all expected tools present but in wrong order
  0.0 — one or more expected tools missing, OR tools fired when none were expected

Braintrust scorer contract:
  Receives keyword args: input, output, expected, metadata
  Returns: dict with 'name', 'score' (0–1), optional 'metadata'

  output  — dict with keys 'output' (str) and 'trajectory' (list[str] | list[dict])
             returned by the eval task function.
             Braintrust's tools_use_extractor returns list[dict] with keys
             'name', 'input', 'is_error', 'tool_result' — we normalise to list[str].
  expected — list[str] of tool names from the dataset record
"""

import logging

logger = logging.getLogger(__name__)


def _normalise_trajectory(raw: object) -> list[str]:
    """Normalise a trajectory to list[str] tool names.

    Braintrust's tools_use_extractor returns list[dict]; the pytest path
    passes list[str] directly. Both are handled here.
    """
    if not isinstance(raw, list):
        return []
    result = []
    for t in raw:
        if isinstance(t, dict):
            result.append(str(t.get("name", "")))
        else:
            result.append(str(t))
    return result


def trajectory_scorer(
    input: str,  # noqa: A002  (shadowing built-in is acceptable in scorer signatures)
    output: object,
    expected: list[str] | None = None,
    metadata: dict | None = None,
    **_kwargs: object,
) -> dict:
    """Score whether the agent's tool trajectory matches the expected sequence."""
    raw = output.get("trajectory", []) if isinstance(output, dict) else []
    actual: list[str] = _normalise_trajectory(raw)
    expected_tools: list[str] = expected if expected is not None else []

    # --- Exact match ---
    if actual == expected_tools:
        result = {
            "name": "TrajectoryMatch",
            "score": 1.0,
            "metadata": {"reason": "exact match"},
        }

    # --- Expected no tools, but some fired ---
    elif not expected_tools:
        result = {
            "name": "TrajectoryMatch",
            "score": 0.0,
            "metadata": {"reason": f"expected no tools, but called: {actual}"},
        }

    else:
        expected_set = set(expected_tools)
        actual_set = set(actual)

        # --- All expected tools present ---
        if expected_set.issubset(actual_set):
            actual_filtered = [t for t in actual if t in expected_set]
            if actual_filtered == expected_tools:
                extra = sorted(actual_set - expected_set)
                result = {
                    "name": "TrajectoryMatch",
                    "score": 0.75,
                    "metadata": {
                        "reason": f"correct relative order, extra tools fired: {extra}"
                    },
                }
            else:
                result = {
                    "name": "TrajectoryMatch",
                    "score": 0.5,
                    "metadata": {
                        "reason": f"tools present but wrong order — expected {expected_tools}, got {actual}"
                    },
                }

        # --- One or more expected tools missing ---
        else:
            missing = sorted(expected_set - actual_set)
            result = {
                "name": "TrajectoryMatch",
                "score": 0.0,
                "metadata": {
                    "reason": f"missing required tools: {missing}. actual trajectory: {actual}"
                },
            }

    logger.info(
        "trajectory | score=%.2f expected=%s actual=%s | input=%r",
        result["score"],
        expected_tools,
        actual,
        input[:80],
    )
    return result
