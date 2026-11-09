# COM-03: Persistir la información cuya conservación exija el escenario.

> **Cubierto.**

| | |
|---|---|
| **Responsable** | Melissa |
| **Estado** | Cubierto |
| **Evidencia mínima que se revisa** | Demostración de persistencia ante reinicio de componentes. |

## Qué hay y qué falta

El esquema persiste en PostgreSQL con volumen (`k8s/base/postgres.yaml`). En `dev` se reiniciaron `deploy/api`, `deploy/worker` y el Pod `postgres-0` (2026-11-08) y los recuentos de `GET /v1/stats` quedaron idénticos.

## Evidencia

- [COM-03-stats-antes.txt](../evidencias/COM-03-stats-antes.txt): correo 53 (50 `delivered`, 3 `failed`) e interno 54 (`delivered`).
- [COM-03-stats-despues.txt](../evidencias/COM-03-stats-despues.txt): los mismos recuentos tras reiniciar API, worker y PostgreSQL.
