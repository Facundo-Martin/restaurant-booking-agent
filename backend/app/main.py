"""FastAPI application factory."""

import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.api.routes import bookings, chat
from app.exceptions import AppException
from app.logging import logger
from app.middleware import (
    CorrelationIdMiddleware,
    SecurityHeadersMiddleware,
    get_correlation_id,
)
from app.models.schemas import ErrorDetail, ErrorResponse

# Disable interactive docs on the live Lambda — /docs and /openapi.json are
# accessible to anyone with the Function URL and serve no purpose in production.
# The TypeScript client is regenerated from a local dev server instead.
_in_lambda = bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

app = FastAPI(
    title="Restaurant Booking Agent",
    description="FastAPI + Strands Agents backend for the restaurant booking assistant",
    version="0.1.0",
    docs_url=None if _in_lambda else "/docs",
    redoc_url=None if _in_lambda else "/redoc",
    openapi_url=None if _in_lambda else "/openapi.json",
)

app.add_middleware(SecurityHeadersMiddleware)
# CorrelationIdMiddleware must be inside SecurityHeadersMiddleware so the
# X-Request-ID header it adds is also covered by the security header pass.
app.add_middleware(CorrelationIdMiddleware)

if not os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )

app.include_router(chat.router)
app.include_router(bookings.router)


@app.exception_handler(AppException)
async def app_exception_handler(_request: Request, exc: AppException) -> JSONResponse:
    """Translate AppException into a structured JSON error response."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=ErrorDetail(
                code=exc.code, message=exc.message, request_id=get_correlation_id()
            )
        ).model_dump(),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    # Covers FastAPI's own internal exceptions (405 Method Not Allowed, etc.)
    # that are never raised as AppException, keeping the error shape consistent.
    """Translate FastAPI HTTPException into a structured JSON error response."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=ErrorDetail(
                code="HTTP_ERROR",
                message=str(exc.detail),
                request_id=get_correlation_id(),
            )
        ).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request, _exc: RequestValidationError
) -> JSONResponse:
    """Return 422 with a consistent error envelope for Pydantic validation failures."""
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            error=ErrorDetail(
                code="VALIDATION_ERROR",
                message="Request validation failed.",
                request_id=get_correlation_id(),
            )
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request, _exc: Exception
) -> JSONResponse:
    """Log and return 500 for any unhandled exception, without leaking internals."""
    logger.exception(
        "Unhandled exception",
        extra={"path": request.url.path, "method": request.method},
    )
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error=ErrorDetail(
                code="INTERNAL_ERROR",
                message="An unexpected error occurred.",
                request_id=get_correlation_id(),
            )
        ).model_dump(),
    )


@app.get("/health", operation_id="healthCheck")
def health() -> dict:
    """Return a simple liveness check response."""
    return {"status": "ok"}


@app.api_route(
    "/", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False
)
def root(request: Request) -> JSONResponse:
    """Catch-all for the API root — returns 404 with the valid endpoints listed.

    Hitting / usually means the client has the wrong URL (missing /chat or /bookings).
    """
    valid_endpoints = [
        f"{' '.join(sorted(route.methods - {'HEAD', 'OPTIONS'}))}  {route.path}"
        for route in request.app.routes
        if isinstance(route, APIRoute) and route.path != "/"
    ]
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not found. You have reached the API root.",
            "valid_endpoints": sorted(valid_endpoints),
        },
    )
