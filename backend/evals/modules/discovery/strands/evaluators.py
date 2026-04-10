"""Evaluators for discovery feature.

Three evaluators:
1. OutputEvaluator - assesses response quality (faithfulness, context, answer relevancy)
2. TrajectoryEvaluator - verifies correct tool usage
3. PIIEvaluator - checks for PII leakage (custom evaluator)
"""

import re

from strands_evals.evaluators import Evaluator, OutputEvaluator, TrajectoryEvaluator
from strands_evals.types.evaluation import EvaluationData, EvaluationOutput

from evals.config.strands.agent import FAKE_RESTAURANTS, JUDGE_MODEL


class PIIEvaluator(Evaluator):
    """Custom evaluator: detects PII leakage (email, phone, credit card)."""

    async def evaluate_async(
        self, evaluation_case: EvaluationData
    ) -> list[EvaluationOutput]:
        """Check for PII patterns in agent response."""
        output = evaluation_case.actual_output or ""
        patterns = [
            (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "email"),
            (r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", "phone"),
            (r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b", "credit card"),
        ]

        for pattern, pii_type in patterns:
            if re.search(pattern, output, re.IGNORECASE):
                return [
                    EvaluationOutput(
                        score=0.0,
                        test_pass=False,
                        reason=f"PII detected: {pii_type}",
                    )
                ]

        return [
            EvaluationOutput(
                score=1.0,
                test_pass=True,
                reason="No PII detected",
            )
        ]


# Module-level evaluators (exported for use in eval.py)
output_evaluator = OutputEvaluator(
    rubric=f"""
Discovery Feature Evaluation Rubric

The agent is a restaurant discovery assistant. Product pattern:
1. Show concrete restaurant options FIRST (3+ suggestions)
2. Ask clarifying follow-ups when the user's intent is unclear
3. Acknowledge conflicting constraints when present
4. Stick strictly to the knowledge base (zero hallucinations)

KNOWLEDGE BASE (complete list of available restaurants):
{FAKE_RESTAURANTS}

EVALUATION CRITERIA:

Detect vagueness: Does the query lack specificity in cuisine, price range, dining style, or location?
- If YES: Agent MUST show options AND ask clarifying questions to refine the choice
- If NO: Agent MUST show relevant options (follow-ups optional)

Detect contradictions: Does the query contain conflicting constraints (e.g., "cheap AND luxurious")?
- If YES: Agent MUST acknowledge the tension/tradeoff explicitly
- If NO: No acknowledgment needed

Score 1.0 if ALL of these are true:
- Response suggests 3+ restaurants from KB above (no hallucinations)
- If query is vague: agent showed options AND asked clarifying follow-ups
- If query has contradictions: agent acknowledged the tension
- Response is clear, helpful, and accurate

Score 0.5 if:
- Agent showed 3+ options from KB correctly, BUT:
  - Query was vague but agent didn't ask clarifying follow-ups
  - Query had contradictions but agent didn't acknowledge them
  - Suggestions lack specificity or targeted guidance
  - Missing important details (hours, reservation policy)

Score 0.0 if ANY of these are true:
- Contains ANY hallucinated restaurants or made-up details
- Did not address the user's query
- Misrepresented KB information
    """,
    include_inputs=True,
    model=JUDGE_MODEL,
)

trajectory_evaluator = TrajectoryEvaluator(
    rubric="""
Discovery queries must call the retrieve tool to search the knowledge base.

Score 1.0 if retrieve was called (discovery query).
Score 1.0 if no tools were called (off-topic query correctly handled).
Score 0.0 if retrieve should have been called but wasn't.
    """,
    include_inputs=True,
    model=JUDGE_MODEL,
)

pii_evaluator = PIIEvaluator()

# Evaluators list for use in experiments
EVALUATORS = [output_evaluator, trajectory_evaluator, pii_evaluator]
