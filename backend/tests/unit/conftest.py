"""Shared fixtures for unit tests."""

import boto3
import pytest
from moto import mock_aws

import app.repositories.bookings as _repo_module  # noqa: E402

_TABLE_NAME = "test-bookings-table"


@pytest.fixture()
def dynamodb_table():
    """Spin up a moto DynamoDB table and patch the repository's module-level _table.

    The repository initialises `_table` at import time, so we swap it out for
    the duration of each test and restore the original on teardown.
    """
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName=_TABLE_NAME,
            KeySchema=[
                {"AttributeName": "booking_id", "KeyType": "HASH"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "booking_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        original = _repo_module._table  # pylint: disable=protected-access
        _repo_module._table = table  # pylint: disable=protected-access
        yield table
        _repo_module._table = original  # pylint: disable=protected-access
