from sst import Resource

# SST injects these at deploy time — no SSM calls, no hardcoded ARNs.
# At runtime (Lambda + sst dev), Resource reads from environment variables
# that SST populated during deployment.
TABLE_NAME: str = Resource.Bookings.name  # type: ignore[attr-defined]
KB_ID: str = Resource.RestaurantKB.id  # type: ignore[attr-defined]
