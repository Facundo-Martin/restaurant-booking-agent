"""Evaluation test case definitions, organized by feature.

Packages:
- common: Shared EvalCase dataclass
- agent_evals: Existing agent evaluation cases (OUTPUT_QUALITY_CASES, TRAJECTORY_CASES)
- discovery: New discovery feature evaluation cases
"""

# Re-export existing cases for backward compatibility
from evals.cases.agent_evals import OUTPUT_QUALITY_CASES, TRAJECTORY_CASES
from evals.cases.common import EvalCase

__all__ = ["EvalCase", "OUTPUT_QUALITY_CASES", "TRAJECTORY_CASES"]
