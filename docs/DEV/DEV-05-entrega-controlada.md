# DEV-05: Automatizar una entrega controlada, separando validación y producción de forma lógica.

> **Pendiente por Diego: workflow en `main`, falta la demostración.**

| | |
|---|---|
| **Responsable** | Diego |
| **Estado** | Pendiente |
| **Evidencia mínima que se revisa** | Workflow, controles de aprobación y demostración de despliegue. |

## Qué hay y qué falta

[entrega.yml](../../.github/workflows/entrega.yml) y [desplegar.sh](../../scripts/desplegar.sh):

- Al terminar `Publicar imagen` en `main`, despliega a **dev** (environment `dev`, sin aprobación).
- **prod** va después y espera la aprobación del environment `prod` (revisora: `kmmelissat`).
- Despliega la imagen `ghcr.io/kmmelissat/notifier:<sha>` del commit; nunca `latest`.
- El manifiesto se aplica dentro de la VM con `az vm run-command`, porque la API de Kubernetes (6443) no
  se expone. Identidad OIDC `sp-notifier-deploy`, solo Virtual Machine Contributor.
- Tras aplicar espera el rollout de `api` y `worker` y comprueba `/readyz` por HTTPS.
- También se lanza a mano con un SHA (`workflow_dispatch`), que es la vía de rollback ([DEV-12](DEV-12-rollback.md)).

La primera ejecución automática falló en el renderizado: la etiqueta del SHA no se aplicaba (corregido en el PR #20).

Falta: una ejecución completa, que necesita `notifier-secrets` ([DEV-10](DEV-10-configuracion-y-secretos.md)), la VM
encendida y el PR #20 mergeado.

## Evidencia

Pendiente de enlazar: ejecución a dev, pausa de aprobación de prod y despliegue a prod. Guardar las capturas en [evidencias/](../evidencias) con el prefijo `DEV-05-`.
