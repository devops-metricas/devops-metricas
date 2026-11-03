CREATE TABLE clients (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name          text NOT NULL UNIQUE,
    api_key_hash  text NOT NULL UNIQUE,
    role          text NOT NULL DEFAULT 'client' CHECK (role IN ('client', 'admin')),
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE notifications (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id        uuid NOT NULL REFERENCES clients (id),
    channel          text NOT NULL CHECK (channel IN ('email', 'internal')),
    recipient        text NOT NULL,
    subject          text,
    body             text NOT NULL,
    idempotency_key  text,
    content_hash     text NOT NULL,
    status           text NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('accepted', 'pending', 'processing', 'delivered', 'failed')),
    attempts         integer NOT NULL DEFAULT 0,
    max_attempts     integer NOT NULL,
    next_attempt_at  timestamptz NOT NULL DEFAULT now(),
    locked_until     timestamptz,
    last_error       text,
    traceparent      text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    delivered_at     timestamptz
);

-- Idempotencia por (aplicación cliente, canal, clave). Sin ventana de expiración:
-- la garantía dura mientras exista el registro, que cumple el mínimo de 24 h.
CREATE UNIQUE INDEX notifications_idempotency_uq
    ON notifications (client_id, channel, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

-- Cola: el worker busca trabajos listos por estado y fecha.
CREATE INDEX notifications_queue_idx
    ON notifications (next_attempt_at)
    WHERE status IN ('pending', 'processing');

CREATE INDEX notifications_status_idx ON notifications (channel, status);

-- Cada transición de estado (ESC1-05).
CREATE TABLE notification_events (
    id               bigserial PRIMARY KEY,
    notification_id  uuid NOT NULL REFERENCES notifications (id),
    from_status      text,
    to_status        text NOT NULL,
    detail           text,
    at               timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX notification_events_nid_idx ON notification_events (notification_id, id);

-- Historial de intentos de entrega (ESC1-06).
CREATE TABLE delivery_attempts (
    id               bigserial PRIMARY KEY,
    notification_id  uuid NOT NULL REFERENCES notifications (id),
    attempt_no       integer NOT NULL,
    started_at       timestamptz NOT NULL,
    finished_at      timestamptz NOT NULL,
    outcome          text NOT NULL CHECK (outcome IN ('success', 'transient_error', 'permanent_error')),
    error            text
);
CREATE INDEX delivery_attempts_nid_idx ON delivery_attempts (notification_id, attempt_no);

-- Canal "notificación interna": quedan disponibles para consulta del destinatario.
CREATE TABLE internal_messages (
    id               bigserial PRIMARY KEY,
    notification_id  uuid NOT NULL UNIQUE REFERENCES notifications (id),
    recipient        text NOT NULL,
    subject          text,
    body             text NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX internal_messages_recipient_idx ON internal_messages (recipient, id DESC);
