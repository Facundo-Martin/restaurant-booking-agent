from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext
from mangum import Mangum
from mangum.types import LambdaEvent

from app.main import app

logger = Logger(service="restaurant-booking")

# Separate entry point from handler_chat.py so SST can size each Lambda independently:
# - handler_chat:    120s timeout, 1024MB memory (multi-turn Bedrock agent)
# - handler_bookings: 10s timeout,  256MB memory (simple DynamoDB reads)
# SST resolves this file via the handler path: "backend/app/handler_bookings.handler"
_mangum_handler = Mangum(app, lifespan="off")


@logger.inject_lambda_context(log_event=False)
def handler(event: LambdaEvent, context: LambdaContext) -> dict:
    return _mangum_handler(event, context)
