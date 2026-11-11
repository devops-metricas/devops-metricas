"""Incidente controlado y reproducible (MET-07, condición 5.11): proveedor de correo degradado.

Envía tráfico constante y pasa por cuatro fases con marca temporal UTC:
    base         proveedor sano
    degradacion  FAULT_CMD activa NOTIFIER_EMAIL_FAULT_RATE en el worker (503 inyectados)
    recuperacion RESTORE_CMD quita la falla
    mitigacion   el admin reprocesa las notificaciones que quedaron 'failed' por la degradación
Al final calcula, por fase y canal, los SLI de MET-01 a partir de la API (fuente de verdad), y
guarda la línea de tiempo y los números en docs/evidencias/MET-07-*.

    export API_URL=https://<fqdn>/dev API_KEY=ntf_... ADMIN_KEY=ntf_...
    export FAULT_CMD='./scripts/vm.sh "k3s kubectl -n notifier-dev set env deploy/worker \
NOTIFIER_EMAIL_FAULT_RATE=0.6 && k3s kubectl -n notifier-dev rollout status deploy/worker"'
    export RESTORE_CMD='./scripts/vm.sh "k3s kubectl -n notifier-dev set env deploy/worker \
NOTIFIER_EMAIL_FAULT_RATE- && k3s kubectl -n notifier-dev rollout status deploy/worker"'
    python scripts/incidente.py

Variables opcionales: RATE (solicitudes/s, 2), PHASE_SECONDS (duración de cada fase, 180),
OBJETIVO_S (umbral del SLI de entrega oportuna, 30). Solo datos ficticios.
"""

import json
import os
import statistics
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import httpx

API_URL = os.environ.get("API_URL", "http://localhost:8000")
API_KEY = os.environ.get("API_KEY", "")
ADMIN_KEY = os.environ.get("ADMIN_KEY", API_KEY)
FAULT_CMD = os.environ.get("FAULT_CMD", "")
RESTORE_CMD = os.environ.get("RESTORE_CMD", "")
RATE = float(os.environ.get("RATE", "2"))
PHASE_SECONDS = float(os.environ.get("PHASE_SECONDS", "180"))
OBJETIVO_S = float(os.environ.get("OBJETIVO_S", "30"))
TERMINAL = {"delivered", "failed"}

RUN = uuid.uuid4().hex[:8]
OUT = Path(__file__).resolve().parent.parent / "docs" / "evidencias"
timeline: list[tuple[str, str]] = []
sent: list[dict] = []  # {id, phase, channel, sent_at}
phase = "base"
stop = threading.Event()


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def mark(event: str) -> None:
    timeline.append((now(), event))
    print(f"{timeline[-1][0]}  {event}", flush=True)


def call(method: str, path: str, key: str = API_KEY, **kw) -> httpx.Response:
    return httpx.request(method, API_URL + path, headers={"X-API-Key": key}, timeout=15, **kw)


def sender() -> None:
    """Tráfico constante: 2 de cada 3 por correo (el canal afectado), 1 interno (control)."""
    i = 0
    while not stop.is_set():
        t0 = time.monotonic()
        channel = "internal" if i % 3 == 2 else "email"
        recipient = f"usuario{i}@example.test" if channel == "email" else f"usuario{i}"
        try:
            r = httpx.post(
                API_URL + "/v1/notifications",
                timeout=15,
                json={
                    "channel": channel,
                    "recipient": recipient,
                    "subject": f"Incidente {RUN}",
                    "body": f"mensaje {i} fase {phase}",
                },
                headers={"X-API-Key": API_KEY, "X-Request-Id": f"inc-{RUN}-{i}"},
            )
            if r.status_code == 202:
                sent.append(
                    {"id": r.json()["id"], "phase": phase, "channel": channel, "sent_at": now()}
                )
            elif r.status_code in (401, 403):
                mark(f"clave rechazada ({r.status_code}): revisar API_KEY; se detiene la corrida")
                os._exit(1)
            else:
                mark(f"respuesta inesperada {r.status_code} en la solicitud {i}")
        except httpx.HTTPError as exc:
            mark(f"error de red en la solicitud {i}: {exc}")
        i += 1
        stop.wait(max(0.0, 1 / RATE - (time.monotonic() - t0)))


