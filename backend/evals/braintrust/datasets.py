"""Dataset loading helpers with preflight guards.

Every eval runner should load its dataset through these helpers rather than
calling braintrust.init_dataset() directly. This enforces two invariants
before any eval work begins:

  1. The dataset is non-empty (catches missing seed step).
  2. The managed dataset row count matches the authored cases in evals/cases.py
     (catches silent drift between local cases and the Braintrust snapshot).
"""

import braintrust


def load_dataset(
    project: str,
    name: str,
    version: str | int | None,
) -> tuple[braintrust.Dataset, list]:
    """Load a Braintrust dataset, materialise its rows, and guard against empty results.

    Args:
        project: Braintrust project name.
        name: Dataset name.
        version: Pinned version to fetch, or None for latest.
                 In CI this should always be an explicit version.

    Returns:
        (dataset, rows) — the dataset handle and the materialised row list.

    Raises:
        RuntimeError: If the dataset is empty (likely not seeded yet).
    """
    dataset = braintrust.init_dataset(project=project, name=name, version=version)
    rows = list(dataset)
    if not rows:
        raise RuntimeError(
            f"Braintrust dataset '{name}' is empty. "
            "Run `pnpm eval:braintrust:seed` before running evals."
        )
    return dataset, rows


def assert_case_count_matches(
    rows: list,
    authored_cases: list,
    dataset_name: str,
) -> None:
    """Assert that the managed dataset has the same number of rows as the authored cases.

    A count mismatch means evals/cases.py and the Braintrust snapshot have
    drifted — either a case was added/removed locally without re-seeding, or
    the dataset was modified in Braintrust outside the seed script.

    Args:
        rows: Materialised rows from load_dataset().
        authored_cases: The authoritative list from evals/cases.py.
        dataset_name: Dataset name used in the error message.

    Raises:
        RuntimeError: If the counts differ.
    """
    if len(rows) != len(authored_cases):
        raise RuntimeError(
            f"Dataset '{dataset_name}' has {len(rows)} rows in Braintrust "
            f"but evals/cases.py defines {len(authored_cases)} cases. "
            "Re-run `pnpm eval:braintrust:seed` to sync them."
        )
