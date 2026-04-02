"""Request-scoped context variables used by runtime and tool code."""

from contextvars import ContextVar

current_user_id: ContextVar[str] = ContextVar("current_user_id", default="anonymous")