def run_cmd(cmd: str, what: str) -> None:
    mark(f"inicio: {what}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout, result.stderr, file=sys.stderr)
        stop.set()
        sys.exit(f"falló: {what}")
    mark(f"fin: {what}")


def details(ids: list[str]) -> dict[str, dict]:
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = pool.map(lambda i: call("GET", f"/v1/notifications/{i}", ADMIN_KEY).json(), ids)
    return {r["id"]: r for r in rows}


def wait_terminal(ids: list[str], timeout: float = 300) -> dict[str, dict]:
    deadline = time.monotonic() + timeout
    while True:
        rows = details(ids)
        if all(r["status"] in TERMINAL for r in rows.values()) or time.monotonic() > deadline:
            return rows
        time.sleep(5)


def seconds(a: str, b: str) -> float:
    return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()


def summarize(rows: dict[str, dict], label: str) -> list[dict]:
    out = []
    for ph in ("base", "degradacion", "recuperacion"):
        for ch in ("email", "internal"):
            group = [rows[s["id"]] for s in sent if s["phase"] == ph and s["channel"] == ch]
            if not group:
                continue
            e2e = [seconds(r["created_at"], r["delivered_at"]) for r in group if r["delivered_at"]]
            on_time = sum(1 for x in e2e if x <= OBJETIVO_S)
            q = statistics.quantiles(e2e, n=20) if len(e2e) >= 2 else [0] * 19
            out.append(
                {
                    "momento": label,
                    "fase": ph,
                    "canal": ch,
                    "aceptadas": len(group),
                    "entregadas": sum(r["status"] == "delivered" for r in group),
                    "fallidas": sum(r["status"] == "failed" for r in group),
                    "sli_entrega_oportuna_pct": round(100 * on_time / len(group), 1),
                    "intentos_promedio": round(statistics.mean(r["attempts"] for r in group), 2),
                    "e2e_p50_s": round(statistics.median(e2e), 2) if e2e else None,
                    "e2e_p95_s": round(q[18], 2) if e2e else None,
                }
            )
    return out


def table(rows: list[dict]) -> str:
    cols = list(rows[0])
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows]
    return "\n".join(lines)


def main() -> None:
    global phase
    if not (API_KEY and FAULT_CMD and RESTORE_CMD):
        sys.exit(__doc__)
    mark(f"corrida {RUN}: {RATE} solicitudes/s, fases de {PHASE_SECONDS:g} s")
    mark(f"objetivo de entrega oportuna: {OBJETIVO_S:g} s")
    hilo = threading.Thread(target=sender, daemon=True)
    hilo.start()

    mark("fase base (proveedor sano)")
    time.sleep(PHASE_SECONDS)

    phase = "degradacion"
    run_cmd(FAULT_CMD, "activar falla del proveedor de correo")
    time.sleep(PHASE_SECONDS)

    phase = "recuperacion"
    run_cmd(RESTORE_CMD, "quitar la falla del proveedor de correo")
    time.sleep(PHASE_SECONDS)
    stop.set()
    hilo.join(timeout=30)  # esperar la solicitud en vuelo: si no, queda fuera de la consulta
    mark(f"fin del tráfico: {len(sent)} solicitudes aceptadas")

    ids = [s["id"] for s in sent]
    rows = wait_terminal(ids)
    mark("todas las notificaciones en estado final (o se agotó la espera)")
    antes = summarize(rows, "antes de mitigar")

    failed = [i for i, r in rows.items() if r["status"] == "failed"]
    mark(f"mitigación: reprocesar {len(failed)} notificaciones fallidas (acción de admin)")
    for i in failed:
        call("POST", f"/v1/notifications/{i}/reprocess", ADMIN_KEY)
    rows = wait_terminal(ids)
    mark("verificación posterior: estados finales tras el reproceso")
    despues = summarize(rows, "después de mitigar")

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%MZ")
    report = [
        f"# MET-07: incidente controlado, corrida {RUN}",
        "",
        "## Línea de tiempo (UTC)",
        "",
        *[f"- `{t}` {e}" for t, e in timeline],
        "",
        "## Resultados por fase (fuente: API, GET /v1/notifications/{id})",
        "",
        table(antes + despues),
        "",
        "Ejemplos de notificaciones fallidas para correlacionar (scripts/correlacion.sh):",
        *[f"- {i}" for i in failed[:3]],
    ]
    (OUT / f"MET-07-incidente-{stamp}.md").write_text("\n".join(report) + "\n")
    (OUT / f"MET-07-incidente-{stamp}.json").write_text(
        json.dumps(
            {"run": RUN, "timeline": timeline, "sent": sent, "resumen": antes + despues},
            indent=1,
            ensure_ascii=False,
        )
    )
    print("\n".join(report))
    print(f"\nEvidencia: docs/evidencias/MET-07-incidente-{stamp}.md (y .json)")


if __name__ == "__main__":
    main()
