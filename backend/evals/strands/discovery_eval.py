"""
Strands Discovery Eval — RAG evaluation for discovery queries.

Replaces evals/braintrust/eval_discovery.py using Strands Evals natively
(no Braintrust/autoevals dependency). Evaluates:
1. OutputEvaluator — faithfulness, context relevancy, answer relevancy combined
2. TrajectoryEvaluator — correct tool usage (retrieve must be called)
3. PIIEvaluator — no PII leakage in responses

Run from backend/ directory:
    PYTHONPATH=. uv run python evals/strands/discovery_eval.py

SST resource stubs loaded from backend/.env automatically.
"""

import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from strands import Agent
from strands import tool as strands_tool
from strands.models import BedrockModel
from strands_evals import Case, Experiment
from strands_evals.evaluators import Evaluator, OutputEvaluator, TrajectoryEvaluator
from strands_evals.extractors import tools_use_extractor
from strands_evals.types import EvaluationOutput
from strands_evals.types.evaluation import EvaluationData
from strands_tools import retrieve as _real_retrieve

# Load .env before importing app.agent.core — config.py reads SST resource links at
# import time and will raise if the env vars aren't present.
load_dotenv()

from app.agent.core import RETRY_STRATEGY, SYSTEM_PROMPT, TOOLS  # noqa: E402
from evals.cases.discovery import DISCOVERY_CASES  # noqa: E402

# Agent model: Haiku is fast, cheap, and capable for discovery evaluation
_AGENT_MODEL = BedrockModel(
    model_id="us.anthropic.claude-3-5-haiku-20241022-v1:0",
    additional_request_fields={"thinking": {"type": "disabled"}},
)

# Judge model: Haiku for scoring
_JUDGE_MODEL = "us.anthropic.claude-3-5-haiku-20241022-v1:0"

# Canned restaurant list — deterministic responses for consistent scoring
_FAKE_RESTAURANTS = (
    "Available restaurants: Nonna's Hearth (Italian, open daily, accepts reservations), "
    "Bistro Parisienne (French, closed Mondays, accepts reservations), "
    "Sakura Garden (Japanese, open daily, accepts reservations)."
)


# Fake retrieve tool — replaces the real Bedrock KB call during evals
@strands_tool
def retrieve(query: str) -> str:
    """Search the knowledge base for restaurants, menus, and availability."""
    return _FAKE_RESTAURANTS


_EVAL_TOOLS = [retrieve if t is _real_retrieve else t for t in TOOLS]


# ============================================================================
# Custom Evaluators
# ============================================================================


class PIIEvaluator(Evaluator):
    """Custom evaluator: no PII leakage (email, phone, credit card)."""

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


# ============================================================================
# Test Cases
# ============================================================================

test_cases = [
    Case(
        name=c.id,
        input=c.input,
        expected_output=c.expected["description"],
        expected_trajectory=c.expected["should_call"],
        metadata=c.metadata,
    )
    for c in DISCOVERY_CASES
]

# ============================================================================
# Evaluators
# ============================================================================

output_evaluator = OutputEvaluator(
    rubric="""
    The agent is a restaurant discovery assistant. Evaluate the response on three dimensions:

    1. AnswerRelevancy: Does it answer the user's query?
    2. Faithfulness: Does it stick to the knowledge base without hallucinating restaurants?
    3. ContextRelevancy: Is the retrieved context appropriate for the query?

    Knowledge base context provided in metadata.

    Score 1.0 if the response:
    - Directly answers the user's question
    - Only mentions restaurants/details from the knowledge base
    - Uses relevant context appropriately
    - Is clear and helpful

    Score 0.5 if the response:
    - Partially answers the query
    - Mostly uses KB data with minor hallucination
    - Uses somewhat relevant context

    Score 0.0 if the response:
    - Hallucinates restaurants or details not in knowledge base
    - Does not address the user's query
    - Uses irrelevant or contradictory context
    """,
    include_inputs=True,
    model=_JUDGE_MODEL,
)

trajectory_evaluator = TrajectoryEvaluator(
    rubric="""
    Discovery queries must call the retrieve tool to search the knowledge base.

    Score 1.0 if retrieve was called (discovery query).
    Score 1.0 if no tools were called (off-topic query correctly handled).
    Score 0.0 if retrieve should have been called but wasn't.
    """,
    include_inputs=True,
    model=_JUDGE_MODEL,
)

