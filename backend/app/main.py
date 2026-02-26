"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import bookings, chat

app = FastAPI(
    title="Restaurant Booking Agent",
    description="FastAPI + Strands Agents backend for the restaurant booking assistant",
    version="0.1.0",
)

# CORS — in production the Lambda Function URL config handles this.
# In local dev (uvicorn), FastAPI must handle it so the browser allows
# requests from localhost:3000 to localhost:8000.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(bookings.router)


@app.get("/health")
def health() -> dict:
    """Return a simple liveness check response."""
    return {"status": "ok"}


@app.api_route("/", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def root() -> JSONResponse:
    """Catch-all for the API root — returns 404 with the valid endpoints listed.

    Hitting / usually means the client has the wrong URL (missing /chat or /bookings).
    """
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not found. You have reached the API root.",
            "valid_endpoints": [
                "POST  /chat",
                "GET   /bookings/{booking_id}?restaurant_name=...",
                "DELETE /bookings/{booking_id}?restaurant_name=...",
                "GET   /health",
            ],
        },
    )
