"""Seed Braintrust evaluation datasets from the project's test cases.

Idempotent — uses a stable `id` per record so re-running updates rather than
duplicates. Run once to create datasets; re-run after adding / changing cases.

Credentials are loaded from backend/.env (copy .env.example → .env and fill in
BRAINTRUST_API_KEY + AWS_* values). No manual env-var exports needed.

Usage:
    cd backend
    uv run python scripts/create_braintrust_dataset.py
"""

import dataclasses
import sys
from pathlib import Path

from dotenv import load_dotenv

# Ensure the backend package roots (`app`, `evals`) are importable when this
# script is executed as `python scripts/create_braintrust_dataset.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Load .env before importing braintrust so BRAINTRUST_API_KEY is available.
load_dotenv()

import braintrust  # noqa: E402
from evals.braintrust.config import (  # noqa: E402
    BRAINTRUST_PROJECT,
    OUTPUT_QUALITY_DATASET,
    TRAJECTORY_DATASET,
)
from evals.cases import OUTPUT_QUALITY_CASES, TRAJECTORY_CASES  # noqa: E402


def seed_dataset(name: str, cases: list) -> None:
    """Push all cases to a Braintrust dataset, upserting by stable record ID."""
    dataset = braintrust.init_dataset(
        project=BRAINTRUST_PROJECT,
        name=name,
    )
    for case in cases:
        record = dataclasses.asdict(case)
        dataset.insert(
            input=record["input"],
            expected=record["expected"],
            metadata=record["metadata"],
            id=record["id"],
        )
    dataset.flush()
    print(f"  Seeded {len(cases)} records → '{name}'")


if __name__ == "__main__":
    print(f"Seeding Braintrust datasets for '{BRAINTRUST_PROJECT}' …")
    seed_dataset(OUTPUT_QUALITY_DATASET, OUTPUT_QUALITY_CASES)
    seed_dataset(TRAJECTORY_DATASET, TRAJECTORY_CASES)
    print(
        f"Done. View datasets at https://www.braintrust.dev under '{BRAINTRUST_PROJECT}'."
    )
