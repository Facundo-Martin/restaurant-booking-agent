import os

from sst import Resource

# SST injects these at deploy time — no SSM calls, no hardcoded ARNs.
# At runtime (Lambda + sst dev), Resource reads from environment variables
# that SST populated during deployment.
TABLE_NAME: str = Resource.Bookings.name  # type: ignore[attr-defined]
KB_ID: str = Resource.RestaurantKB.id  # type: ignore[attr-defined]

# Input validation limits — tune here without touching the schema definitions.
CHAT_MAX_MESSAGE_LENGTH: int = 4096  # characters per individual message
CHAT_MAX_MESSAGES: int = 50          # messages per /chat request
BOOKING_MAX_SPECIAL_REQUESTS_LENGTH: int = 500

# Bedrock Guardrail — optional. When set, the guardrail is evaluated on every
# model invocation before the response reaches the agent. Leave unset in dev/test;
# set via SST link once a guardrail is deployed (see infra/ai.ts).
# BEDROCK_GUARDRAIL_VERSION defaults to "DRAFT" so the latest saved version is
# used automatically during the guardrail authoring phase.
GUARDRAIL_ID: str | None = os.environ.get("BEDROCK_GUARDRAIL_ID")
GUARDRAIL_VERSION: str = os.environ.get("BEDROCK_GUARDRAIL_VERSION", "DRAFT")
