"""Shared Metrics instance for the restaurant-booking service.

Uses CloudWatch Embedded Metric Format (EMF) — metrics are emitted via
CloudWatch Logs so no PutMetricData API calls or extra IAM permissions
are needed beyond the default Lambda logging role.

Namespace can be overridden via POWERTOOLS_METRICS_NAMESPACE env var.
"""

from aws_lambda_powertools import Metrics
from aws_lambda_powertools.metrics import MetricUnit

metrics = Metrics(namespace="RestaurantBookingAgent")

__all__ = ["metrics", "MetricUnit"]
