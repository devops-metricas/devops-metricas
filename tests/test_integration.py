"""Pruebas del escenario contra PostgreSQL real (P1-1, P1-3, P1-4 y reglas de reintento)."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from notifier.channels import PermanentError, TransientError, email
from notifier.config import settings
from notifier.db import get_pool
from notifier.worker import main as worker
from tests.conftest import auth

pytestmark = pytest.mark.integration


def payload(**kw):
    return {
        "recipient": "ana@example.test",
        "channel": "email",
        "subject": "hola",
        "body": "cuerpo",
        **kw,
    }


def post(client, key, **kw):
    return client.post("/v1/notifications", json=payload(**kw), headers=auth(key))


def drain():
    while worker.process_one():
        pass


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch):
    monkeypatch.setattr(settings, "retry_backoff_seconds", 0.0)
    monkeypatch.setattr(email, "send", lambda row: None)


def test_unauthorized_client_is_rejected(client, db):
    assert post(client, "ntf_falsa").status_code == 401


def test_accept_then_deliver_both_channels(client, db):
    ids = [
        post(client, db["app_a"], channel=ch, recipient=rcp).json()["id"]
        for ch, rcp in (("email", "ana@example.test"), ("internal", "usuario-1"))
    ]
    drain()
    for nid in ids:
        d = client.get(f"/v1/notifications/{nid}", headers=auth(db["app_a"])).json()
        assert d["status"] == "delivered"
        assert [h["to_status"] for h in d["history"]][:2] == ["accepted", "pending"]
    inbox = client.get("/v1/inbox/usuario-1", headers=auth(db["app_a"])).json()
    assert len(inbox) == 1


def test_batch_of_100_all_have_id_and_status(client, db):
    ids = [
        post(
            client,
            db["app_a"],
            channel=("email" if i % 2 else "internal"),
            recipient=("a@b.test" if i % 2 else f"u{i}"),
            body=f"m{i}",
        ).json()["id"]
        for i in range(100)
    ]
    assert len(set(ids)) == 100
    for nid in ids:
        assert client.get(f"/v1/notifications/{nid}", headers=auth(db["app_a"])).json()["status"]


def test_idempotency_sequential_and_conflict(client, db):
    first = post(client, db["app_a"], idempotency_key="k1")
    assert first.status_code == 202
    for _ in range(4):
        again = post(client, db["app_a"], idempotency_key="k1")
        assert again.status_code == 200
        assert again.json()["id"] == first.json()["id"]
        assert again.json()["idempotent_replay"] is True
    assert post(client, db["app_a"], idempotency_key="k1", body="distinto").status_code == 409
    # Otra aplicación puede usar la misma clave: el alcance es (cliente, canal, clave).
    assert post(client, db["app_b"], idempotency_key="k1").json()["id"] != first.json()["id"]
    with get_pool().connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM notifications").fetchone()["n"] == 2


def test_idempotency_concurrent(client, db):
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(
            pool.map(lambda _: post(client, db["app_a"], idempotency_key="par"), range(5))
        )
    assert {r.json()["id"] for r in results} == {results[0].json()["id"]}
    assert sorted(r.status_code for r in results).count(202) == 1
    with get_pool().connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM notifications").fetchone()["n"] == 1


def test_transient_failure_retries_then_fails_and_can_be_reprocessed(client, db, monkeypatch):
    def boom(_row):
        raise TransientError("503")

    monkeypatch.setattr(email, "send", boom)
    nid = post(client, db["app_a"]).json()["id"]
    drain()
    d = client.get(f"/v1/notifications/{nid}", headers=auth(db["app_a"])).json()
    assert d["status"] == "failed"
    assert [a["outcome"] for a in d["delivery_attempts"]] == ["transient_error"] * 3

    # Solo un admin reprocesa.
    url = f"/v1/notifications/{nid}/reprocess"
    assert client.post(url, headers=auth(db["app_a"])).status_code == 403
    monkeypatch.setattr(email, "send", lambda row: None)
    assert client.post(url, headers=auth(db["admin"])).status_code == 202
    drain()
    d = client.get(f"/v1/notifications/{nid}", headers=auth(db["admin"])).json()
    assert d["status"] == "delivered"
    assert [a["attempt_no"] for a in d["delivery_attempts"]] == [1, 2, 3, 4]


def test_permanent_failure_is_not_retried(client, db, monkeypatch):
    def reject(_row):
        raise PermanentError("550")

    monkeypatch.setattr(email, "send", reject)
    nid = post(client, db["app_a"], recipient="x@invalid.test").json()["id"]
    drain()
    d = client.get(f"/v1/notifications/{nid}", headers=auth(db["app_a"])).json()
    assert d["status"] == "failed"
    assert len(d["delivery_attempts"]) == 1


def test_orphaned_processing_job_is_recovered(client, db):
    """P1-4: un worker que muere a mitad deja el trabajo 'processing'; otro lo retoma."""
    nid = post(client, db["app_a"]).json()["id"]
    claimed = worker.claim()
    assert claimed["id_text"] == nid
    assert worker.claim() is None  # sigue bloqueado
    with get_pool().connection() as conn:
        conn.execute("UPDATE notifications SET locked_until = now() - interval '1 second'")
    drain()
    d = client.get(f"/v1/notifications/{nid}", headers=auth(db["app_a"])).json()
    assert d["status"] == "delivered"
    assert any("recuperado" in (h["detail"] or "") for h in d["history"])


def test_clients_cannot_read_each_others_notifications(client, db):
    nid = post(client, db["app_a"]).json()["id"]
    assert client.get(f"/v1/notifications/{nid}", headers=auth(db["app_b"])).status_code == 404
    assert client.get(f"/v1/notifications/{nid}", headers=auth(db["admin"])).status_code == 200


def test_stats_by_channel_and_status(client, db):
    post(client, db["app_a"])
    post(client, db["app_a"], channel="internal", recipient="u1")
    drain()
    assert client.get("/v1/stats", headers=auth(db["app_a"])).status_code == 403
    stats = client.get("/v1/stats", headers=auth(db["admin"])).json()
    assert stats["email"]["by_status"]["delivered"] == {"count": 1, "rate": 1.0}
