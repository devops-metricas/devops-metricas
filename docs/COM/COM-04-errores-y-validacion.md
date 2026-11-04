# COM-04: Manejar errores previsibles y validar entradas.

> **Parcial. Completa Melissa.**

| | |
|---|---|
| **Responsable** | Melissa |
| **Estado** | Parcial |
| **Evidencia mínima que se revisa** | Pruebas positivas, negativas y de recuperación. |

## Qué hay y qué falta

Pruebas negativas y de recuperación en `tests/` y comandos `email-failure`, `email-degraded` y
`recovery` de `scripts/smoke.py`. Probados en local; falta ejecutarlos en el clúster.

## Evidencia

- [COM-04-errores.txt](../evidencias/COM-04-errores.txt): `email-failure` (error permanente sin
  reintentos) y las pruebas negativas y de recuperación de pytest.
- [COM-04-degradado-y-recuperacion.txt](../evidencias/COM-04-degradado-y-recuperacion.txt):
  `email-degraded` (reintenta hasta 3 veces y el canal interno sigue) y `recovery` (60 trabajos
  pendientes al reiniciar el worker, todos se entregan).
