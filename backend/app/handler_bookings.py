from mangum import Mangum

from app.main import app

# Separate entry point from handler_chat.py so SST can size each Lambda independently:
# - handler_chat:    120s timeout, 1024MB memory (multi-turn Bedrock agent)
# - handler_bookings: 10s timeout,  256MB memory (simple DynamoDB reads)
# SST resolves this file via the handler path: "backend/app/handler_bookings.handler"
handler = Mangum(app)
