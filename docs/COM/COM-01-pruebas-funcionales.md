# COM-01: Implementar las funciones y reglas del escenario asignado.

> **Cubierto.**

| | |
|---|---|
| **Responsable** | Melissa |
| **Estado** | Cubierto |
| **Evidencia mínima que se revisa** | Pruebas de aceptación ejecutables y resultados verificables. |

## Qué hay y qué falta

Hay 23 pruebas en `tests/` y `scripts/smoke.py` (ver README). Pasan en local con PostgreSQL y Mailpit.
`smoke.py batch` e `idempotency` también pasan contra `dev` en el clúster (2026-11-08).

## Evidencia

[COM-01-pytest.txt](../evidencias/COM-01-pytest.txt): 23 pruebas pasan y el lote de 100 solicitudes
termina en `delivered`. Más pruebas del escenario en [ESC1-smoke-local.txt](../evidencias/ESC1-smoke-local.txt).

En el clúster: [COM-01-smoke-batch-idempotency.txt](../evidencias/COM-01-smoke-batch-idempotency.txt)
(100 solicitudes aceptadas y entregadas; idempotencia secuencial y concurrente).
