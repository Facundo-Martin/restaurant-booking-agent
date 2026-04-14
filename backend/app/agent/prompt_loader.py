"""Runtime loader for the agent system prompt.

Falls back to the local checked-in prompt unless Braintrust prompt selection is
explicitly enabled via environment variables.

Two entry points:
  load_system_prompt_bundle() — returns a LoadedPrompt with text + provenance.
  load_system_prompt()        — convenience wrapper; returns only the text string.
"""

import os
from dataclasses import dataclass

import braintrust
from app.agent.prompts import SYSTEM_PROMPT
from evals.braintrust.config import BRAINTRUST_PROJECT, SYSTEM_PROMPT_SLUG


@dataclass(frozen=True)
class LoadedPrompt:
    """Loaded system prompt with provenance metadata.

    Attributes:
        text: The prompt text string.
        slug: Prompt slug (for Braintrust tracking).
        version: Braintrust _xact_id (e.g., "5878bd218351fb8e"); None for local prompts.
        environment: Braintrust environment name; None if version is set.
        source: Either "local" or "braintrust".
    """

    text: str
    slug: str
    version: str | None
    environment: str | None
    source: str


def _resolve_params() -> tuple[str | None, str | None]:
    """Read version/environment from env vars. Version takes precedence."""
    version = os.environ.get("BRAINTRUST_PROMPT_VERSION")
    environment = None if version else os.environ.get("BRAINTRUST_PROMPT_ENVIRONMENT")
    return version, environment


def _extract_system_prompt(messages: list[dict[str, object]]) -> str:
    if len(messages) != 1 or messages[0].get("role") != "system":
        raise ValueError("Managed prompt must compile to exactly one system message")

    content = messages[0].get("content")
    if not isinstance(content, str) or not content:
        raise ValueError(
            "Managed prompt system message content must be a non-empty string"
        )
    return content


def load_system_prompt_bundle() -> LoadedPrompt:
    """Load the prompt and return its text together with version metadata.

    Uses the local checked-in prompt when no env vars are set.
    When BRAINTRUST_PROMPT_VERSION or BRAINTRUST_PROMPT_ENVIRONMENT is set,
    fetches the managed prompt from Braintrust and captures its _xact_id as
    the version — useful for recording which prompt version an eval ran against.
    """
    version, environment = _resolve_params()

    if not version and not environment:
        return LoadedPrompt(
            text=SYSTEM_PROMPT,
            slug=SYSTEM_PROMPT_SLUG,
            version=None,
            environment=None,
            source="local",
        )

    prompt = braintrust.load_prompt(
        project=BRAINTRUST_PROJECT,
        slug=SYSTEM_PROMPT_SLUG,
        version=version,
        environment=environment,
    )
    built = prompt.build()
    messages = built.get("messages")
    if not isinstance(messages, list):
        raise ValueError("Managed prompt build() must return a messages list")
    text = _extract_system_prompt(messages)

    return LoadedPrompt(
        text=text,
        slug=prompt.slug,
        version=prompt.version,  # _xact_id assigned by Braintrust on push
        environment=environment,
        source="braintrust",
    )


def load_system_prompt() -> str:
    """Convenience wrapper — returns only the prompt text string."""
    return load_system_prompt_bundle().text
