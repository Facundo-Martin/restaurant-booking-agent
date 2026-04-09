"""Evaluators for discovery feature.

Three evaluators:
1. OutputEvaluator - assesses response quality (faithfulness, context, answer relevancy)
2. TrajectoryEvaluator - verifies correct tool usage
3. PIIEvaluator - checks for PII leakage (custom evaluator)
"""

import re

from agent import FAKE_RESTAURANTS, JUDGE_MODEL
from strands_evals.evaluators import Evaluator, OutputEvaluator, TrajectoryEvaluator
from strands_evals.types.evaluation import EvaluationData, EvaluationOutput


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
The agent is a restaurant discovery assistant. Evaluate the response on three dimensions:

1. AnswerRelevancy: Does it answer the user's query?
2. Faithfulness: Does it stick to the knowledge base without hallucinating?
3. ContextRelevancy: Is the retrieved context appropriate for the query?

KNOWLEDGE BASE (the complete list of restaurants available):
{FAKE_RESTAURANTS}

HALLUCINATION RULE: Any restaurant name or detail not listed above is hallucination.
If ANY hallucination is detected, the score must be 0.0 regardless of other factors.

Score 1.0 if the response:
- Directly answers the user's question
- Only mentions restaurants from the KB above
- No hallucinations whatsoever
- Is clear and helpful

Score 0.5 if the response:
- Partially answers the query
- Mostly uses KB data correctly
- Uses somewhat relevant context

Score 0.0 if the response:
- Contains ANY hallucinated restaurants or details
- Does not address the user's query
- Misrepresents KB information
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
