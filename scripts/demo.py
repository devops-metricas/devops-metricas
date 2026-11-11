"""Demostración guiada contra una API en ejecución (dev), con salida legible para presentar.

    export API_URL=https://<fqdn>/dev API_KEY=ntf_... ADMIN_KEY=ntf_...
    python scripts/demo.py            # avanza con Enter en cada paso
    python scripts/demo.py --auto     # sin pausas

Usa solo datos ficticios. Los pasos que tocan el clúster (degradar el correo, reiniciar el worker,
borrar el Pod de PostgreSQL) no están aquí: se hacen aparte, como indica la guía de práctica.
"""

import os
import subprocess
import sys
import time
import uuid

import httpx

API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.environ.get("API_KEY", "")
ADMIN_KEY = os.environ.get("ADMIN_KEY", API_KEY)
AUTO = "--auto" in sys.argv

B, G, Y, R = "\033[1m", "\033[32m", "\033[33m", "\033[31m"
C, D, X = "\033[36m", "\033[2m", "\033[0m"
SMOKE = os.path.join(os.path.dirname(__file__), "smoke.py")


def paso(titulo: str, idea: str) -> None:
    if not AUTO:
        input(f"\n{D}[Enter para continuar]{X}")
    print(f"\n{B}{C}━━ {titulo} ━━{X}\n{D}{idea}{X}\n")


def llamar(metodo: str, ruta: str, clave: str = API_KEY, **kw) -> httpx.Response:
    r = httpx.request(metodo, API_URL + ruta, headers={"X-API-Key": clave}, timeout=15, **kw)
    color = G if r.status_code < 300 else (Y if r.status_code < 500 else R)
    print(f"  {B}{metodo} {ruta}{X}  →  {color}{B}{r.status_code}{X}")
    return r


def esperar_final(nid: str) -> dict:
    for _ in range(40):
        d = httpx.get(f"{API_URL}/v1/notifications/{nid}", headers={"X-API-Key": API_KEY}).json()
        if d["status"] in ("delivered", "failed"):
            return d
        time.sleep(1)
    return d


def main() -> None:
    if not API_KEY:
        sys.exit("Falta API_KEY (y ADMIN_KEY) en el entorno.")
    print(f"{B}Demostración: notificaciones multicanal{X}   {D}{API_URL}{X}")

    paso("1. Enviar una notificación", "202 significa recibida y registrada, no entregada.")
    clave = f"demo-{uuid.uuid4().hex[:8]}"
    cuerpo = {
        "recipient": "ana@example.test",
        "channel": "internal",
        "subject": "Hola",
        "body": "Prueba de la demo",
        "idempotency_key": clave,
    }
    r = llamar("POST", "/v1/notifications", json=cuerpo)
    nid = r.json()["id"]
    print(f"  id: {nid}\n  estado al responder: {Y}{r.json().get('status', 'pending')}{X}")
    d = esperar_final(nid)
    print(f"  estado final: {G if d['status'] == 'delivered' else R}{B}{d['status']}{X}")
    for a in d.get("delivery_attempts", []):
        print(f"  intento {a.get('attempt_no', '?')}: {a.get('outcome', a)}")

    paso(
        "2. Idempotencia",
        "La misma clave devuelve la original; con otro contenido es un conflicto.",
    )
    r2 = llamar("POST", "/v1/notifications", json=cuerpo)
    igual = r2.json().get("id") == nid
    print(f"  misma notificación: {G if igual else R}{B}{'sí' if igual else 'NO'}{X}")
    llamar("POST", "/v1/notifications", json={**cuerpo, "body": "Otro contenido"})
    print(f"  {D}409 = misma clave con contenido distinto{X}")

    paso("3. Lote de 100 solicitudes", "P1-1: todas deben quedar en estado final.")
    subprocess.run([sys.executable, SMOKE, "batch"], check=False)

    paso("7. Acceso rechazado", "Sin clave o con clave inválida da 401; sin rol admin, 403.")
    subprocess.run([sys.executable, SMOKE, "access"], check=False)

    paso(
        "Recuentos (GET /v1/stats)",
        "Anótalos antes de borrar el Pod de PostgreSQL; compáralos después.",
    )
    r = llamar("GET", "/v1/stats", clave=ADMIN_KEY)
    s = r.json()
    for k, v in s.items():
        print(f"  {B}{k}{X}: {v}")
    print(f"\n{G}{B}Fin de la parte automática.{X}")


if __name__ == "__main__":
    main()
