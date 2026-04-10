"""
Shared utility functions for evals with full type hints.
"""

import json
from pathlib import Path
from typing import Any

from strands_evals import Experiment
from strands_evals.types.evaluation_report import EvaluationReport


def save_report(
    experiment: Experiment,
    reports: list[EvaluationReport],
    ts: str,
    output_dir: Path,
    evaluator_names: list[str],
    responses: dict[str, dict] | None = None,
) -> Path:
    """
    Save evaluation results to JSON with proper evaluator labeling.

    Args:
        experiment: Experiment object containing test cases
        reports: List of EvaluationReport objects (one per evaluator)
        ts: Timestamp string for filename (format: YYYYMMDD_HHMMSS)
        output_dir: Directory to save the report file
        evaluator_names: List of evaluator names (must match report order)
        responses: Dict mapping case names to {output, trajectory} dicts

    Returns:
        Path to the saved JSON report file
    """
    case_results: list[dict[str, Any]] = []
    responses = responses or {}

    # Iterate through evaluators and label them correctly
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
            # VALIDATION: Check if reason seems related to case (simple heuristic)
            # Flag if reason mentions specific restaurants/queries not in this case
            reason_lower = reason.lower()
            input_lower = case.input.lower()

            # Check for obvious mismatches (e.g., "cheap AND luxurious" in reason but "Italian food" in input)
            if "cheap" in reason_lower and "luxurious" in reason_lower:
                if (
                    "cheap" not in input_lower
                    and "luxurious" not in input_lower
                    and "contradictory" not in input_lower
                ):
                    print(
                        f"⚠️  WARNING: Reason mentions 'cheap/luxurious' but case '{case.name}' input is: {case.input}"
                    )
            if "gluten" in reason_lower and "soy" in reason_lower:
                if "gluten" not in input_lower and "soy" not in input_lower:
                    print(
                        f"⚠️  WARNING: Reason mentions 'gluten-free soy' but case '{case.name}' input is: {case.input}"
                    )

            result_dict = {
                "name": case.name,
                "input": case.input,
                "expected_trajectory": case.expected_trajectory,
                "evaluator": evaluator_name,
                "score": score,
                "test_pass": test_pass,
                "reason": reason,
            }
            # Include LLM output if available
            if case.name in responses:
                result_dict["llm_output"] = responses[case.name].get("output", "")
            case_results.append(result_dict)

    data = {
        "timestamp": ts,
        "total_cases": len(experiment.cases),
        "case_results": case_results,
    }

    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"eval_{ts}.json"
    output_path.write_text(json.dumps(data, indent=2))

    return output_path


def print_summary(
    reports: list[EvaluationReport],
    evaluator_names: list[str],
    threshold: float = 0.85,
) -> None:
    """
    Print evaluation summary.

    Args:
        reports: List of EvaluationReport objects
        evaluator_names: List of evaluator names (must match report order)
        threshold: Pass rate threshold (default: 0.85)
    """
    print("\n" + "=" * 70)
    print("EVALUATION SUMMARY")
    print("=" * 70 + "\n")

    for idx, report in enumerate(reports):
        evaluator_name = (
            evaluator_names[idx] if idx < len(evaluator_names) else f"Evaluator{idx}"
        )
        passed = sum(1 for p in report.test_passes if p)
        total = len(report.test_passes)
        pass_rate = passed / total if total > 0 else 0

        status = "✅ PASS" if pass_rate >= threshold else "❌ FAIL"
        print(f"{status} | {evaluator_name}: {passed}/{total} ({pass_rate:.0%})")

    print(f"\nTarget: ≥{threshold:.0%} per evaluator")
    print("=" * 70 + "\n")
