"""Canal de correo de prueba (SMTP hacia Mailpit)."""

import random
import smtplib
from email.message import EmailMessage

from notifier.channels import PermanentError, TransientError
from notifier.config import settings
from notifier.observability import get_tracer

# Los destinatarios de este dominio simulan un rechazo permanente (SMTP 550).
INVALID_DOMAIN = "@invalid.test"


def send(row: dict) -> None:
    with get_tracer().start_as_current_span("email.send") as span:
        span.set_attribute("notification.id", str(row["id"]))
        _maybe_inject_fault()
        if row["recipient"].lower().endswith(INVALID_DOMAIN):
            raise PermanentError("550 destinatario rechazado por el proveedor")

        msg = EmailMessage()
        msg["From"] = settings.mail_from
        msg["To"] = row["recipient"]
        msg["Subject"] = row["subject"] or "(sin asunto)"
        msg["X-Notification-Id"] = str(row["id"])
        msg.set_content(row["body"])
        try:
            with smtplib.SMTP(
                settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds
            ) as smtp:
                smtp.send_message(msg)
        except smtplib.SMTPRecipientsRefused as exc:
            raise PermanentError(f"destinatario rechazado: {exc}") from exc
        except smtplib.SMTPResponseException as exc:
            kind = PermanentError if 500 <= exc.smtp_code < 600 else TransientError
            raise kind(f"SMTP {exc.smtp_code}: {exc.smtp_error!r}") from exc
        except OSError as exc:  # incluye timeouts, conexión rechazada y SMTPException
            raise TransientError(f"fallo de conexión SMTP: {exc}") from exc


def _maybe_inject_fault() -> None:
    if settings.email_fault_rate > 0 and random.random() < settings.email_fault_rate:
        if settings.email_fault_kind == "timeout":
            raise TransientError("timeout SMTP (inyectado)")
        raise TransientError("SMTP 503 servicio no disponible (inyectado)")
