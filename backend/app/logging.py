"""Shared Logger instance for the restaurant-booking service.

Import from here rather than constructing Logger directly in each module.
Powertools re-uses the same instance when the service name matches, but
having a single canonical source prevents accidental divergence in service
names or sampling rates.
"""

from aws_lambda_powertools import Logger

logger = Logger(service="restaurant-booking")
