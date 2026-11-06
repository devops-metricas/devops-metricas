# DEV-08: Integrar la validación de Terraform en GitHub Actions.

> **Parcial. Faltan las capturas.**

| | |
|---|---|
| **Responsable** | Diego |
| **Estado** | Parcial |
| **Evidencia mínima que se revisa** | Validación y plan ante cambios, sin aplicar automáticamente PR no aprobados. |

## Qué hay y qué falta

El workflow [terraform.yml](../../.github/workflows/terraform.yml) se dispara cuando cambia
`infra/terraform/**` o el propio workflow:

| Evento | Jobs | Identidad en Azure | ¿Aplica? |
|---|---|---|---|
| Pull request | `validate` y `plan` | `sp-notifier-plan`, solo **Reader** | **No, nunca** |
| Push a `main` | `validate`, `plan` y `apply` | `sp-notifier-infra`, Contributor | Sí, tras la aprobación del entorno `infra` |

- **`validate`**: `terraform fmt -check -recursive`, `init -backend=false` y `validate`. No toca Azure.
- **`plan`**: usa el estado remoto y escribe el plan en el resumen de la ejecución para revisarlo en el PR.
- **`apply`**: solo con `push` a `main` (`if`), dentro del entorno `infra`, que exige un revisor. Vuelve a
  planear y aplica en el mismo job y sobre el mismo commit; no reutiliza un archivo de plan porque en un
  repo público el artefacto expondría valores sensibles.
- **Un PR no puede aplicar**: la identidad con Contributor solo acepta tokens de `main` y del entorno
  `infra` (credenciales federadas de [bootstrap.sh](../../infra/bootstrap/bootstrap.sh)); la de los PR es de
  solo lectura, porque un PR puede editar el workflow.
- **Un solo plan o apply a la vez**: `concurrency: terraform`, más el candado del estado remoto.
- **Datos personales**: la IP de administración y los correos van como *secrets*, para que se enmascaren
  en los logs públicos.

Falta: capturar las ejecuciones de abajo y enlazarlas. Estado Parcial hasta tener las capturas.

## Evidencia

Ejecuciones reales del workflow:

- Plan en un PR, en verde: [run 41774273160](https://github.com/kmmelissat/devops-metricas/actions/runs/41774273160).
- Push a `main` con plan y apply aprobado: [run 41774548688](https://github.com/kmmelissat/devops-metricas/actions/runs/41774548688).

Capturas por tomar, en [evidencias/](../evidencias):

1. `DEV-08-pr-plan.png`: jobs `validate` y `plan` de un PR, sin job `apply`.
2. `DEV-08-plan-resumen.png`: el resumen del `plan`.
3. `DEV-08-apply-aprobacion.png`: el job `apply` esperando la aprobación del entorno `infra`.
