import time
import uuid
from contextlib import asynccontextmanager
from typing import Annotated

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from opentelemetry import propagate
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_fastapi_instrumentator import Instrumentator

from notifier import repository
from notifier.config import settings
from notifier.db import close_pool, get_pool
from notifier.models import AuthenticatedClient, NotificationRequest
from notifier.observability import (
    IDEMPOTENCY_CONFLICTS,
    IDEMPOTENT_REPLAYS,
    NOTIFICATIONS_ACCEPTED,
    get_logger,
    setup_logging,
    setup_tracing,
)
from notifier.security import authenticate, require_admin

setup_logging("api")
setup_tracing("api")
log = get_logger("notifier.api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    close_pool()


app = FastAPI(title="Plataforma de notificaciones", version="0.1.0", lifespan=lifespan)
FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,readyz,metrics")
Instrumentator(excluded_handlers=["/healthz", "/readyz", "/metrics"]).instrument(app).expose(
    app, endpoint="/metrics", include_in_schema=False
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    structlog.contextvars.bind_contextvars(request_id=request_id)
    start = time.perf_counter()
    try:
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        if request.url.path not in ("/healthz", "/readyz", "/metrics"):
            log.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=round((time.perf_counter() - start) * 1000, 1),
            )
        return response
    except Exception:
        log.exception("request_failed", method=request.method, path=request.url.path)
        raise
    finally:
        structlog.contextvars.unbind_contextvars("request_id")


CurrentClient = Annotated[AuthenticatedClient, Depends(authenticate)]
Admin = Annotated[AuthenticatedClient, Depends(require_admin)]


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"status": "ok"}


@app.get("/readyz", include_in_schema=False)
def readyz():
    try:
        with get_pool().connection() as conn:
            conn.execute("SELECT 1")
    except Exception as exc:
        raise HTTPException(503, "base de datos no disponible") from exc
    return {"status": "ready"}


@app.post("/v1/notifications", status_code=202)
def create_notification(req: NotificationRequest, client: CurrentClient, response: Response):
    """202 = recibida y registrada, NO entregada. Una repetición idempotente devuelve 200
    con la referencia original."""
    carrier: dict[str, str] = {}
    propagate.inject(carrier)  # el worker continúa esta traza (API -> cola -> worker)
    try:
        with get_pool().connection() as conn:
            result = repository.create_notification(
                conn, client.id, req, settings.max_attempts, carrier.get("traceparent")
            )
    except repository.IdempotencyConflict as exc:
        IDEMPOTENCY_CONFLICTS.labels(client.name, req.channel).inc()
        log.warning("idempotency_conflict", client=client.name, channel=req.channel)
        raise HTTPException(
            409, "la clave de idempotencia ya se usó con contenido distinto"
        ) from exc

    if result.replay:
        response.status_code = 200
        IDEMPOTENT_REPLAYS.labels(client.name, req.channel).inc()
        log.info("notification_replayed", notification_id=result.id, client=client.name)
    else:
        NOTIFICATIONS_ACCEPTED.labels(client.name, req.channel).inc()
        log.info(
            "notification_accepted",
            notification_id=result.id,
            client=client.name,
            channel=req.channel,
        )
    return {"id": result.id, "status": result.status, "idempotent_replay": result.replay}


@app.get("/v1/notifications/{notification_id}")
def get_notification(notification_id: uuid.UUID, client: CurrentClient):
    scope = None if client.role == "admin" else client.id
    with get_pool().connection() as conn:
        detail = repository.get_notification_detail(conn, str(notification_id), scope)
    if detail is None:
        raise HTTPException(404, "notificación no encontrada")
    return detail


@app.post("/v1/notifications/{notification_id}/reprocess", status_code=202)
def reprocess_notification(notification_id: uuid.UUID, admin: Admin):
    with get_pool().connection() as conn:
        row = repository.reprocess_failed(
            conn, str(notification_id), settings.max_attempts, admin.name
        )
    if row is None:
        raise HTTPException(409, "solo se pueden reprocesar notificaciones en estado 'failed'")
    log.info("notification_reprocessed", notification_id=row["id"], by=admin.name)
    return row


@app.get("/v1/inbox/{recipient}")
def inbox(recipient: str, client: CurrentClient, limit: int = 50):
    """Notificaciones internas del destinatario (un cliente solo ve las que él originó)."""
    limit = max(1, min(limit, 200))
    sql = (
        "SELECT m.notification_id::text AS notification_id, m.subject, m.body, m.created_at "
        "FROM internal_messages m JOIN notifications n ON n.id = m.notification_id "
        "WHERE m.recipient = %s"
    )
    params: list = [recipient]
    if client.role != "admin":
        sql += " AND n.client_id = %s"
        params.append(client.id)
    sql += " ORDER BY m.id DESC LIMIT %s"
    params.append(limit)
    with get_pool().connection() as conn:
        return conn.execute(sql, params).fetchall()


@app.get("/v1/stats")
def stats(_admin: Admin):
    """Recuentos y tasas por canal y estado."""
    with get_pool().connection() as conn:
        return repository.stats_by_channel_status(conn)
