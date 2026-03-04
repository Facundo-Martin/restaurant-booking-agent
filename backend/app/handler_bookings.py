from aws_lambda_powertools.utilities.typing import LambdaContext
from mangum import Mangum
from mangum.types import LambdaEvent

from app.logging import logger
from app.main import app
from app.metrics import metrics
from app.tracer import tracer

# Separate entry point from handler_chat.py so SST can size each Lambda independently:
# - handler_chat:    120s timeout, 1024MB memory (multi-turn Bedrock agent)
# - handler_bookings: 10s timeout,  256MB memory (simple DynamoDB reads)
# SST resolves this file via the handler path: "backend/app/handler_bookings.handler"
_mangum_handler = Mangum(app, lifespan="off")


# Decorator order follows Powertools convention: Logger outermost → Tracer → Metrics innermost.
# inject_lambda_context: enriches all log lines with Lambda context (request ID, cold start).
# capture_lambda_handler: creates an X-Ray subsegment for the full invocation.
# log_metrics: flushes the EMF blob at handler exit; cold start emitted as a separate metric.
@logger.inject_lambda_context(log_event=False, clear_state=True)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def handler(event: LambdaEvent, context: LambdaContext) -> dict:
    return _mangum_handler(event, context)
