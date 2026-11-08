# DEV-10: Separar configuración y secretos de las imágenes; aplicar privilegio mínimo.

> **Pendiente por Diego: faltan los secrets de Kubernetes y las capturas.**

| | |
|---|---|
| **Responsable** | Diego |
| **Estado** | Pendiente |
| **Evidencia mínima que se revisa** | Mecanismos de configuración y evidencia de permisos. |

## Qué hay y qué falta

**Configuración fuera de la imagen.** Los valores no secretos van en el ConfigMap `notifier-config`
(`configMapGenerator` en [k8s/base/kustomization.yaml](../../k8s/base/kustomization.yaml)); cada overlay añade
`NOTIFIER_ENVIRONMENT`. Los pods lo leen con `envFrom`.

**Secretos fuera de la imagen y del repo.** `api`, `worker` y `postgres` leen `database-url` y
`postgres-password` del Secret `notifier-secrets`, que **no está versionado**. **Falta crearlo** en
`notifier-dev` y `notifier-prod`; mientras no exista, los pods no arrancan. Lo crea
[scripts/crear-secretos.sh](../../scripts/crear-secretos.sh): genera una contraseña distinta por entorno, arma
`database-url`, aplica el Secret dentro de la VM con `az vm run-command`, no imprime valores y no pisa un Secret
existente (cambiar la contraseña sin cambiarla en PostgreSQL dejaría a la API sin acceso). Sin ejecutar todavía.

**Permisos mínimos de los pipelines** (revisados):

| Workflow | Permisos del `GITHUB_TOKEN` | Identidad en Azure |
|---|---|---|
| `ci.yml` | `contents: read` | Ninguna |
| `publicar-imagen.yml` | `contents: read`, `packages: write` | Ninguna; sube a GHCR con el `GITHUB_TOKEN` |
| `terraform.yml` | `contents: read`; `id-token: write` solo en `plan` y `apply` | PR: `sp-notifier-plan` (Reader). `main`: `sp-notifier-infra` (Contributor, entorno `infra`) |
| `infra-ops.yml` | `contents: read`, `id-token: write` | `sp-notifier-infra`; `apply` y `destroy` exigen el entorno `infra` |
| `entrega.yml` | `contents: read`, `id-token: write` | `sp-notifier-deploy`, solo Virtual Machine Contributor; `prod` exige aprobación |

No hay contraseñas guardadas: Azure se autentica por OIDC y GHCR con el `GITHUB_TOKEN`. La IP de
administración y los correos son *secrets* de GitHub, no variables.

## Evidencia

Pendiente de enlazar. Guardar las capturas en [evidencias/](../evidencias) con el prefijo `DEV-10-`
(`kubectl get secret` sin mostrar valores, y el ConfigMap).
