"""Worker: toma trabajos de la cola (tabla notifications), entrega y reintenta.

Cola sobre PostgreSQL con FOR UPDATE SKIP LOCKED. Un trabajo "processing" cuyo `locked_until`
venció (worker caído a medias) vuelve a ser elegible, de modo que ningún estado se pierde.
"""

import signal
import threading
import time
from datetime import UTC, datetime

from opentelemetry import propagate, trace
from prometheus_client import start_http_server

from notifier import repository
from notifier.channels import PermanentError, TransientError, email, internal
from notifier.config import settings
from notifier.db import close_pool, get_pool
from notifier.observability import (
    ATTEMPT_DURATION,
    DELIVERY_ATTEMPTS,
    END_TO_END_SECONDS,
    NOTIFICATIONS_FINISHED,
    OLDEST_PENDING_AGE,
    QUEUE_DEPTH,
    get_logger,
    get_tracer,
    setup_logging,
    setup_tracing,
)

log = get_logger("notifier.worker")

CLAIM_SQL = """
WITH picked AS (
    SELECT id, status AS prev_status
    FROM notifications
    WHERE (status = 'pending' AND next_attempt_at <= now())
       OR (status = 'processing' AND locked_until < now())
    ORDER BY next_attempt_at, created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE notifications n
SET status = 'processing', attempts = n.attempts + 1,
    locked_until = now() + make_interval(secs => %s), updated_at = now()
FROM picked
WHERE n.id = picked.id
RETURNING n.*, n.id::text AS id_text, picked.prev_status
"""


def backoff_seconds(attempt: int) -> float:
    """Espera antes del siguiente intento, tras fallar el intento `attempt` (1 = el inicial)."""
    return settings.retry_backoff_seconds * 2 ** (attempt - 1)


def claim() -> dict | None:
    with get_pool().connection() as conn:
        row = conn.execute(CLAIM_SQL, (settings.lock_seconds,)).fetchone()
        if row is not None:
            detail = f"intento {row['attempts']} de {row['max_attempts']}"
            if row["prev_status"] == "processing":
                detail += " (recuperado: el worker anterior no terminó)"
            repository.record_event(conn, row["id"], row["prev_status"], "processing", detail)
    return row


def process_one() -> bool:
    """Procesa un trabajo si hay uno elegible. Devuelve False si la cola está vacía."""
    row = claim()
    if row is None:
        return False

    parent = propagate.extract({"traceparent": row["traceparent"]} if row["traceparent"] else {})
    with get_tracer().start_as_current_span(
        "notification.process",
        context=parent,
        kind=trace.SpanKind.CONSUMER,
        attributes={
            "notification.id": row["id_text"],
            "notification.channel": row["channel"],
            "notification.attempt": row["attempts"],
        },
    ):
        started = datetime.now(UTC)
        error: str | None = None
        try:
            if row["channel"] == "email":
                email.send(row)
            outcome = "success"
        except PermanentError as exc:
            outcome, error = "permanent_error", str(exc)
        except TransientError as exc:
            outcome, error = "transient_error", str(exc)
        except (
            Exception
        ) as exc:  # error inesperado: se trata como pasajero, no se pierde el trabajo
            outcome, error = "transient_error", f"{type(exc).__name__}: {exc}"
            log.exception("unexpected_delivery_error", notification_id=row["id_text"])
        finished = datetime.now(UTC)
        _finish(row, outcome, error, started, finished)
    return True


def _finish(row: dict, outcome: str, error: str | None, started, finished) -> None:
    channel, nid = row["channel"], row["id"]
    attempt = row["attempts"]
    DELIVERY_ATTEMPTS.labels(channel, outcome).inc()
    ATTEMPT_DURATION.labels(channel).observe((finished - started).total_seconds())

    with get_pool().connection() as conn:
        conn.execute(
            "INSERT INTO delivery_attempts "
            "(notification_id, attempt_no, started_at, finished_at, outcome, error) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (nid, attempt, started, finished, outcome, error),
        )
        if outcome == "success":
            if channel == "internal":
                internal.store(conn, row)  # misma transacción que el cambio de estado
            conn.execute(
                "UPDATE notifications SET status = 'delivered', locked_until = NULL, "
                "last_error = NULL, delivered_at = now(), updated_at = now() WHERE id = %s",
                (nid,),
            )
            repository.record_event(conn, nid, "processing", "delivered", f"intento {attempt}")
            final = "delivered"
        elif outcome == "transient_error" and attempt < row["max_attempts"]:
            wait = backoff_seconds(attempt)
            conn.execute(
                "UPDATE notifications SET status = 'pending', locked_until = NULL, "
                "last_error = %s, next_attempt_at = now() + make_interval(secs => %s), "
                "updated_at = now() WHERE id = %s",
                (error, wait, nid),
            )
            repository.record_event(
                conn, nid, "processing", "pending", f"reintento en {wait:g}s: {error}"
            )
            final = None
        else:
            reason = "error permanente" if outcome == "permanent_error" else "reintentos agotados"
            conn.execute(
                "UPDATE notifications SET status = 'failed', locked_until = NULL, last_error = %s, "
                "updated_at = now() WHERE id = %s",
                (error, nid),
            )
            repository.record_event(conn, nid, "processing", "failed", f"{reason}: {error}")
            final = "failed"

    if final:
        NOTIFICATIONS_FINISHED.labels(channel, final).inc()
    if final == "delivered":
        END_TO_END_SECONDS.labels(channel).observe((finished - row["created_at"]).total_seconds())
    log.info(
        "delivery_attempt",
        notification_id=row["id_text"],
        channel=channel,
        attempt=attempt,
        outcome=outcome,
        final_status=final or "pending",
        error=error,
    )


def refresh_queue_gauges() -> None:
    with get_pool().connection() as conn:
        counts = {
            r["status"]: r["n"]
            for r in conn.execute(
                "SELECT status, count(*) AS n FROM notifications "
                "WHERE status IN ('pending', 'processing') GROUP BY status"
            )
        }
        age = conn.execute(
            "SELECT COALESCE(EXTRACT(EPOCH FROM now() - min(next_attempt_at)), 0) AS age "
            "FROM notifications WHERE status = 'pending' AND next_attempt_at <= now()"
        ).fetchone()["age"]
    for status in ("pending", "processing"):
        QUEUE_DEPTH.labels(status).set(counts.get(status, 0))
    OLDEST_PENDING_AGE.set(float(age))


def main() -> None:
    setup_logging("worker")
    setup_tracing("worker")
    start_http_server(settings.worker_metrics_port)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())  # termina el intento en curso y sale

    log.info("worker_started", metrics_port=settings.worker_metrics_port)
    last_gauges = 0.0
    while not stop.is_set():
        try:
            if time.monotonic() - last_gauges > 5:
                refresh_queue_gauges()
                last_gauges = time.monotonic()
            worked = process_one()
        except Exception:
            log.exception("worker_loop_error")
            worked = False
        if not worked:
            stop.wait(settings.poll_interval_seconds)
    close_pool()
    log.info("worker_stopped")


if __name__ == "__main__":
    main()