pii_evaluator = PIIEvaluator()

# ============================================================================
# Task Function
# ============================================================================


async def get_discovery_response(case: Case) -> dict:
    """Run discovery agent on a test case."""
    print(f"  Running case: {case.name!r} ...", flush=True)

    agent = Agent(
        model=_AGENT_MODEL,
        tools=_EVAL_TOOLS,
        system_prompt=SYSTEM_PROMPT,
        callback_handler=None,
        retry_strategy=RETRY_STRATEGY,
    )

    response = await agent.invoke_async(case.input)
    trajectory = tools_use_extractor.extract_agent_tools_used_from_messages(
        agent.messages
    )

    print(f"  Done: {case.name!r}", flush=True)
    return {"output": str(response), "trajectory": trajectory}


# ============================================================================
# Reporting
# ============================================================================

_PASS_THRESHOLD = 0.85


def _save_report(experiment: object, reports: list, ts: str) -> Path:
    """Save per-case results and summary statistics."""
    case_results = []
    # Evaluators are returned in order: OutputEvaluator, TrajectoryEvaluator, PIIEvaluator
    evaluator_names = ["OutputEvaluator", "TrajectoryEvaluator", "PIIEvaluator"]

    for idx, report in enumerate(reports):
        evaluator_name = (
            evaluator_names[idx] if idx < len(evaluator_names) else f"Evaluator{idx}"
        )
        for case, score, test_pass, reason in zip(
            experiment.cases,
            report.scores,
            report.test_passes,
            report.reasons,
            strict=True,
        ):
            case_results.append(
                {
                    "name": case.name,
                    "input": case.input,
                    "expected_trajectory": case.expected_trajectory,
                    "evaluator": evaluator_name,
                    "score": score,
                    "test_pass": test_pass,
                    "reason": reason,
                }
            )

    data = {
        "timestamp": ts,
        "total_cases": len(experiment.cases),
        "case_results": case_results,
    }

    out_dir = Path("evals/strands/experiment_files")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"discovery_eval_{ts}.json"
    out_path.write_text(json.dumps(data, indent=2))
    return out_path


# ============================================================================
# Main
# ============================================================================


async def main() -> None:
    """Run discovery evaluation async with rate limiting."""
    experiment = Experiment(
        cases=test_cases,
        evaluators=[output_evaluator, trajectory_evaluator, pii_evaluator],
    )

    # Rate limit to 1 concurrent to avoid Bedrock throttling
    _sem = asyncio.Semaphore(1)

    async def _rate_limited(case: Case) -> dict:
        async with _sem:
            result = await get_discovery_response(case)
            await asyncio.sleep(1)  # Delay between cases to avoid throttling
            return result

    print(f"\n{'=' * 70}")
    print("Discovery Evaluation (Strands Evals)")
    print(f"{'=' * 70}\n")
    print(f"Running {len(test_cases)} cases (max 2 concurrent) ...\n", flush=True)

    reports = await experiment.run_evaluations_async(_rate_limited)

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70 + "\n")

    # Summary
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = _save_report(experiment, reports, ts)
    print(f"\n✅ Results saved to {out_path}\n")

    # Check pass rates
    all_pass = True
    for report in reports:
        passed = sum(1 for p in report.test_passes if p)
        pass_rate = passed / len(report.test_passes)
        evaluator_name = report.__class__.__name__
        status = "✅ PASS" if pass_rate >= _PASS_THRESHOLD else "❌ FAIL"
        print(
            f"{status} | {evaluator_name}: {passed}/{len(report.test_passes)} ({pass_rate:.0%})"
        )
        if pass_rate < _PASS_THRESHOLD:
            all_pass = False

    print(f"\nTarget: ≥{_PASS_THRESHOLD:.0%} per evaluator")
    print("=" * 70 + "\n")

    if not all_pass:
        print(
            f"ERROR: At least one evaluator below {_PASS_THRESHOLD:.0%} threshold",
            file=sys.stderr,
        )
        sys.exit(1)

    print("✅ All evaluators passed!\n")


if __name__ == "__main__":
    asyncio.run(main())
