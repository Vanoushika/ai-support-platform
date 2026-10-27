"""Opt-in telemetry. No request bodies, query strings or model text recorded."""
import os
from functools import wraps
from time import perf_counter

_ENABLED = os.getenv("OTEL_ENABLED", "false").lower() == "true"
_configured = False
_http_count = _http_time = _operation_count = _operation_time = None


def configure_telemetry(default_service):
    global _configured, _http_count, _http_time, _operation_count, _operation_time
    if not _ENABLED or _configured:
        return
    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.metrics.view import View, ExplicitBucketHistogramAggregation
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318").rstrip("/")
    resource = Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME", default_service)})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(
        OTLPSpanExporter(endpoint=endpoint + "/v1/traces", timeout=5),
        schedule_delay_millis=1000,
    ))
    trace.set_tracer_provider(provider)
    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint + "/v1/metrics", timeout=5),
        export_interval_millis=5000,
    )
    metrics.set_meter_provider(MeterProvider(
        resource=resource,
        metric_readers=[reader],
        views=[View(
            instrument_name="*_duration_seconds",
            aggregation=ExplicitBucketHistogramAggregation(
                boundaries=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120, 240)
            ),
        )],
    ))
    meter = metrics.get_meter("support-platform")
    _http_count = meter.create_counter("support_http_requests_total")
    _http_time = meter.create_histogram("support_http_duration_seconds", unit="s")
    _operation_count = meter.create_counter("support_operations_total")
    _operation_time = meter.create_histogram("support_operation_duration_seconds", unit="s")
    _configured = True


def temporal_interceptors():
    if not _ENABLED:
        return []
    from temporalio.contrib.opentelemetry import TracingInterceptor
    return [TracingInterceptor()]


def observed(operation):
    """Observe async work, without logging inputs, outputs or exception text."""
    def decorate(function):
        @wraps(function)
        async def wrapped(*args, **kwargs):
            if not _configured:
                return await function(*args, **kwargs)
            from opentelemetry import trace
            from opentelemetry.trace import Status, StatusCode
            started = perf_counter()
            outcome = "ok"
            with trace.get_tracer("support-platform").start_as_current_span(
                operation, record_exception=False, set_status_on_exception=False
            ) as span:
                try:
                    return await function(*args, **kwargs)
                except BaseException as exc:
                    outcome = "error"
                    span.set_attribute("error.type", type(exc).__name__)
                    span.set_status(Status(StatusCode.ERROR))
                    raise
                finally:
                    attrs = {"operation": operation, "outcome": outcome}
                    _operation_count.add(1, attrs)
                    _operation_time.record(perf_counter() - started, attrs)
        return wrapped
    return decorate


class RequestTelemetryMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if not _configured or scope["type"] != "http" or scope.get("path") == "/health":
            return await self.app(scope, receive, send)
        from opentelemetry import trace
        from opentelemetry.propagate import extract
        from opentelemetry.trace import SpanKind, Status, StatusCode

        method = scope.get("method", "OTHER")
        if method not in {"GET", "POST", "PATCH", "PUT", "DELETE", "HEAD", "OPTIONS"}:
            method = "OTHER"
        # Only propagation headers are read; never export auth/cookie headers.
        carrier = {
            k.decode("latin1"): v.decode("latin1")
            for k, v in scope.get("headers", [])
            if k in (b"traceparent", b"tracestate")
        }
        started = perf_counter()
        status = 500
        with trace.get_tracer("support-platform").start_as_current_span(
            "HTTP " + method, context=extract(carrier), kind=SpanKind.SERVER,
            record_exception=False, set_status_on_exception=False,
        ) as span:
            async def traced_send(message):
                nonlocal status
                if message["type"] == "http.response.start":
                    status = message["status"]
                    headers = list(message.get("headers", []))
                    trace_id = span.get_span_context().trace_id
                    headers.append((b"x-trace-id", format(trace_id, "032x").encode()))
                    message = dict(message, headers=headers)
                await send(message)

            try:
                await self.app(scope, receive, traced_send)
            except BaseException as exc:
                status = 500
                span.set_attribute("error.type", type(exc).__name__)
                span.set_status(Status(StatusCode.ERROR))
                raise
            finally:
                # Matched template avoids ticket IDs and arbitrary URL cardinality.
                route = getattr(scope.get("route"), "path", "unmatched")
                span.update_name(method + " " + route)
                span.set_attribute("http.request.method", method)
                span.set_attribute("http.route", route)
                span.set_attribute("http.response.status_code", status)
                if status >= 500:
                    span.set_status(Status(StatusCode.ERROR))
                labels = {"method": method, "route": route, "status": str(status)}
                _http_count.add(1, labels)
                _http_time.record(perf_counter() - started, labels)
