import json
import logging

from opentelemetry import trace

from app.config import Settings
from app.tracer import JsonLogFormatter, log_extra, otlp_signal_endpoint, setup_tracing


def test_otlp_signal_endpoint_appends_the_http_path():
    assert otlp_signal_endpoint("http://80.238.219.232:4318", "traces") == "http://80.238.219.232:4318/v1/traces"
    assert otlp_signal_endpoint("http://80.238.219.232:4318/", "logs") == "http://80.238.219.232:4318/v1/logs"
    assert (
        otlp_signal_endpoint("http://80.238.219.232:4318/v1/metrics", "metrics")
        == "http://80.238.219.232:4318/v1/metrics"
    )


def test_setup_tracing_does_not_export_during_tests():
    setup_tracing(
        Settings(
            database_url="sqlite://",
            otel_exporter_otlp_endpoint="http://127.0.0.1:4318",
            otel_service_name="mimojo-receipt-intelligence",
            environment="dev",
        )
    )
    assert type(trace.get_tracer_provider()).__name__ == "ProxyTracerProvider"


def test_json_log_line_carries_receipt_fields_and_trace_id():
    record = logging.LogRecord(
        name="app.api.receipts",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="[API] receipt accepted",
        args=(),
        exc_info=None,
    )
    for key, value in log_extra(evidence_id="abc", execution_step="intake", status="accepted").items():
        setattr(record, key, value)
    record.otelTraceID = "trace-1"
    record.otelSpanID = "span-1"
    record.otelTraceSampled = True

    payload = json.loads(JsonLogFormatter().format(record))

    assert payload["message"] == "[API] receipt accepted"
    assert payload["evidence_id"] == "abc"
    assert payload["execution_step"] == "intake"
    assert payload["status"] == "accepted"
    assert payload["trace_id"] == "trace-1"
    assert payload["span_id"] == "span-1"
    assert payload["trace_sampled"] is True
    assert payload["service"] == "mimojo-receipt-intelligence"
