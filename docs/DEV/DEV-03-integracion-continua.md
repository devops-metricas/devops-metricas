# DEV-03: Ejecutar integración continua con GitHub Actions.

> **Pendiente por Diego.**

| | |
|---|---|
| **Responsable** | Diego |
| **Estado** | Pendiente |
| **Evidencia mínima que se revisa** | Pruebas y validaciones automáticas en PR; protección de rama que bloquea la integración cuando fallan. |

## Qué hay y qué falta

[ci.yml](../../.github/workflows/ci.yml) corre en cada PR y en cada push a `main`, con permisos `contents: read`:

- Job **`ci`**: `ruff check`, `ruff format --check` y `pytest` con PostgreSQL 16 como servicio, así que también
  corren las pruebas de integración.
- Job **`imagen`**: `docker build` para verificar que el Dockerfile no se rompe.

**Falta la protección de rama** que exija `ci` e `imagen` y bloquee el merge si fallan (ver [DEV-01](DEV-01-git-y-pull-requests.md)).
Sin ella el CI avisa pero no bloquea. Para la evidencia: un PR de prueba con una prueba rota, con el merge bloqueado.

## Evidencia

Pendiente de enlazar. Guardar las capturas en [evidencias/](../evidencias) con el prefijo `DEV-03-`.
