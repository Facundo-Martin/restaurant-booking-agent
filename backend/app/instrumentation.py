"""Braintrust tracing via Strands built-in telemetry + BraintrustSpanProcessor."""

import os

from braintrust.otel import BraintrustSpanProcessor
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from strands.telemetry import StrandsTelemetry

from sst import Resource as SSTResource

_provider: TracerProvider


def setup() -> None:
    """Register the Braintrust TracerProvider. Call once at application startup."""
    global _provider  # pylint: disable=global-statement

    # Bridge SST-linked secret into the env var that BraintrustSpanProcessor reads.
    os.environ["BRAINTRUST_API_KEY"] = SSTResource.BraintrustApiKey.value  # type: ignore[attr-defined]
    os.environ["BRAINTRUST_PARENT"] = "project_name:Restaurant Booking Agent"

    # Configure the global OTel tracer provider
    _provider = TracerProvider()
    trace.set_tracer_provider(_provider)

    # Add the Braintrust span processor to the tracer provider and configure Strands telemetry
    _provider.add_span_processor(BraintrustSpanProcessor())
    StrandsTelemetry(_provider)


def flush() -> None:
    """Flush buffered spans. Call before the Lambda response closes."""
    _provider.force_flush(timeout_millis=5000)
