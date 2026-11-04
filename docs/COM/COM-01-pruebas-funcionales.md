# COM-01: Implementar las funciones y reglas del escenario asignado.

> **Parcial. Completa Melissa.**

| | |
|---|---|
| **Responsable** | Melissa |
| **Estado** | Parcial |
| **Evidencia mínima que se revisa** | Pruebas de aceptación ejecutables y resultados verificables. |

## Qué hay y qué falta

Hay 23 pruebas en `tests/` y `scripts/smoke.py` (ver README). Pasan en local con PostgreSQL y Mailpit.
Falta ejecutar `smoke.py` contra el clúster, que depende de que la app esté desplegada (Diego).

## Evidencia

[COM-01-pytest.txt](../evidencias/COM-01-pytest.txt): 23 pruebas pasan y el lote de 100 solicitudes
termina en `delivered`. Más pruebas del escenario en [ESC1-smoke-local.txt](../evidencias/ESC1-smoke-local.txt).
