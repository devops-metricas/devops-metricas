"""Pruebas reproducibles contra una API en ejecución (local, dev o prod).

    export API_URL=http://localhost:8000 API_KEY=ntf_... ADMIN_KEY=ntf_...
    python scripts/smoke.py batch          # P1-1: 100 solicitudes entre ambos canales
    python scripts/smoke.py idempotency    # P1-3: 5 repeticiones, secuenciales y concurrentes
    python scripts/smoke.py email-failure  # errores permanentes: failed sin reintentos
    python scripts/smoke.py email-degraded # P1-2: correo degradado; reintentos, canal interno vivo
    python scripts/smoke.py recovery       # P1-4: reinicia el worker con trabajos pendientes
    python scripts/smoke.py access         # ESC1-02: sin clave, clave inválida, rol insuficiente
    python scripts/smoke.py stats

email-degraded exige el worker con NOTIFIER_EMAIL_FAULT_RATE>0 (p. ej. 1.0; ver README).
recovery exige RESTART_CMD, el comando que reinicia el worker, por ejemplo:
    RESTART_CMD="docker compose restart worker"
    RESTART_CMD="kubectl -n notifier-dev rollout restart deploy/worker"

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
        {
            "channel": "email",
            "recipient": f"usuario{i}@example.test",
            "subject": f"Lote {run}",
            "body": f"mensaje {i}",
        }
        if i % 2
        else {
            "channel": "internal",
            "recipient": f"usuario{i}",
            "subject": f"Lote {run}",
            "body": f"mensaje {i}",
        }
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
    check(
        wait_terminal([internal.json()["id"]]).popitem()[1] == "delivered",
        "el canal interno sigue entregando",
    )


def email_degraded() -> None:
    n = 10
    emails = [
        submit(channel="email", recipient=f"deg{i}@example.test", body="x").json()["id"]
        for i in range(n)
    ]
    internals = [
        submit(channel="internal", recipient=f"deg{i}", body="x").json()["id"] for i in range(n)
    ]
    check(len(set(emails + internals)) == 2 * n, "se aceptan aunque el correo falle")
    status = wait_terminal(emails + internals, timeout=180)
    check(all(status[i] == "delivered" for i in internals), "el canal interno entrega todo")
    check(all(status[i] in TERMINAL for i in emails), "los correos llegan a un estado final")

    attempts = {
        i: call("GET", f"/v1/notifications/{i}").json()["delivery_attempts"] for i in emails
    }
    check(any(len(a) > 1 for a in attempts.values()), "hubo reintentos (más de un intento)")
    check(all(len(a) <= 3 for a in attempts.values()), "ninguno supera 3 intentos")
    for i in emails:
        if status[i] == "failed":
            check(len(attempts[i]) == 3, f"{i[:8]}: failed tras agotar los 3 intentos")
            check(
                all(a["outcome"] == "transient_error" for a in attempts[i]),
                f"{i[:8]}: todos sus intentos fueron errores pasajeros",
            )


def recovery() -> None:
    restart = os.environ.get("RESTART_CMD")
    if not restart:
        sys.exit("falta RESTART_CMD (comando que reinicia el worker); ver la cabecera del script")
    ids = [
        submit(channel="internal", recipient=f"rec{i}", body="sobrevive").json()["id"]
        for i in range(60)
    ]
    pending = sum(
        call("GET", f"/v1/notifications/{i}").json()["status"] not in TERMINAL for i in ids
    )
    print(f"trabajos sin terminar al reiniciar: {pending}")
    check(pending > 0, "hay trabajos pendientes al momento del reinicio")
    check(os.system(restart) == 0, "worker reiniciado")
    status = wait_terminal(ids, timeout=180)
    check(len(status) == 60, "las 60 notificaciones siguen consultables")
    check(all(s == "delivered" for s in status.values()), "todas se entregan tras el reinicio")


def access() -> None:
    body = {"channel": "internal", "recipient": "x", "body": "x"}
    check(call("POST", "/v1/notifications", key="", json=body).status_code == 401, "sin clave: 401")
    check(
        call("POST", "/v1/notifications", key="ntf_falsa", json=body).status_code == 401,
        "clave inválida: 401",
    )
    nid = submit(**body).json()["id"]
    check(
        call("POST", f"/v1/notifications/{nid}/reprocess").status_code == 403,
        "cliente sin rol admin no puede reprocesar (403)",
    )
    check(call("GET", "/v1/stats").status_code == 403, "cliente sin rol admin no ve stats (403)")
    check(call("GET", "/v1/stats", key=ADMIN_KEY).status_code == 200, "admin sí ve stats (200)")


def stats() -> None:
    print(call("GET", "/v1/stats", key=ADMIN_KEY).text)


COMMANDS = {
    "batch": batch,
    "idempotency": idempotency,
    "email-failure": email_failure,
    "email-degraded": email_degraded,
    "recovery": recovery,
    "access": access,
    "stats": stats,
}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS or not API_KEY:
        sys.exit(__doc__)
    COMMANDS[sys.argv[1]]()
