"""Structured logs plus OpenTelemetry export.

This is the receipt-service equivalent of the TechOps ``tracer`` module that
cs-agent logging follows. cs-agent itself only formats JSON logs and stores
``OTEL_*`` settings; it does not start a tracer. Export here is OTLP HTTP
because the collector is on port 4318. cs-agent's requirements pin gRPC, which
is port 4317.

Tempo receives traces, Loki receives logs, and the same collector receives metrics.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.config import Settings

_LOGGING_INITIALIZED = False
_configured = False
_tracer_provider: TracerProvider | None = None
_meter_provider: MeterProvider | None = None
_logger_provider: LoggerProvider | None = None

_EXTRA_FIELDS = (
    "evidence_id",
    "jira_ticket_id",
    "execution_step",
    "duration_ms",
    "status",
    "stage",
)


class JsonLogFormatter(logging.Formatter):
    """One JSON object per line for Loki, including trace ids when a span is active."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "service": os.getenv("OTEL_SERVICE_NAME", "mimojo-receipt-intelligence"),
            "environment": os.getenv("ENVIRONMENT", "dev"),
        }
        for key in _EXTRA_FIELDS:
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value

        trace_id = getattr(record, "otelTraceID", None)
        span_id = getattr(record, "otelSpanID", None)
        sampled = getattr(record, "otelTraceSampled", None)
        if trace_id:
            payload["trace_id"] = trace_id
        if span_id:
            payload["span_id"] = span_id
        if sampled is not None:
            payload["trace_sampled"] = sampled
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_extra(
    *,
    evidence_id: str | None = None,
    jira_ticket_id: str | None = None,
    execution_step: str | None = None,
    duration_ms: float | None = None,
    status: str | None = None,
    stage: str | None = None,
) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    if evidence_id is not None:
        extra["evidence_id"] = evidence_id
    if jira_ticket_id is not None:
        extra["jira_ticket_id"] = str(jira_ticket_id)
    if execution_step is not None:
        extra["execution_step"] = execution_step
    if duration_ms is not None:
        extra["duration_ms"] = duration_ms
    if status is not None:
        extra["status"] = status
    if stage is not None:
        extra["stage"] = stage
    return extra


def otlp_signal_endpoint(endpoint: str, signal: str) -> str:
    base = endpoint.strip().rstrip("/")
    suffix = f"/v1/{signal}"
    if base.endswith(suffix):
        return base
    return f"{base}{suffix}"


def setup_logging(settings: Settings) -> None:
    """Configure process-wide JSON logs once. Runs even when export is off."""
    global _LOGGING_INITIALIZED
    os.environ.setdefault("OTEL_SERVICE_NAME", settings.otel_service_name)
    os.environ.setdefault("ENVIRONMENT", settings.environment)
    if _LOGGING_INITIALIZED:
        return

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    stream = logging.StreamHandler()
    stream.setFormatter(JsonLogFormatter())
    root.addHandler(stream)
    _LOGGING_INITIALIZED = True


def setup_tracing(settings: Settings) -> None:
    """Start OTLP export of traces, metrics, and logs when a collector is configured."""
    global _configured, _tracer_provider, _meter_provider, _logger_provider
    if _configured or not _export_enabled(settings):
        return

    service_name = settings.otel_service_name.strip() or "mimojo-receipt-intelligence"
    environment = settings.environment.strip() or "dev"
    endpoint = settings.otel_exporter_otlp_endpoint.strip()
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "mimojo",
            "deployment.environment": environment,
            "deployment.environment.name": environment,
        }
    )

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_signal_endpoint(endpoint, "traces")))
    )
    trace.set_tracer_provider(tracer_provider)

    export_interval = int(os.getenv("OTEL_METRIC_EXPORT_INTERVAL_MS", "30000"))
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=otlp_signal_endpoint(endpoint, "metrics")),
                export_interval_millis=export_interval,
            )
        ],
    )
    metrics.set_meter_provider(meter_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=otlp_signal_endpoint(endpoint, "logs")))
    )
    set_logger_provider(logger_provider)

    root = logging.getLogger()
    if not any(isinstance(handler, LoggingHandler) for handler in root.handlers):
        root.addHandler(LoggingHandler(level=logging.INFO, logger_provider=logger_provider))

    LoggingInstrumentor().instrument(set_logging_format=False)
    RequestsInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()
    log = get_logger(__name__)
    try:
        SystemMetricsInstrumentor().instrument()
    except Exception:
        log.warning("system metrics instrumentation was skipped", exc_info=True)

    _tracer_provider = tracer_provider
    _meter_provider = meter_provider
    _logger_provider = logger_provider
    _configured = True
    log.info(
        "[App] exporting traces, metrics, and logs to %s",
        endpoint,
        extra=log_extra(execution_step="startup", status="ready"),
    )


def instrument_app(app) -> None:
    if not _configured:
        return
    FastAPIInstrumentor.instrument_app(app, excluded_urls="health")


def instrument_engine(engine) -> None:
    if not _configured:
        return
    SQLAlchemyInstrumentor().instrument(engine=engine)


def shutdown_tracing() -> None:
    global _tracer_provider, _meter_provider, _logger_provider
    if _tracer_provider is not None:
        _tracer_provider.shutdown()
        _tracer_provider = None
    if _meter_provider is not None:
        _meter_provider.shutdown()
        _meter_provider = None
    if _logger_provider is not None:
        _logger_provider.shutdown()
        _logger_provider = None


def _export_enabled(settings: Settings) -> bool:
    disabled = os.getenv("OTEL_SDK_DISABLED", "").strip().lower()
    if disabled in {"1", "true", "yes", "on"}:
        return False
    # Keep pytest from pushing spans at the shared collector.
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    return bool(settings.otel_exporter_otlp_endpoint.strip())
