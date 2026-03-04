"""Custom Starlette middleware."""

import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------

_SECURITY_HEADERS = {
    # Prevent MIME-type sniffing — browser must honour the declared Content-Type.
    "X-Content-Type-Options": "nosniff",
    # Block the response from being embedded in a frame — mitigates clickjacking.
    "X-Frame-Options": "DENY",
    # Don't send the Referer header when navigating away — avoids leaking API URLs.
    "Referrer-Policy": "no-referrer",
    # Legacy XSS filter for older browsers; harmless on modern ones.
    "X-XSS-Protection": "1; mode=block",
    # Strict-Transport-Security is intentionally omitted — it belongs at the
    # API Gateway / CloudFront layer, not inside the application.
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach a fixed set of security headers to every response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.update(_SECURITY_HEADERS)
        return response


# One correlation ID per async context — safe across concurrent requests.
# ContextVar resets automatically when the async context ends, so there is
# no bleed between Lambda invocations that reuse the same execution environment.
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Return the correlation ID for the current request, or an empty string."""
    return _correlation_id.get()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach a correlation ID to every request and echo it in the response.

    - Honours an incoming ``X-Request-ID`` header (e.g. from an upstream proxy).
    - Generates a UUID v4 when no header is present.
    - Stores the ID in a ``ContextVar`` so any code in the call stack can read
      it via ``get_correlation_id()`` without it being passed explicitly.
    - Adds ``X-Request-ID`` to every response so clients can log it.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        cid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        _correlation_id.set(cid)
        response = await call_next(request)
        response.headers["X-Request-ID"] = cid
        return response
