# COM-05: Establecer controles de acceso apropiados cuando el escenario los requiera.

> **Cubierto.**

| | |
|---|---|
| **Responsable** | Melissa |
| **Estado** | Cubierto |
| **Evidencia mínima que se revisa** | Pruebas de acceso autorizado y rechazado. |

## Qué hay y qué falta

Clave por cliente con rol `admin`; pruebas en `tests/` y comando `access` de `scripts/smoke.py`.
Probado en local y contra `dev` en el clúster (2026-11-08).

## Evidencia

[COM-05-acceso.txt](../evidencias/COM-05-acceso.txt): sin clave y clave inválida (401), cliente sin
rol admin (403) y admin autorizado (200).
En el clúster: [COM-05-smoke-access.txt](../evidencias/COM-05-smoke-access.txt), mismos resultados.
