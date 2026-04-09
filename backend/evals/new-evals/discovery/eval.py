"""Discovery Feature Evaluation — Strands Evals

Evaluates restaurant discovery agent on:
- Output quality (faithfulness, context, answer relevancy)
- Tool usage (retrieve must be called)
- PII safety (no email/phone/card leakage)

Run from backend/:
    PYTHONPATH=. uv run python evals/new-evals/discovery/eval.py

Requires SST resource stubs:
    export SST_RESOURCE_Bookings='{"name":"test-table"}'
    export SST_RESOURCE_RestaurantKB='{"id":"test-kb-id"}'
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from strands import Agent
from strands_evals import Case, Experiment
from strands_evals.extractors import tools_use_extractor

# Load .env before importing app.agent.core (config reads SST links at import time)
load_dotenv()

# noqa: E402 — imports must come after load_dotenv() for SST resource links
from agent import (  # noqa: E402
    AGENT_MODEL,
    AGENT_RETRY_STRATEGY,
    AGENT_SYSTEM_PROMPT,
    EVAL_TOOLS,
)
from cases import CASES  # noqa: E402
from evaluators import EVALUATORS  # noqa: E402
from utils import print_summary, save_report  # noqa: E402

_PASS_THRESHOLD = 0.85


async def get_discovery_response(case: Case) -> dict:
    """Run discovery agent on a test case and extract trajectory."""
    print(f"  Running case: {case.name!r} ...", flush=True)

    agent = Agent(
        model=AGENT_MODEL,
        tools=EVAL_TOOLS,
        system_prompt=AGENT_SYSTEM_PROMPT,
        callback_handler=None,
        retry_strategy=AGENT_RETRY_STRATEGY,
    )

    response = await agent.invoke_async(case.input)
    trajectory = tools_use_extractor.extract_agent_tools_used_from_messages(
        agent.messages
    )

    print(f"  Done: {case.name!r}", flush=True)
    return {"output": str(response), "trajectory": trajectory}


experiment = Experiment(cases=CASES, evaluators=EVALUATORS)


async def main() -> None:
    """Run discovery evaluation async with rate limiting."""
    print(f"\n{'=' * 70}")
    print("Discovery Evaluation")
    print(f"{'=' * 70}\n")
    print(f"Running {len(CASES)} cases (max 1 concurrent) ...\n", flush=True)

    # Rate limit to 1 concurrent to avoid Bedrock throttling
    _sem = asyncio.Semaphore(1)

    async def _rate_limited(case: Case) -> dict:
        async with _sem:
            result = await get_discovery_response(case)
            await asyncio.sleep(1)  # Delay between cases to avoid throttling
            return result

    reports = await experiment.run_evaluations_async(_rate_limited)

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70 + "\n")

    # Save report
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("experiment_files")
    evaluator_names = [e.__class__.__name__ for e in EVALUATORS]
    out_path = save_report(experiment, reports, ts, output_dir, evaluator_names)
    print(f"✅ Results saved to {out_path}\n")

    # Print summary and check pass rates
    print_summary(reports, evaluator_names, threshold=_PASS_THRESHOLD)

    # Determine pass/fail
    all_pass = all(
        (sum(1 for p in report.test_passes if p) / len(report.test_passes))
        >= _PASS_THRESHOLD
        for report in reports
    )

    if not all_pass:
        print(
            f"ERROR: At least one evaluator below {_PASS_THRESHOLD:.0%} threshold",
            file=sys.stderr,
        )
        sys.exit(1)

    print("✅ All evaluators passed!\n")


if __name__ == "__main__":
    asyncio.run(main())
