"""Shared utilities for test case definitions."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvalCase:
    """A single test case for evaluation."""

    id: str  # stable identifier (used in Braintrust)
    input: str  # user message or input
    expected: dict | str | list  # expected output (rubric, answer, or trajectory)
    metadata: dict = field(default_factory=dict)  # categorization and debugging info


__all__ = ["EvalCase"]
