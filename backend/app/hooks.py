"""Strands agent hooks for observability and safety."""

from threading import Lock
from typing import Any

from strands.hooks import (
    AfterInvocationEvent,
    BeforeInvocationEvent,
    BeforeToolCallEvent,
    HookProvider,
    HookRegistry,
)

from app.logging import logger
from app.metrics import MetricUnit, metrics
from app.middleware import get_correlation_id


class CorrelationIdHook(HookProvider):  # pylint: disable=too-few-public-methods
    """Inject the request correlation ID into the logger at the start of each invocation.

    Without this, log lines emitted inside the Strands event loop (model calls,
    tool calls) lack the correlation_id key that the rest of the request logs carry.
    """

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeInvocationEvent, self._inject)

    def _inject(self, _event: BeforeInvocationEvent) -> None:
        logger.append_keys(correlation_id=get_correlation_id())


class TokenMetricsHook(HookProvider):  # pylint: disable=too-few-public-methods
    """Emit token usage and agent cycle count to CloudWatch after each invocation.

    Reads from AgentResult.metrics.accumulated_usage — populated by Strands
    internally during stream_async. Provides per-request cost visibility
    without any manual tracking.
    """

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(AfterInvocationEvent, self._emit)

    def _emit(self, event: AfterInvocationEvent) -> None:
        if event.result is None:
            return
        usage = event.result.metrics.accumulated_usage
        metrics.add_metric("InputTokens", MetricUnit.Count, usage.get("inputTokens", 0))
        metrics.add_metric(
            "OutputTokens", MetricUnit.Count, usage.get("outputTokens", 0)
        )
        metrics.add_metric(
            "AgentCycles", MetricUnit.Count, event.result.metrics.cycle_count
        )


class LimitToolCallsHook(HookProvider):
    """Cancel tool calls that exceed a per-request limit.

    Prevents runaway agent loops from accumulating unbounded Bedrock costs.
    Counts reset at the start of each invocation via BeforeInvocationEvent.

    Args:
        max_tool_counts: mapping of tool_name → max allowed calls per invocation.
            Tools not listed are unlimited.
    """

    def __init__(self, max_tool_counts: dict[str, int]) -> None:
        self._limits = max_tool_counts
        self._counts: dict[str, int] = {}
        self._lock = Lock()  # tool callbacks may run concurrently with executor

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeInvocationEvent, self._reset_counts)
        registry.add_callback(BeforeToolCallEvent, self._check)

    def _reset_counts(self, _event: BeforeInvocationEvent) -> None:
        with self._lock:
            self._counts = {}

    def _check(self, event: BeforeToolCallEvent) -> None:
        tool_name = event.tool_use["name"]
        with self._lock:
            max_count = self._limits.get(tool_name)
            count = self._counts.get(tool_name, 0) + 1
            self._counts[tool_name] = count
        if max_count and count > max_count:
            event.cancel_tool = (
                f"Tool '{tool_name}' has been invoked too many times and is now being throttled. "
                f"DO NOT CALL THIS TOOL ANYMORE."
            )
            logger.warning(
                "Tool call cancelled — limit exceeded",
                extra={"tool_name": tool_name, "count": count, "limit": max_count},
            )
