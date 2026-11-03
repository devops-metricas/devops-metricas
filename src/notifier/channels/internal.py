"""Canal de notificación interna: se entrega al quedar disponible en la bandeja del destinatario."""

from psycopg import Connection


def store(conn: Connection, row: dict) -> None:
    # UNIQUE (notification_id) + DO NOTHING: reprocesar no duplica el mensaje en la bandeja.
    conn.execute(
        "INSERT INTO internal_messages (notification_id, recipient, subject, body) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT (notification_id) DO NOTHING",
        (row["id"], row["recipient"], row["subject"], row["body"]),
    )
