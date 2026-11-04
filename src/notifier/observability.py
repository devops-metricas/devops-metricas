"""Logs estructurados, métricas Prometheus y trazas OpenTelemetry."""

import logging
import os

import structlog
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Gauge, Histogram

from notifier.config import settings

# --- Métricas (documentadas en docs/MET/MET-01-catalogo-de-indicadores.md) ---

NOTIFICATIONS_ACCEPTED = Counter(
    "notifier_notifications_accepted_total",
    "Solicitudes aceptadas (registradas de forma durable).",
    ["client", "channel"],
)
IDEMPOTENT_REPLAYS = Counter(
    "notifier_idempotent_replays_total",
    "Solicitudes repetidas que devolvieron la referencia original.",
    ["client", "channel"],
)
IDEMPOTENCY_CONFLICTS = Counter(
    "notifier_idempotency_conflicts_total",
    "Claves de idempotencia repetidas con contenido distinto (rechazadas).",
    ["client", "channel"],
)
DELIVERY_ATTEMPTS = Counter(
    "notifier_delivery_attempts_total",
    "Intentos de entrega por canal y resultado.",
    ["channel", "outcome"],
)
NOTIFICATIONS_FINISHED = Counter(
    "notifier_notifications_finished_total",
    "Notificaciones que alcanzaron un estado final.",
    ["channel", "status"],
)
ATTEMPT_DURATION = Histogram(
    "notifier_delivery_attempt_duration_seconds",
    "Duración de un intento de entrega.",
    ["channel"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
END_TO_END_SECONDS = Histogram(
    "notifier_end_to_end_seconds",
    "Tiempo desde la aceptación hasta la entrega.",
    ["channel"],
    buckets=(0.5, 1, 2, 5, 10, 30, 60, 120, 300),
)
QUEUE_DEPTH = Gauge("notifier_queue_depth", "Notificaciones en cola por estado.", ["status"])
OLDEST_PENDING_AGE = Gauge(
    "notifier_oldest_pending_age_seconds",
    "Antigüedad del trabajo pendiente ya elegible más viejo (0 si no hay).",
)

# --- Logs estructurados ----------------------------------------------------------------


def _add_trace_ids(_logger, _method, event_dict):
    ctx = trace.get_current_span().get_span_context()
    if ctx.is_valid:
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict


def setup_logging(component: str) -> None:
    level = logging.getLevelNamesMapping().get(settings.log_level.upper(), logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _add_trace_ids,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(component=component, environment=settings.environment)


def get_logger(name: str = "notifier"):
    return structlog.get_logger(name)


# --- Trazas ----------------------------------------------------------------------------


def setup_tracing(component: str) -> None:
    """Exporta por OTLP/HTTP solo si OTEL_EXPORTER_OTLP_ENDPOINT está definido."""
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": f"notifier-{component}",
                "deployment.environment": settings.environment,
            }
        )
    )
    if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

    from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor

    PsycopgInstrumentor().instrument()


def get_tracer():
    return trace.get_tracer("notifier")
