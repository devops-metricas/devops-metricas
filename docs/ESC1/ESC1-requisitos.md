# ESC1: Requisitos del Escenario 1 (Notificaciones multicanal)

> **Parcial. Completa Melissa.** Implementado y probado en local; falta ejecutarlo contra el clúster.

| Requisito | Dónde se cumple | Prueba |
|---|---|---|
| ESC1-01 Registrar al menos dos clientes e identificar el origen | `python -m notifier.cli create-client` (tabla `clients`); cada notificación guarda `client_id` | `test_clients_cannot_read_each_others_notifications` |
| ESC1-02 Autenticar y rechazar clientes no autorizados | `X-API-Key` con hash en `security.py` | `test_unauthorized_client_is_rejected`; `smoke.py access` |
| ESC1-03 Aceptar destinatario, canal, contenido y clave opcional | `POST /v1/notifications` | `test_accept_then_deliver_both_channels`; `test_invalid_requests_rejected` |
| ESC1-04 Correo de prueba e interno consultable | Canales `email` (Mailpit) e `internal`; `GET /v1/inbox/{recipient}` | `test_accept_then_deliver_both_channels` |
| ESC1-05 Estados y transiciones | Tabla `notification_events` | `test_accept_then_deliver_both_channels` |
| ESC1-06 Estado e historial de intentos | `GET /v1/notifications/{id}` (`delivery_attempts`) | `test_transient_failure_retries_then_fails_and_can_be_reprocessed` |
| ESC1-07 Reintentar transitorios, no permanentes | Hasta 3 intentos con espera exponencial en el worker | `test_transient_failure_retries_…`; `test_permanent_failure_is_not_retried`; `smoke.py email-degraded` |
| ESC1-08 Reproceso explícito autorizado | `POST /v1/notifications/{id}/reprocess` (rol `admin`) | `test_transient_failure_retries_…_can_be_reprocessed`; `smoke.py access` |
| ESC1-09 Idempotencia | Índice único por (cliente, canal, clave) | `test_idempotency_sequential_and_conflict`; `test_idempotency_concurrent`; `smoke.py idempotency` |
| ESC1-10 Recuentos y tasas por canal y estado | `GET /v1/stats` (rol `admin`) | `test_stats_by_channel_and_status` |

## Pruebas del escenario (P1-1 a P1-5)

| Prueba | Comando | Estado |
|---|---|---|
| P1-1 Carga controlada (100 solicitudes) | `smoke.py batch` | Pasa en local |
| P1-2 Dependencia degradada | `smoke.py email-degraded` (worker con `NOTIFIER_EMAIL_FAULT_RATE>0`) | Pasa en local |
| P1-3 Idempotencia secuencial y concurrente | `smoke.py idempotency` | Pasa en local |
| P1-4 Recuperación al reiniciar el worker | `smoke.py recovery` | Pasa en local; falta contra el clúster |
| P1-5 Correlación de extremo a extremo y alerta | Trazas y alerta (métricas) | **Pendiente por Camila y Rene** (MET-04 y MET-06) |

## Qué falta

Ejecutar los comandos contra el ambiente `dev` en el clúster y guardar la salida en
[evidencias/](../evidencias) con el prefijo `ESC1-`. Depende de que la aplicación esté desplegada (Diego).

## Evidencia

[ESC1-smoke-local.txt](../evidencias/ESC1-smoke-local.txt): P1-1 (100 solicitudes), P1-3 (idempotencia
secuencial y concurrente) y recuentos de `GET /v1/stats`, ejecutados en local. P1-2 y P1-4 pasaron en
local sin captura guardada.
