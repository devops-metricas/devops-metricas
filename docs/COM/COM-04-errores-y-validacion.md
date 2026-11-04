# COM-04: Manejar errores previsibles y validar entradas.

> **Parcial. Completa Melissa.**

| | |
|---|---|
| **Responsable** | Melissa |
| **Estado** | Parcial |
| **Evidencia mínima que se revisa** | Pruebas positivas, negativas y de recuperación. |

## Qué hay y qué falta

Pruebas negativas y de recuperación en `tests/` y comandos `email-failure`, `email-degraded` y
`recovery` de `scripts/smoke.py`. Falta guardar la salida de `email-degraded` y `recovery` (probados
en local, sin captura) y ejecutarlos en el clúster.

## Evidencia

[COM-04-errores.txt](../evidencias/COM-04-errores.txt): `email-failure` (error permanente sin
reintentos) y las pruebas negativas y de recuperación de pytest.
