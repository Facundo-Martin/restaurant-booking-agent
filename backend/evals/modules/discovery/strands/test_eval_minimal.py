"""Minimal evaluation test to debug the 0% pass rate issue.

This mimics eval.py but runs with just one case and verbose error handling.

Run from backend/:
    PYTHONPATH=.:evals/new-evals uv run python evals/new-evals/discovery/test_eval_minimal.py
"""

import asyncio
import sys

from dotenv import load_dotenv
from strands import Agent
from strands_evals import Case, Experiment
from strands_evals.extractors import tools_use_extractor

# Load .env before importing app modules (config reads SST links at import time)
load_dotenv()

# noqa: E402 — imports must come after load_dotenv() for SST resource links
from evals.config.strands.agent import (  # noqa: E402
    AGENT_MODEL,
    AGENT_RETRY_STRATEGY,
    AGENT_SYSTEM_PROMPT,
    EVAL_TOOLS,
)
from evals.modules.discovery.cases import DISCOVERY_CASES as CASES  # noqa: E402
from evals.modules.discovery.strands.evaluators import EVALUATORS  # noqa: E402


async def test_minimal():
    """Test the evaluation pipeline to find the error."""
    print("=" * 70)
    print("MINIMAL EVAL TEST")
    print("=" * 70)
    print(f"\nNumber of cases: {len(CASES)}")
    print(f"Number of evaluators: {len(EVALUATORS)}")
    print(f"Evaluators: {[e.__class__.__name__ for e in EVALUATORS]}")

    # Test with first case
    case = CASES[0]
    print(f"\n=== Testing first case: {case.name} ===")
    print(f"Input: {case.input}")
    print(f"Expected output: {case.expected_output}")
    print(f"Expected trajectory: {case.expected_trajectory}")

    # Run agent
    print("\n--- Running agent ---")
    agent = Agent(
        model=AGENT_MODEL,
        tools=EVAL_TOOLS,
        system_prompt=AGENT_SYSTEM_PROMPT,
        callback_handler=None,
        retry_strategy=AGENT_RETRY_STRATEGY,
    )

    try:
        response = await agent.invoke_async(case.input)
        trajectory = tools_use_extractor.extract_agent_tools_used_from_messages(
            agent.messages
        )
        print("✅ Agent ran successfully")
        print(f"Response: {response}")
        print(f"Trajectory: {trajectory}")

        output_dict = {"output": str(response), "trajectory": trajectory}

        # Test Experiment
        print("\n--- Testing Experiment ---")

        async def dummy_task(case: Case) -> dict:
            """Dummy task that returns the same output for all cases."""
            return output_dict

        experiment = Experiment(cases=[case], evaluators=EVALUATORS)
        print("✅ Experiment created")
        print(f"  Cases: {len(experiment._cases)}")
        print(f"  Evaluators: {len(experiment._evaluators)}")

        print("\n--- Running evaluations ---")
        try:
            reports = await experiment.run_evaluations_async(dummy_task, max_workers=1)
            print("✅ Evaluations completed!")
            print(f"\nResults ({len(reports)} evaluators):")
            for i, report in enumerate(reports):
                print(f"  Report {i}:")
                print(f"    Type: {type(report)}")
                print(f"    Fields: {list(report.model_fields.keys())}")
                if hasattr(report, "test_passes"):
                    pass_rate = sum(1 for p in report.test_passes if p) / len(
                        report.test_passes
                    )
                    print(
                        f"    Pass rate: {pass_rate:.0%} ({sum(1 for p in report.test_passes if p)}/{len(report.test_passes)})"
                    )
                if hasattr(report, "overall_score"):
                    print(f"    Overall score: {report.overall_score}")

        except Exception as e:
            print("❌ ERROR in run_evaluations_async:")
            print(f"  {type(e).__name__}: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)

    except Exception as e:
        print(f"❌ ERROR: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    print("\n" + "=" * 70)
    print("✅ TEST PASSED")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_minimal())
