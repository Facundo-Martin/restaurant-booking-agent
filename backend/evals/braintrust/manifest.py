"""Metadata attached to every Braintrust experiment run.

Braintrust automatically records git commit, branch, and dataset version.
This class captures the remaining fields useful for comparing runs:
prompt version, model IDs, and scorer version. The redundant fields
(commit, dataset_version, etc.) are included anyway for quick reference
in the UI without having to drill into repo_info or the dataset link.
"""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class EvalMetadata:
    # Core identifiers
    project_name: str
    dataset_name: str
    prompt_slug: str
    agent_model_id: str
    scorer_version: str
    commit: str
    # Optional — populated when known, None otherwise
    dataset_version: str | int | None = None
    prompt_version: str | int | None = (
        None  # Braintrust _xact_id, e.g. "5878bd218351fb8e"
    )
    prompt_environment: str | None = None
    judge_model_id: str | None = None  # None for evals that don't use an LLM judge

    def to_metadata(self) -> dict[str, object]:
        return asdict(self)
