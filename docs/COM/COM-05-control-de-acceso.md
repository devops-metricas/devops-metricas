# COM-05: Establecer controles de acceso apropiados cuando el escenario los requiera.

> **Parcial. Completa Melissa.**

| | |
|---|---|
| **Responsable** | Melissa |
| **Estado** | Parcial |
| **Evidencia mínima que se revisa** | Pruebas de acceso autorizado y rechazado. |

## Qué hay y qué falta

Clave por cliente con rol `admin`; pruebas en `tests/` y comando `access` de `scripts/smoke.py`.
Probado en local. Falta ejecutarlo contra el clúster.

## Evidencia

[COM-05-acceso.txt](../evidencias/COM-05-acceso.txt): sin clave y clave inválida (401), cliente sin
rol admin (403) y admin autorizado (200).
