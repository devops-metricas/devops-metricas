# DEV-01: Versionar aplicación, infraestructura y configuraciones no secretas en Git.

> **Pendiente por Diego.**

| | |
|---|---|
| **Responsable** | Diego |
| **Estado** | Pendiente |
| **Evidencia mínima que se revisa** | Repositorio e historial con pull requests revisados. |

## Qué hay y qué falta

Todo el código, la infraestructura (`infra/`), los manifiestos (`k8s/`) y la documentación están en Git, sin
secretos. Los cambios entran por pull request desde ramas con prefijo por tipo (`ci/`, `docs/`, `fix/`, `feat/`,
`infra/`), y el historial conserva cada PR mergeado con el ID del requisito en el título. Listado de PR:
`gh pr list --state all`.

**Falta la protección de `main`**: hoy no hay reglas ni *rulesets* en el repositorio (la API devuelve 404), así que
la regla "todo entra por PR" depende de la disciplina del equipo. Configuración propuesta, que requiere permisos
de administración (Melissa), en Settings, Rules, Rulesets: requerir pull request con 1 aprobación, requerir los
checks `ci` e `imagen`, bloquear los push directos y los force-push. Cubre también DEV-03.

## Evidencia

Pendiente de enlazar. Guardar las capturas en [evidencias/](../evidencias) con el prefijo `DEV-01-`.
