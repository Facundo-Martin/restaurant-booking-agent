"""Root conftest — stubs sst.Resource before any app code is imported.

app/config.py does `from sst import Resource` at module level, which reads
Lambda environment variables injected by SST at deploy time. In tests those
variables don't exist, so we replace the entire `sst` module with a MagicMock
before any `from app.*` import can trigger the real import chain.
"""

import sys
from unittest.mock import MagicMock

_mock_sst = MagicMock()
_mock_sst.Resource.Bookings.name = "test-bookings-table"
_mock_sst.Resource.RestaurantKB.id = "test-kb-id"
sys.modules["sst"] = _mock_sst
