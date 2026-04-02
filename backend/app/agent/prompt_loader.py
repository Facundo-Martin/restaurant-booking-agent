"""Runtime loader for the agent system prompt.

Falls back to the local checked-in prompt unless Braintrust prompt selection is
explicitly enabled via environment variables.
"""

import os

import braintrust
from app.agent.prompts import SYSTEM_PROMPT
from evals.braintrust.config import BRAINTRUST_PROJECT, SYSTEM_PROMPT_SLUG


def _extract_system_prompt(messages: list[dict[str, object]]) -> str:
    if len(messages) != 1 or messages[0].get("role") != "system":
        raise ValueError("Managed prompt must compile to exactly one system message")

    content = messages[0].get("content")
    if not isinstance(content, str) or not content:
        raise ValueError(
            "Managed prompt system message content must be a non-empty string"
        )
    return content


def load_system_prompt() -> str:
    """Load the managed Braintrust prompt when configured, else use local fallback."""
    version = os.environ.get("BRAINTRUST_PROMPT_VERSION")
    environment = None if version else os.environ.get("BRAINTRUST_PROMPT_ENVIRONMENT")

    if not version and not environment:
        return SYSTEM_PROMPT

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
    return _extract_system_prompt(messages)
