"""FastAPI application factory."""

import os

from aws_lambda_powertools import Logger
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.api.routes import bookings, chat
from app.exceptions import AppException
from app.middleware import CorrelationIdMiddleware, get_correlation_id
from app.models.schemas import ErrorDetail, ErrorResponse

logger = Logger(service="restaurant-booking")

app = FastAPI(
    title="Restaurant Booking Agent",
    description="FastAPI + Strands Agents backend for the restaurant booking assistant",
    version="0.1.0",
)

# CORS — only needed in local dev. In production, Lambda Function URL config
# and API Gateway handle CORS before the request reaches FastAPI.
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
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=ErrorDetail(code=exc.code, message=exc.message, request_id=get_correlation_id())
        ).model_dump(),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    # Covers FastAPI's own internal exceptions (405 Method Not Allowed, etc.)
    # that are never raised as AppException, keeping the error shape consistent.
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=ErrorDetail(code="HTTP_ERROR", message=str(exc.detail), request_id=get_correlation_id())
        ).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            error=ErrorDetail(code="VALIDATION_ERROR", message="Request validation failed.", request_id=get_correlation_id())
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception", extra={"path": request.url.path, "method": request.method})
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error=ErrorDetail(code="INTERNAL_ERROR", message="An unexpected error occurred.", request_id=get_correlation_id())
        ).model_dump(),
    )


@app.get("/health", operation_id="healthCheck")
def health() -> dict:
    """Return a simple liveness check response."""
    return {"status": "ok"}


@app.api_route("/", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
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
