"""Pruebas reproducibles contra una API en ejecución (local, dev o prod).

    export API_URL=http://localhost:8000 API_KEY=ntf_... ADMIN_KEY=ntf_...
    python scripts/smoke.py batch          # P1-1: 100 solicitudes entre ambos canales
    python scripts/smoke.py idempotency    # P1-3: 5 repeticiones, secuenciales y concurrentes
    python scripts/smoke.py email-failure  # P1-2: correos que fallan de forma permanente
    python scripts/smoke.py stats

Termina con código distinto de cero si una comprobación falla (apto para CI).
Usa solo datos ficticios.
"""

import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx

API_URL = os.environ.get("API_URL", "http://localhost:8000")
API_KEY = os.environ.get("API_KEY", "")
ADMIN_KEY = os.environ.get("ADMIN_KEY", API_KEY)
TERMINAL = {"delivered", "failed"}


def call(method: str, path: str, key: str = API_KEY, **kw) -> httpx.Response:
    return httpx.request(method, API_URL + path, headers={"X-API-Key": key}, timeout=15, **kw)


def submit(**body) -> httpx.Response:
    return call("POST", "/v1/notifications", json=body)


def check(condition: bool, message: str) -> None:
    print(("OK    " if condition else "FALLA ") + message)
    if not condition:
        sys.exit(1)


def wait_terminal(ids: list[str], timeout: float = 120) -> dict[str, str]:
    deadline = time.monotonic() + timeout
    status: dict[str, str] = {}
    while time.monotonic() < deadline:
        for nid in ids:
            if status.get(nid) not in TERMINAL:
                status[nid] = call("GET", f"/v1/notifications/{nid}").json()["status"]
        if all(s in TERMINAL for s in status.values()):
            break
        time.sleep(1)
    return status


def batch() -> None:
    run = uuid.uuid4().hex[:8]
    bodies = [
        {"channel": "email", "recipient": f"usuario{i}@example.test", "subject": f"Lote {run}",
         "body": f"mensaje {i}"} if i % 2 else
        {"channel": "internal", "recipient": f"usuario{i}", "subject": f"Lote {run}",
         "body": f"mensaje {i}"}
        for i in range(100)
    ]
    with ThreadPoolExecutor(max_workers=10) as pool:
        responses = list(pool.map(lambda b: submit(**b), bodies))
    check(all(r.status_code == 202 for r in responses), "100 solicitudes aceptadas (202)")
    ids = [r.json()["id"] for r in responses]
    check(len(set(ids)) == 100, "100 identificadores distintos")
    status = wait_terminal(ids)
    check(all(s in TERMINAL for s in status.values()), "todas llegan a un estado final consultable")
    print("estados:", {s: list(status.values()).count(s) for s in set(status.values())})


def idempotency() -> None:
    body = {"channel": "internal", "recipient": "usuario-idem", "body": "una sola vez"}
    seq_key = f"seq-{uuid.uuid4().hex[:8]}"
    seq = [submit(**body, idempotency_key=seq_key) for _ in range(5)]
    check(len({r.json()["id"] for r in seq}) == 1, "secuencial: 5 respuestas, una notificación")
    check([r.status_code for r in seq] == [202, 200, 200, 200, 200], "secuencial: 202 y luego 200")

    par_key = f"par-{uuid.uuid4().hex[:8]}"
    with ThreadPoolExecutor(max_workers=5) as pool:
        par = list(pool.map(lambda _: submit(**body, idempotency_key=par_key), range(5)))
    check(len({r.json()["id"] for r in par}) == 1, "concurrente: 5 respuestas, una notificación")
    check(sum(r.status_code == 202 for r in par) == 1, "concurrente: exactamente un 202")

    clash = submit(**{**body, "body": "otro contenido"}, idempotency_key=seq_key)
    check(clash.status_code == 409, "misma clave con contenido distinto se rechaza (409)")


def email_failure() -> None:
    ids = [
        submit(channel="email", recipient=f"nadie{i}@invalid.test", body="x").json()["id"]
        for i in range(3)
    ]
    status = wait_terminal(ids)
    check(all(s == "failed" for s in status.values()), "destinatarios inválidos terminan failed")
    for nid in ids:
        d = call("GET", f"/v1/notifications/{nid}").json()
        check(len(d["delivery_attempts"]) == 1, f"{nid[:8]}: error permanente sin reintentos")
    internal = submit(channel="internal", recipient="usuario-ok", body="sigue funcionando")
    check(wait_terminal([internal.json()["id"]]).popitem()[1] == "delivered",
          "el canal interno sigue entregando")


def stats() -> None:
    print(call("GET", "/v1/stats", key=ADMIN_KEY).text)


COMMANDS = {"batch": batch, "idempotency": idempotency, "email-failure": email_failure,
            "stats": stats}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS or not API_KEY:
        sys.exit(__doc__)
    COMMANDS[sys.argv[1]]()
