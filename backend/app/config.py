"""Application configuration loaded from SST Resource links at deploy time."""

import os

from sst import Resource

# SST injects these at deploy time — no SSM calls, no hardcoded ARNs.
# At runtime (Lambda + sst dev), Resource reads from environment variables
# that SST populated during deployment.
TABLE_NAME: str = Resource.Bookings.name  # type: ignore[attr-defined]
KB_ID: str = Resource.RestaurantKB.id  # type: ignore[attr-defined]
SESSIONS_BUCKET: str = Resource.AgentSessions.name  # type: ignore[attr-defined]

# Input validation limits — tune here without touching the schema definitions.
CHAT_MAX_MESSAGE_LENGTH: int = 4096  # characters per individual message
CHAT_MAX_MESSAGES: int = 50  # messages per /chat request
BOOKING_MAX_SPECIAL_REQUESTS_LENGTH: int = 500

# Agent stream timeout — hard upper bound on how long a single chat turn can run.
# Set below the 120s Lambda timeout to guarantee the SSE done event is emitted
# before Lambda kills the execution environment mid-stream.
# Retries multiply wait time (boto3 standard mode: up to 3 × Bedrock latency),
# so a timeout is necessary even with retries in place.
MAX_AGENT_SECONDS: int = 110

# Bedrock Guardrail — injected via SST link from infra/ai.ts (RestaurantGuardrail).
# GUARDRAIL_VERSION is the published version string; "DRAFT" uses the latest saved draft,
# which is fine during authoring. Pin to "1" (or higher) for production deployments.
# Falls back to env vars so local uvicorn runs without a linked guardrail still work.
# getattr() cannot be used here — SST raises Exception (not AttributeError) when links
# are inactive, bypassing getattr's default. A try/except is required.
try:
    GUARDRAIL_ID: str | None = Resource.RestaurantGuardrail.id  # type: ignore[attr-defined]
    GUARDRAIL_VERSION: str = Resource.RestaurantGuardrail.version  # type: ignore[attr-defined]
except Exception:  # pylint: disable=broad-exception-caught
    GUARDRAIL_ID = os.environ.get("BEDROCK_GUARDRAIL_ID")
    GUARDRAIL_VERSION = os.environ.get("BEDROCK_GUARDRAIL_VERSION", "DRAFT")

# Stage name — injected by SST at deploy time via APP_STAGE env var; falls back to "dev" locally.
APP_STAGE: str = os.environ.get("APP_STAGE", "dev")
