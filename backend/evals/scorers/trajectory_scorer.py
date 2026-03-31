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

  output  — dict with keys 'output' (str) and 'trajectory' (list[str])
             returned by the eval task function
  expected — list[str] of tool names from the dataset record
"""


def trajectory_scorer(
    input: str,  # noqa: A002  (shadowing built-in is acceptable in scorer signatures)
    output: object,
    expected: list[str] | None = None,
    metadata: dict | None = None,
    **_kwargs: object,
) -> dict:
    """Score whether the agent's tool trajectory matches the expected sequence."""
    actual: list[str] = output.get("trajectory", []) if isinstance(output, dict) else []
    expected_tools: list[str] = expected if expected is not None else []

    # --- Exact match ---
    if actual == expected_tools:
        return {
            "name": "TrajectoryMatch",
            "score": 1.0,
            "metadata": {"reason": "exact match"},
        }

    # --- Expected no tools, but some fired ---
    if not expected_tools:
        return {
            "name": "TrajectoryMatch",
            "score": 0.0,
            "metadata": {"reason": f"expected no tools, but called: {actual}"},
        }

    expected_set = set(expected_tools)
    actual_set = set(actual)

    # --- All expected tools present ---
    if expected_set.issubset(actual_set):
        # Check relative order of expected tools within the actual sequence
        actual_filtered = [t for t in actual if t in expected_set]
        if actual_filtered == expected_tools:
            extra = sorted(actual_set - expected_set)
            return {
                "name": "TrajectoryMatch",
                "score": 0.75,
                "metadata": {
                    "reason": f"correct relative order, extra tools fired: {extra}"
                },
            }
        return {
            "name": "TrajectoryMatch",
            "score": 0.5,
            "metadata": {
                "reason": (
                    f"tools present but wrong order — "
                    f"expected {expected_tools}, got {actual}"
                )
            },
        }

    # --- One or more expected tools missing ---
    missing = sorted(expected_set - actual_set)
    return {
        "name": "TrajectoryMatch",
        "score": 0.0,
        "metadata": {
            "reason": f"missing required tools: {missing}. actual trajectory: {actual}"
        },
    }
