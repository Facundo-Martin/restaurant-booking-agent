"""Fixtures for integration tests.

Each fixture skips the test when the required environment variable is absent,
so integration tests are safe to collect in any environment — they simply
report 'skipped' rather than failing.

Required env vars:
  INTEGRATION_TABLE_NAME  — DynamoDB table name in the test SST stage
  INTEGRATION_API_URL     — API Gateway URL (health + bookings routes)
  INTEGRATION_CHAT_URL    — Lambda Function URL (chat streaming)
"""

import os

import boto3
import pytest

import app.repositories.bookings as _repo_module


@pytest.fixture(scope="module")
def real_table():
    """Swap the repository's module-level cached table to a real DynamoDB table.

    Mirrors the unit-test pattern (moto swap) but uses a real boto3 resource
    backed by the DynamoDB table in the test SST stage. Restores the original
    on teardown so later test modules are unaffected.
    """
    table_name = os.environ.get("INTEGRATION_TABLE_NAME")
    if not table_name:
        pytest.skip("INTEGRATION_TABLE_NAME not set")

    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    real = dynamodb.Table(table_name)

    original = _repo_module._TABLE_HANDLE  # pylint: disable=protected-access
    _repo_module._TABLE_HANDLE = real  # pylint: disable=protected-access
    yield real
    _repo_module._TABLE_HANDLE = original  # pylint: disable=protected-access


@pytest.fixture(scope="module")
def api_url():
    """Base URL of the API Gateway (health + bookings routes)."""
    url = os.environ.get("INTEGRATION_API_URL")
    if not url:
        pytest.skip("INTEGRATION_API_URL not set")
    return url.rstrip("/")


@pytest.fixture(scope="module")
def chat_url():
    """Base URL of the Chat Lambda Function URL."""
    url = os.environ.get("INTEGRATION_CHAT_URL")
    if not url:
        pytest.skip("INTEGRATION_CHAT_URL not set")
    return url.rstrip("/")
