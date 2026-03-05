"""Shared Tracer instance for the restaurant-booking service.

Tracer reads POWERTOOLS_SERVICE_NAME from the environment and auto-disables
itself outside Lambda (local dev, tests) so no mocking is required.
"""

from aws_lambda_powertools import Tracer

tracer = Tracer()
