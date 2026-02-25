from mangum import Mangum

from app.main import app

# Mangum adapts the Lambda event/context to an ASGI request that FastAPI understands,
# and translates the FastAPI response back to a Lambda response.
# SST resolves this file via the handler path: "backend/app/handler_chat.handler"
handler = Mangum(app)
