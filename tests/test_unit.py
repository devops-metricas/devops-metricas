"""Pruebas sin base de datos."""

import smtplib

import pytest
from pydantic import ValidationError

from notifier.channels import PermanentError, TransientError, email
from notifier.config import settings
from notifier.models import NotificationRequest
from notifier.worker.main import backoff_seconds


def make(**kw):
    base = {"recipient": "ana@example.test", "channel": "email", "body": "hola"}
    return NotificationRequest(**{**base, **kw})


def test_content_hash_depends_on_content_not_key():
    assert make(idempotency_key="a").content_hash() == make(idempotency_key="b").content_hash()
    assert make(body="otro").content_hash() != make().content_hash()


def test_email_recipient_needs_at_sign():
    with pytest.raises(ValidationError):
        make(recipient="no-es-correo")
    assert make(channel="internal", recipient="usuario-42").channel == "internal"


@pytest.mark.parametrize("bad", [{"channel": "sms"}, {"body": ""}, {"recipient": ""}])
def test_invalid_requests_rejected(bad):
    with pytest.raises(ValidationError):
        make(**bad)


def test_backoff_is_exponential(monkeypatch):
    monkeypatch.setattr(settings, "retry_backoff_seconds", 2.0)
    assert [backoff_seconds(n) for n in (1, 2, 3)] == [2.0, 4.0, 8.0]


def row(recipient="ana@example.test"):
    return {"id": "x", "recipient": recipient, "subject": "s", "body": "b"}


def test_invalid_domain_is_permanent():
    with pytest.raises(PermanentError):
        email.send(row("alguien@invalid.test"))


def test_injected_fault_is_transient(monkeypatch):
    monkeypatch.setattr(settings, "email_fault_rate", 1.0)
    with pytest.raises(TransientError, match="503"):
        email.send(row())


class _FakeSMTP:
    def __init__(self, exc):
        self.exc = exc

    def __call__(self, *a, **k):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def send_message(self, _msg):
        raise self.exc


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (smtplib.SMTPResponseException(451, b"try later"), TransientError),
        (smtplib.SMTPResponseException(550, b"no such user"), PermanentError),
        (smtplib.SMTPServerDisconnected("bye"), TransientError),
        (TimeoutError("timed out"), TransientError),
    ],
)
def test_smtp_error_classification(monkeypatch, exc, expected):
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP(exc))
    with pytest.raises(expected):
        email.send(row())


def test_api_rejects_missing_key_without_touching_db():
    from fastapi.testclient import TestClient

    from notifier.api.app import app

    with TestClient(app) as c:
        r = c.post(
            "/v1/notifications", json={"recipient": "a@b.test", "channel": "email", "body": "x"}
        )
        assert r.status_code == 401
        assert c.get("/healthz").json() == {"status": "ok"}
