# MET-02: Incorporar logs estructurados para operaciones y fallas relevantes.

| | |
|---|---|
| **Responsable** | Camila |
| **Estado** | Parcial: verificado en local; falta la captura en el clúster |
| **Evidencia mínima que se revisa** | Registros con identificadores que permitan correlación. |

## 1. Formato

Cada línea es un objeto JSON (`structlog`, configurado en `src/notifier/observability.py`):

| Campo | Siempre | Qué es |
|---|---|---|
| `timestamp` | Sí | ISO 8601 en UTC. |
| `level` | Sí | `info`, `warning`, `error`. |
| `component` | Sí | `api` o `worker`. |
| `environment` | Sí | `local`, `dev` o `prod` (sale de `NOTIFIER_ENVIRONMENT`). |
| `event` | Sí | Qué ocurrió (tabla de la sección 2). |
| `trace_id`, `span_id` | Si hay traza activa | Identificador W3C de la traza: une logs de la API, logs del worker y la traza en Jaeger. |
| `request_id` | En la API | Cabecera `X-Request-Id` del cliente o uno generado. Se devuelve en la respuesta: el cliente puede citarlo al reportar un problema. |
| `notification_id` | En eventos de una notificación | UUID de la notificación, el que ve el cliente. |

**Datos sensibles.** Los logs no incluyen la clave de API (solo el nombre del cliente), el cuerpo del
mensaje ni el destinatario. Excepción conocida: cuando el servidor SMTP rechaza un destinatario, el
texto del `error` que devuelve `smtplib` incluye la dirección. Con datos ficticios no es un riesgo; con
datos reales habría que truncar ese mensaje antes de registrarlo.

## 2. Eventos registrados

| `event` | Componente | Nivel | Cuándo | Campos clave |
|---|---|---|---|---|
| `request_completed` | api | info | Toda solicitud (excepto salud y métricas) | `method`, `path`, `status`, `duration_ms` |
| `request_failed` | api | error | Excepción no controlada | traza de la excepción |
| `notification_accepted` | api | info | Alta nueva (202) | `notification_id`, `client`, `channel` |
| `notification_replayed` | api | info | Repetición idempotente (200) | `notification_id`, `client` |
| `idempotency_conflict` | api | warning | Misma clave, otro contenido (409) | `client`, `channel` |
| `notification_reprocessed` | api | info | Reproceso de una fallida por admin | `notification_id`, `by` |
| `delivery_attempt` | worker | info | Cada intento de entrega | `notification_id`, `attempt`, `outcome`, `final_status`, `error` |
| `unexpected_delivery_error` | worker | error | Excepción no prevista al entregar | `notification_id` |
| `worker_started` / `worker_stopped` | worker | info | Arranque y apagado ordenado | |
| `worker_loop_error` | worker | error | Falla del ciclo (p. ej. base caída) | traza de la excepción |

Las transiciones de estado completas quedan además en la tabla `notification_events` (consultables con
`GET /v1/notifications/{id}`): los logs son para investigar, la base es la fuente de verdad.

## 3. Cómo se correlaciona

La API guarda el `traceparent` de la solicitud en la fila de la notificación. El worker lo lee al tomar
el trabajo y abre su span como hijo de esa traza. Por eso **el mismo `trace_id` aparece en el log de la
API y en todos los intentos del worker**, aunque pasen minutos entre uno y otro y estén en Pods
distintos.

Ejemplo real (entorno local, falla inyectada al 70 %; archivo completo en
[evidencias/MET-02-correlacion-local.txt](../evidencias/MET-02-correlacion-local.txt)):

| Hora (UTC) | Componente | `event` | Detalle | `trace_id` |
|---|---|---|---|---|
| 02:16:… | api | `notification_accepted` | canal email | `8dc551ea…` |
| +0,2 s | worker | `delivery_attempt` | intento 1, `transient_error` (503) | `8dc551ea…` |
| +1,3 s | worker | `delivery_attempt` | intento 2, `transient_error` (503) | `8dc551ea…` |
| +3,3 s | worker | `delivery_attempt` | intento 3, `success` | `8dc551ea…` |

Con ese `trace_id` se abre la traza en Jaeger ([MET-04](MET-04-trazas-opentelemetry.md)).

Un reproceso manual (`notification_reprocessed`) ocurre en otra solicitud HTTP, con su propio `trace_id`,
pero el intento que genera en el worker sigue en la traza **original** de la notificación, porque el
`traceparent` guardado no cambia. Para unir las dos se usa el `notification_id`.

## 4. Consultas de investigación

En el clúster los logs se leen con `kubectl` dentro de la VM (la API de Kubernetes no se expone). El
script `scripts/correlacion.sh` hace los pasos 1 a 3 y guarda la evidencia.

```bash
# 1. Todo lo que pasó con una notificación (API y worker)
./scripts/vm.sh "k3s kubectl -n notifier-dev logs deploy/api --since=1h | grep <notification_id>"
./scripts/vm.sh "k3s kubectl -n notifier-dev logs deploy/worker --since=1h | grep <notification_id>"

# 2. Todos los intentos fallidos de la última hora, con su error
./scripts/vm.sh "k3s kubectl -n notifier-dev logs deploy/worker --since=1h | grep '\"outcome\": \"transient_error\"'"

# 3. Lo que vio un cliente que reporta un problema con su X-Request-Id
./scripts/vm.sh "k3s kubectl -n notifier-dev logs deploy/api --since=1h | grep <request_id>"

# 4. Errores no previstos
./scripts/vm.sh "k3s kubectl -n notifier-dev logs deploy/worker --since=1h | grep '\"level\": \"error\"'"
```

## 5. Limitaciones

- Los logs viven en el nodo mientras exista el contenedor: un Pod eliminado pierde los suyos
  (`kubectl logs --previous` solo recupera el reinicio inmediato anterior). No se agregó un backend de
  logs (Loki) para no sumar memoria en la VM de 8 GB; la evidencia se guarda en `docs/evidencias/`.
- `grep` sobre texto no permite agregaciones: para contar o comparar se usan las métricas (MET-01).

## Evidencia

- [x] Correlación verificada en local: [MET-02-correlacion-local.txt](../evidencias/MET-02-correlacion-local.txt).
- [ ] En el clúster: `scripts/correlacion.sh <id> dev` → `evidencias/MET-02-correlacion-<id>.txt`.
