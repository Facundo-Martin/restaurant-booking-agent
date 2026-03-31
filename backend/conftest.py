"""Root conftest — stubs sst.Resource before any app code is imported.

app/config.py does `from sst import Resource` at module level, which reads
Lambda environment variables injected by SST at deploy time. In tests those
variables don't exist, so we replace the entire `sst` module with a MagicMock
before any `from app.*` import can trigger the real import chain.

Credentials (AWS_*, BRAINTRUST_API_KEY) are loaded from backend/.env so
neither manual env-var exports nor CI-only secrets are required locally.
"""

import sys
from unittest.mock import MagicMock

from dotenv import load_dotenv

# Load .env before anything else so AWS credentials are available to boto3
# and BRAINTRUST_API_KEY is available to the Braintrust SDK for agent evals.
load_dotenv()

_mock_sst = MagicMock()
_mock_sst.Resource.Bookings.name = "test-bookings-table"
_mock_sst.Resource.RestaurantKB.id = "test-kb-id"
_mock_sst.Resource.AgentSessions.name = "test-sessions-bucket"
# Set to None so GUARDRAIL_ID resolves to None — prevents BedrockModel from
# being constructed with a MagicMock guardrail ID that would fail Bedrock calls.
_mock_sst.Resource.RestaurantGuardrail = None
sys.modules["sst"] = _mock_sst

# Patch out instrumentation before any test imports app.main.
# instrumentation.setup() is called at module level in app/main.py and requires
# a real Braintrust API key + OTel connections — neither of which we need in tests.
from unittest.mock import patch as _patch  # noqa: E402

_patch("app.instrumentation.setup", return_value=None).start()
_patch("app.instrumentation.flush", return_value=None).start()
