"""FastAPI application factory."""

from fastapi import FastAPI

from app.api.routes import bookings, chat

app = FastAPI(
    title="Restaurant Booking Agent",
    description="FastAPI + Strands Agents backend for the restaurant booking assistant",
    version="0.1.0",
)

app.include_router(chat.router)
app.include_router(bookings.router)


@app.get("/health")
def health() -> dict:
    """Return a simple liveness check response."""
    return {"status": "ok"}
