"""
Discovery feature test cases.

Organized by category:
- Baseline: happy path, normal usage
- Filtered: discovery with filters/constraints
- Ambiguous: vague or unclear queries
- Edge: boundary conditions
- Boundary: unusual inputs
"""

from strands_evals import Case

from evals.discovery.cases import DISCOVERY_CASES

# Import all discovery cases from the existing case definitions
# This reuses the 17 test cases already defined in evals/cases/discovery.py
CASES = [
    Case(
        name=c.id,
        input=c.input,
        expected_output=c.expected["description"],
        expected_trajectory=c.expected["should_call"],
        metadata=c.metadata,
    )
    for c in DISCOVERY_CASES
]
