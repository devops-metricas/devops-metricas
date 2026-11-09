# DEV-10: Separar configuración y secretos de las imágenes; aplicar privilegio mínimo.

> **Cubierto.**

| | |
|---|---|
| **Responsable** | Diego |
| **Estado** | Cubierto |
| **Evidencia mínima que se revisa** | Mecanismos de configuración y evidencia de permisos. |

## Qué hay y qué falta

**Configuración fuera de la imagen.** Los valores no secretos van en el ConfigMap `notifier-config`
(`configMapGenerator` en [k8s/base/kustomization.yaml](../../k8s/base/kustomization.yaml)); cada overlay añade
`NOTIFIER_ENVIRONMENT`. Los pods lo leen con `envFrom`.

**Secretos fuera de la imagen y del repo.** `api`, `worker` y `postgres` leen `database-url` y
`postgres-password` del Secret `notifier-secrets` (con `secretKeyRef`), que **no está versionado**. Lo crea
[scripts/crear-secretos.sh](../../scripts/crear-secretos.sh): genera una contraseña distinta por entorno, arma
`database-url`, aplica el Secret dentro de la VM con `az vm run-command`, no imprime valores y no pisa un Secret
existente (cambiar la contraseña sin cambiarla en PostgreSQL dejaría a la API sin acceso). Se lanza desde Actions con
el workflow [crear-secretos.yml](../../.github/workflows/crear-secretos.yml) (entorno `dev` o `prod`), que usa la
identidad `sp-notifier-deploy`; no hace falta una cuenta de Azure personal.

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

Estado del clúster el 2026-11-09 (00:46 UTC), sin mostrar ningún valor secreto:

```
== notifier-dev                          == notifier-prod
notifier-secrets: database-url            notifier-secrets: database-url
                  postgres-password                         postgres-password
notifier-secrets   Opaque   2 claves      notifier-secrets   Opaque   2 claves

ConfigMap (no secreto)                    ConfigMap (no secreto)
  NOTIFIER_ENVIRONMENT=dev                  NOTIFIER_ENVIRONMENT=prod
  NOTIFIER_MAX_ATTEMPTS=3                   NOTIFIER_MAX_ATTEMPTS=3
  NOTIFIER_RETRY_BACKOFF_SECONDS=5          NOTIFIER_RETRY_BACKOFF_SECONDS=5
  NOTIFIER_SMTP_HOST=mailpit                NOTIFIER_SMTP_HOST=mailpit
  NOTIFIER_SMTP_PORT=1025                   NOTIFIER_SMTP_PORT=1025
  NOTIFIER_EMAIL_FAULT_RATE=0               NOTIFIER_EMAIL_FAULT_RATE=0
  NOTIFIER_EMAIL_FAULT_KIND=503             NOTIFIER_EMAIL_FAULT_KIND=503

Pod api, variable sensible              Pod api, variable sensible
  NOTIFIER_DATABASE_URL                   NOTIFIER_DATABASE_URL
    <- secret notifier-secrets/database-url   <- secret notifier-secrets/database-url
  envFrom: ConfigMap notifier-config-…      envFrom: ConfigMap notifier-config-…
```

- La contraseña es distinta en cada entorno: el script genera una por namespace.
- En la definición del Deployment de `api` en prod no aparecen `postgresql://` ni `password:`: los valores
  viven solo en el Secret, nunca en el manifiesto del repo.
- **Secrets creados con el workflow** en dev: [ejecución de Crear secretos](https://github.com/devops-metricas/devops-metricas/actions/runs/42525062315)
  (`notifier-dev: notifier-secrets creado`, sin ningún valor en el log). Los de prod se crearon con el mismo
  `scripts/crear-secretos.sh`, ejecutado desde una sesión de Azure con rol Contributor sobre `rg-notifier`.
- **Permisos mínimos**: la tabla de arriba. Cada identidad de Azure acepta tokens solo de los entornos o ramas
  necesarios (credenciales federadas), y el despliegue usa una identidad que no puede cambiar la infraestructura.

**Límites**: los Secrets de Kubernetes se guardan en base64 dentro de etcd; K3s se instala con
`--secrets-encryption`, así que se cifran en reposo, pero cualquiera con acceso de administrador a la VM puede
leerlos. Para este alcance es suficiente; un gestor externo de secretos sería el siguiente paso.
