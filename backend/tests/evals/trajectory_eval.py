# Requires AWS credentials with Bedrock InvokeModel access.
# Run from the backend/ directory:
#   PYTHONPATH=. uv run python -u tests/evals/trajectory_eval.py
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from strands import Agent
from strands.models import BedrockModel
from strands_evals import Case, Experiment
from strands_evals.evaluators import TrajectoryEvaluator
from strands_evals.extractors import tools_use_extractor
from strands_tools import calculator, current_time

# No SST deps — BedrockModel created directly.
_model = BedrockModel(
    model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    additional_request_fields={"thinking": {"type": "disabled"}},
)

# Haiku as judge: faster + cheaper than Sonnet with no meaningful accuracy loss for rubric scoring.
_JUDGE_MODEL = "us.anthropic.claude-3-5-haiku-20241022-v1:0"

_TOOLS = [calculator, current_time]


# Define async task function — cases run concurrently via run_evaluations_async
async def get_response_with_tools(case: Case) -> dict:
    print(f"  Running case: {case.name!r} ...", flush=True)
    agent = Agent(
        model=_model,
        tools=_TOOLS,
        system_prompt="You are a helpful assistant. Use tools when appropriate.",
        callback_handler=None,
    )
    response = await agent.invoke_async(case.input)
    trajectory = tools_use_extractor.extract_agent_tools_used_from_messages(
        agent.messages
    )
    print(f"  Done: {case.name!r}", flush=True)
    return {"output": str(response), "trajectory": trajectory}


# Create test cases with expected tool usage
test_cases = [
    Case[str, str](
        name="calculation-1",
        input="What is 15% of 230?",
        expected_trajectory=["calculator"],
        metadata={"category": "math"},
    ),
    Case[str, str](
        name="time-1",
        input="What time is it right now?",
        expected_trajectory=["current_time"],
        metadata={"category": "time"},
    ),
    Case[str, str](
        name="complex-1",
        input="What time is it and what is 25 * 48?",
        expected_trajectory=["current_time", "calculator"],
        metadata={"category": "multi-tool"},
    ),
]

# Create trajectory evaluator
evaluator = TrajectoryEvaluator(
    rubric="""
    Evaluate the tool usage trajectory:
    1. Correct tool selection — were the right tools chosen for the task?
    2. Proper sequence — were tools used in a logical order?
    3. Efficiency — were unnecessary tools avoided?

    Use the built-in scoring tools (exact_match_scorer, in_order_match_scorer,
    any_order_match_scorer) to verify trajectory matches.

    Score 1.0 if optimal tools used correctly.
    Score 0.5 if correct tools used but in a suboptimal sequence.
    Score 0.0 if wrong tools used or critical tools missing.
    """,
    include_inputs=True,
    model=_JUDGE_MODEL,
)

# Seed the evaluator with tool descriptions to prevent context overflow
sample_agent = Agent(model=_model, tools=_TOOLS, callback_handler=None)
evaluator.update_trajectory_description(
    tools_use_extractor.extract_tools_description(sample_agent, is_short=True)
)

_PASS_THRESHOLD = 0.85  # Fail CI if fewer than 85% of cases pass


def _save_report(experiment: object, report: object, ts: str, name: str) -> Path:
    """Save a rich JSON with per-case scores, reasons, and summary statistics.

    EvaluationReport exposes parallel lists (scores, test_passes, reasons) that
    align positionally with experiment.cases — zip them to produce per-case rows.
    """
    case_results = [
        {
            "name": case.name,
            "input": case.input,
            "expected_trajectory": case.expected_trajectory,
            "score": score,
            "test_pass": test_pass,
            "reason": reason,
            "metadata": case.metadata,
        }
        for case, score, test_pass, reason in zip(
            experiment.cases,
            report.scores,
            report.test_passes,
            report.reasons,
            strict=True,
        )
    ]

    passed = sum(1 for r in case_results if r["test_pass"])
    data = {
        "timestamp": ts,
        "overall_score": report.overall_score,
        "pass_rate": passed / len(case_results),
        "cases_passed": passed,
        "cases_total": len(case_results),
        "case_results": case_results,
    }

    out_dir = Path("tests/evals/experiment_files")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"{name}_{ts}.json"
    out_path.write_text(json.dumps(data, indent=2))
    return out_path


async def main() -> None:
    experiment = Experiment[str, str](cases=test_cases, evaluators=[evaluator])
    print(f"Running {len(test_cases)} cases concurrently ...", flush=True)
    reports = await experiment.run_evaluations_async(get_response_with_tools)
    print("Evaluations complete. Generating report ...", flush=True)

    print("=== Tool Trajectory Evaluation Results ===")
    report = reports[0]
    report.run_display()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = _save_report(experiment, report, ts, "trajectory_evaluation")
    print(f"\nResults saved to {out_path}")

    passed = sum(1 for p in report.test_passes if p)
    pass_rate = passed / len(report.test_passes)
    print(f"\nPass rate: {passed}/{len(report.test_passes)} ({pass_rate:.0%})")
    if pass_rate < _PASS_THRESHOLD:
        print(
            f"ERROR: pass rate {pass_rate:.0%} is below threshold {_PASS_THRESHOLD:.0%}",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
