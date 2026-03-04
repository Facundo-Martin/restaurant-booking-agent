"""Lambda entry point for the chat function (LWA mode).

With AWS_LAMBDA_EXEC_WRAPPER=/opt/bootstrap, LWA's bootstrap runs run.sh,
which starts uvicorn serving app.main:app on port 8080. LWA then proxies
each Lambda invocation as HTTP to that uvicorn process and streams the
response back — the Python handler below is never called by Lambda.

This module exists solely so SST can resolve a valid handler path
("backend/app/handler_chat.handler"). The 'handler' attribute is never
invoked; do not add logic here.
"""

from app.main import app

# Satisfies Lambda's module resolution. Never called — see module docstring.
handler = app
