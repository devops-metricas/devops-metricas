"""Acceso a datos compartido por la API y el worker."""

from dataclasses import dataclass

from psycopg import Connection

from notifier.models import NotificationRequest


class IdempotencyConflict(Exception):
    """La clave ya existe para (cliente, canal) con contenido distinto."""


@dataclass
class CreateResult:
    id: str
    status: str
    replay: bool


def record_event(
    conn: Connection, notification_id, from_status: str | None, to_status: str, detail=None
) -> None:
    conn.execute(
        "INSERT INTO notification_events (notification_id, from_status, to_status, detail) "
        "VALUES (%s, %s, %s, %s)",
        (notification_id, from_status, to_status, detail),
    )


def create_notification(
    conn: Connection,
    client_id: str,
    req: NotificationRequest,
    max_attempts: int,
    traceparent: str | None,
) -> CreateResult:
    """Registra la solicitud de forma durable. La unicidad la decide la base (ON CONFLICT),
    por lo que 5 solicitudes simultáneas con la misma clave producen un único trabajo."""
    content_hash = req.content_hash()
    row = conn.execute(
        """
        INSERT INTO notifications
            (client_id, channel, recipient, subject, body, idempotency_key,
             content_hash, status, max_attempts, traceparent)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s)
        ON CONFLICT (client_id, channel, idempotency_key)
            WHERE idempotency_key IS NOT NULL DO NOTHING
        RETURNING id::text AS id, status
        """,
        (
            client_id,
            req.channel,
            req.recipient,
            req.subject,
            req.body,
            req.idempotency_key,
            content_hash,
            max_attempts,
            traceparent,
        ),
    ).fetchone()
    if row is not None:
        record_event(conn, row["id"], None, "accepted")
        record_event(conn, row["id"], "accepted", "pending", "encolada")
        return CreateResult(row["id"], row["status"], replay=False)

    existing = conn.execute(
        "SELECT id::text AS id, status, content_hash FROM notifications "
        "WHERE client_id = %s AND channel = %s AND idempotency_key = %s",
        (client_id, req.channel, req.idempotency_key),
    ).fetchone()
    if existing["content_hash"] != content_hash:
        raise IdempotencyConflict(req.idempotency_key)
    return CreateResult(existing["id"], existing["status"], replay=True)


def get_notification_detail(conn: Connection, notification_id: str, client_id: str | None):
    """client_id=None devuelve cualquier notificación (admin)."""
    where, params = "n.id = %s", [notification_id]
    if client_id is not None:
        where += " AND n.client_id = %s"
        params.append(client_id)
    row = conn.execute(
        f"""
        SELECT n.id::text AS id, c.name AS client, n.channel, n.recipient, n.subject,
               n.status, n.attempts, n.max_attempts, n.last_error, n.idempotency_key,
               n.created_at, n.updated_at, n.delivered_at
        FROM notifications n JOIN clients c ON c.id = n.client_id
        WHERE {where}
        """,
        params,
    ).fetchone()
    if row is None:
        return None
    row["history"] = conn.execute(
        "SELECT from_status, to_status, detail, at FROM notification_events "
        "WHERE notification_id = %s ORDER BY id",
        (notification_id,),
    ).fetchall()
    row["delivery_attempts"] = conn.execute(
        "SELECT attempt_no, started_at, finished_at, outcome, error FROM delivery_attempts "
        "WHERE notification_id = %s ORDER BY attempt_no, id",
        (notification_id,),
    ).fetchall()
    return row


def reprocess_failed(conn: Connection, notification_id: str, extra_attempts: int, who: str):
    """Devuelve una notificación fallida a la cola con presupuesto de intentos renovado.
    El historial de intentos se conserva; attempts no se reinicia para no repetir numeración."""
    row = conn.execute(
        """
        UPDATE notifications
        SET status = 'pending', next_attempt_at = now(), locked_until = NULL,
            max_attempts = attempts + %s, updated_at = now()
        WHERE id = %s AND status = 'failed'
        RETURNING id::text AS id, status
        """,
        (extra_attempts, notification_id),
    ).fetchone()
    if row is not None:
        record_event(conn, notification_id, "failed", "pending", f"reprocesada por {who}")
    return row


def stats_by_channel_status(conn: Connection) -> dict:
    rows = conn.execute(
        "SELECT channel, status, count(*) AS n FROM notifications GROUP BY channel, status"
    ).fetchall()
    out: dict[str, dict] = {}
    for r in rows:
        out.setdefault(r["channel"], {"total": 0, "by_status": {}})
        out[r["channel"]]["by_status"][r["status"]] = {"count": r["n"]}
        out[r["channel"]]["total"] += r["n"]
    for ch in out.values():
        for st in ch["by_status"].values():
            st["rate"] = round(st["count"] / ch["total"], 4)
    return out
