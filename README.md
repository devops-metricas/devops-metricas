# Plataforma de notificaciones multicanal

Proyecto de cátedra (DevOps + Métricas de Software), **Escenario 1**. Las aplicaciones cliente piden
enviar mensajes; la plataforma los entrega por correo de prueba o como notificación interna,
reintenta fallas pasajeras, evita duplicados y deja consultar qué pasó con cada envío.

## Documentación por requisito

Cada documento lleva el ID del requisito que sustenta. Las capturas están en `docs/evidencias/`, con el
mismo prefijo. Lo que es solo del equipo (reparto, enunciado, guía del escenario) está en
[docs/interno/](docs/interno/).

| Requisito | Documento |
|---|---|
| COM-02 | [Arquitectura](docs/COM-02-arquitectura.md) |
| COM-06 | [Decisiones técnicas y alternativas descartadas](docs/COM-06-decisiones.md) |
| DEV-06, DEV-07, DEV-09 | [Infraestructura](docs/COM-02-arquitectura.md#infraestructura-azure) y [evidencias](docs/evidencias/) |
| DEV-13 | [Reconstrucción, apagado y destrucción](docs/DEV-13-reconstruccion.md) |
| DEV-14 | [Costos](docs/DEV-14-costos.md) |
| Evidencias de todos los requisitos | `docs/EVIDENCIAS.md` (pendiente) |

## Arquitectura

```
cliente ──HTTPS──▶ API (FastAPI) ──┐
                                   ├──▶ PostgreSQL (notificaciones, intentos, eventos, cola)
                   Worker ◀────────┘          │
                      │                       └─ cola = filas pending/processing (SKIP LOCKED)
                      ├──▶ SMTP de pruebas (Mailpit)      canal email
                      └──▶ tabla internal_messages        canal internal
```

Una sola imagen (`Dockerfile`) sirve para API, worker y migraciones; cambia el comando.
Detalle en [docs/COM-02-arquitectura.md](docs/COM-02-arquitectura.md).

## Desarrollo local

Requisitos: Python 3.12+ y Docker.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
docker compose up -d                       # PostgreSQL + Mailpit (UI en http://localhost:8025)

python -m notifier.migrate                 # crea el esquema
python -m notifier.cli create-client app-pedidos          # imprime la API key
python -m notifier.cli create-client operaciones --admin  # rol admin: reproceso y estadísticas

uvicorn notifier.api.app:app --reload      # API en :8000 (docs en /docs)
python -m notifier.worker.main             # worker (métricas en :9100)
```

Enviar una notificación:

```bash
curl -s -X POST localhost:8000/v1/notifications \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"recipient":"ana@example.test","channel":"email","subject":"Hola","body":"Prueba","idempotency_key":"pedido-1"}'
```

### API

| Método y ruta | Rol | Descripción |
|---|---|---|
| `POST /v1/notifications` | cliente | Acepta una solicitud. `202` = recibida (no entregada); `200` si es repetición idempotente; `409` si la clave se reutiliza con otro contenido |
| `GET /v1/notifications/{id}` | cliente / admin | Estado, historial de transiciones e intentos |
| `POST /v1/notifications/{id}/reprocess` | admin | Reprocesa una notificación `failed` |
| `GET /v1/inbox/{recipient}` | cliente / admin | Notificaciones internas del destinatario |
| `GET /v1/stats` | admin | Recuentos y tasas por canal y estado |
| `GET /healthz`, `/readyz`, `/metrics` | — | Liveness, readiness (consulta la BD) y métricas Prometheus |

Regla del destinatario `…@invalid.test`: el proveedor simulado lo rechaza de forma permanente (no se reintenta).

### Inyectar fallas del correo (prueba P1-2 / incidente)

`NOTIFIER_EMAIL_FAULT_RATE=0.7` (y `NOTIFIER_EMAIL_FAULT_KIND=503|timeout`) en el worker hace que
el 70 % de los envíos por correo fallen de forma pasajera; el canal interno no se afecta.

### Pruebas reproducibles contra un ambiente en ejecución

`scripts/smoke.py` crea datos ficticios, comprueba el resultado y termina con código distinto de cero
si algo falla. Funciona igual en local, dev o prod:

```bash
export API_URL=http://localhost:8000 API_KEY=ntf_... ADMIN_KEY=ntf_...   # claves de create-client
python scripts/smoke.py access          # ESC1-02: sin clave, clave inválida y rol insuficiente
python scripts/smoke.py batch           # P1-1: 100 solicitudes entre ambos canales
python scripts/smoke.py idempotency     # P1-3: 5 repeticiones, secuenciales y concurrentes
python scripts/smoke.py email-failure   # error permanente: failed sin reintentos
```

Con el worker en modo degradado (`NOTIFIER_EMAIL_FAULT_RATE=1.0`):

```bash
python scripts/smoke.py email-degraded  # P1-2: se aceptan, reintenta hasta 3 veces; el canal interno sigue
```

Reinicio del worker con trabajos pendientes (P1-4); `RESTART_CMD` reinicia el worker del ambiente:

```bash
# En el clúster
RESTART_CMD="kubectl -n notifier-dev rollout restart deploy/worker" python scripts/smoke.py recovery
# En local: con el worker detenido, el comando solo lo arranca (los trabajos quedan pendientes)
RESTART_CMD="python -m notifier.worker.main &" python scripts/smoke.py recovery
```

## Pruebas y calidad

```bash
ruff check . && ruff format --check .
pytest                                                              # unitarias
NOTIFIER_DATABASE_URL=postgresql://notifier:notifier@localhost:5432/notifier pytest   # + integración (borra datos de esa BD)
```

## Estructura

```
src/notifier/   API, worker, canales, migraciones SQL, observabilidad
tests/          unitarias e integración
k8s/            manifiestos (kustomize): base + overlays dev y prod
infra/          Terraform (Azure + K3s) y bootstrap inicial
.github/        CI, Terraform, entrega y rollback
scripts/        pruebas reproducibles (lote, idempotencia)
docs/           un documento por requisito (COM-02, COM-06, DEV-13, DEV-14), evidencias/ e interno/
```
