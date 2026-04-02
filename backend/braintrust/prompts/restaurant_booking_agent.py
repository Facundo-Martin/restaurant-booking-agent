"""Push the Restaurant Booking Agent system prompt to Braintrust."""

import braintrust
from app.agent.prompts import SYSTEM_PROMPT
from evals.braintrust.config import (
    BRAINTRUST_PROJECT,
    SYSTEM_PROMPT_NAME,
    SYSTEM_PROMPT_SLUG,
)

project = braintrust.projects.create(name=BRAINTRUST_PROJECT)

project.prompts.create(
    name=SYSTEM_PROMPT_NAME,
    slug=SYSTEM_PROMPT_SLUG,
    description="System prompt for the Restaurant Booking Agent",
    model="bedrock/us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    messages=[{"role": "system", "content": SYSTEM_PROMPT}],
    if_exists="replace",
)
