"""Shared Braintrust constants for project, dataset, prompt, and experiment metadata.

Keep this module dependency-light — no braintrust imports, no boto3, no app imports.
It is the single source of truth for all stable identifiers used across eval runners,
scorers, and tests.
"""

# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------
BRAINTRUST_PROJECT = "Restaurant Booking Agent"

# ---------------------------------------------------------------------------
# Dataset names (stable identifiers — changing these creates new datasets)
# ---------------------------------------------------------------------------
OUTPUT_QUALITY_DATASET = "restaurant-agent-output-quality"
TRAJECTORY_DATASET = "restaurant-agent-trajectory"

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT_NAME = "Restaurant Booking Agent System Prompt"
SYSTEM_PROMPT_SLUG = "restaurant-booking-agent-system"
DEFAULT_PROMPT_ENVIRONMENT = "development"

# ---------------------------------------------------------------------------
# Model IDs
# ---------------------------------------------------------------------------
# Agent model used in evals — intentionally separate from the runtime model
# in app/agent/core.py so eval cost/latency is an explicit architectural choice.
EVAL_AGENT_MODEL_ID = "us.anthropic.claude-3-5-haiku-20241022-v1:0"

# Judge model used by the output-quality LLM-as-judge scorer.
EVAL_JUDGE_MODEL_ID = "us.anthropic.claude-3-5-haiku-20241022-v1:0"

# ---------------------------------------------------------------------------
# Scorer versions
# ---------------------------------------------------------------------------
# Increment these strings whenever the rubric or scoring logic changes so that
# score regressions in Braintrust can be correlated with scorer evolution.
OUTPUT_QUALITY_SCORER_VERSION = "output-quality-v2"
TRAJECTORY_SCORER_VERSION = "trajectory-v1"
WORKFLOW_SCORER_VERSION = "workflow-v1"
