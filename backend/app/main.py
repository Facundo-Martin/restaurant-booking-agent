"""FastAPI application factory."""

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.api.routes import bookings, chat

app = FastAPI(
    title="Restaurant Booking Agent",
    description="FastAPI + Strands Agents backend for the restaurant booking assistant",
    version="0.1.0",
)

# CORS — only needed in local dev. In production, Lambda Function URL config
# and API Gateway handle CORS before the request reaches FastAPI.
if not os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )

app.include_router(chat.router)
app.include_router(bookings.router)


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
