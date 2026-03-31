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

from dotenv import load_dotenv

# Load .env before importing braintrust so BRAINTRUST_API_KEY is available.
load_dotenv()

import braintrust  # noqa: E402

from evals.cases import OUTPUT_QUALITY_CASES, TRAJECTORY_CASES  # noqa: E402


def seed_dataset(name: str, cases: list) -> None:
    """Push all cases to a Braintrust dataset, upserting by stable record ID."""
    dataset = braintrust.init_dataset(
        project="Restaurant Booking Agent",
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
    print("Seeding Braintrust datasets for 'Restaurant Booking Agent' …")
    seed_dataset("restaurant-agent-output-quality", OUTPUT_QUALITY_CASES)
    seed_dataset("restaurant-agent-trajectory", TRAJECTORY_CASES)
    print(
        "Done. View datasets at https://www.braintrust.dev under 'Restaurant Booking Agent'."
    )
