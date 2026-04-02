"""Typed provenance model for Braintrust evaluation experiments.

Every experiment should record a full artifact tuple so that repeated runs
of the same code remain reproducible and comparable across prompt/dataset changes.
"""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class EvalProvenance:
    project_name: str
    dataset_name: str
    dataset_version: str | int | None
    prompt_slug: str
    prompt_version: str | int | None
    prompt_environment: str | None
    agent_model_id: str
    judge_model_id: str | None
    scorer_version: str
    commit: str

    def to_metadata(self) -> dict[str, object]:
        return asdict(self)
