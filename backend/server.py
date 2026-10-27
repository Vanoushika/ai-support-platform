from observability import configure_telemetry, RequestTelemetryMiddleware

configure_telemetry("support-api")

from main import app
from workflow_api import router as workflow_router

app.include_router(workflow_router)
app.add_middleware(RequestTelemetryMiddleware)
