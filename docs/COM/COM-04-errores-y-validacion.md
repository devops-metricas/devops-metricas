# COM-04: Manejar errores previsibles y validar entradas.

> **Cubierto.**

| | |
|---|---|
| **Responsable** | Melissa |
| **Estado** | Cubierto |
| **Evidencia mínima que se revisa** | Pruebas positivas, negativas y de recuperación. |

## Qué hay y qué falta

Pruebas negativas y de recuperación en `tests/` y comandos `email-failure`, `email-degraded` y
`recovery` de `scripts/smoke.py`. Probados en local y en `dev` en el clúster (2026-11-08).

## Evidencia

- [COM-04-errores.txt](../evidencias/COM-04-errores.txt): `email-failure` (error permanente sin
  reintentos) y las pruebas negativas y de recuperación de pytest.
- [COM-04-degradado-y-recuperacion.txt](../evidencias/COM-04-degradado-y-recuperacion.txt):
  `email-degraded` (reintenta hasta 3 veces y el canal interno sigue) y `recovery` (60 trabajos
  pendientes al reiniciar el worker, todos se entregan).
- [COM-04-smoke-errores-y-recovery.txt](../evidencias/COM-04-smoke-errores-y-recovery.txt): los tres comandos
  en el clúster. `email-degraded` con `NOTIFIER_EMAIL_FAULT_RATE=1.0` en el worker (revertido al terminar).
  `recovery` con el worker escalado a 0 antes de la prueba, para que haya trabajos pendientes: en el
  clúster el worker despacha más rápido de lo que el script lee el estado.
