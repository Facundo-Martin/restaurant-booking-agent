"""Application-level exceptions."""

from fastapi import HTTPException


class AppException(HTTPException):
    """Base for all application-level HTTP errors.

    Carries a machine-readable ``code`` alongside the HTTP status so clients
    can branch on specific conditions without parsing the message string.

    Usage::

        raise AppException(status_code=404, code="BOOKING_NOT_FOUND", message="Booking abc not found.")
    """

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message
