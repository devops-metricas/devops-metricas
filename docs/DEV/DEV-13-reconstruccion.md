# Reconstrucción, apagado y destrucción del ambiente

Cubre DEV-13 (reconstruir desde una suscripción autorizada) y el procedimiento de detención y
eliminación de DEV-14. Todo lo que no está en la sección "Intervenciones manuales" se hace con
código versionado y el pipeline.

## 1. Prerrequisitos

| Qué | Para qué |
|---|---|
| Suscripción Azure for Students con rol **Owner** para quien ejecuta el bootstrap | Crear identidades y asignar roles |
| `az` (Azure CLI) con `az login` | Bootstrap |
| `gh` (GitHub CLI) con sesión en la cuenta dueña del repo | El bootstrap lee el subject OIDC del repo |
| Un par de claves SSH (`ssh-keygen -t ed25519 -f ~/.ssh/notifier_azure`) | Administrar la VM |
| Repositorio en GitHub con los entornos `infra`, `dev` y `prod` | Aprobaciones (requieren repo público o plan de pago) |

La suscripción solo permite las regiones `northcentralus`, `brazilsouth`, `norwayeast`, `westus` y
`francecentral`. Se usa `northcentralus` y la VM `Standard_B2as_v2` (2 vCPU, 8 GB), disponible allí.

## 2. Intervenciones manuales (declaradas, 5.6 del enunciado)

Son las únicas, y no sustituyen el aprovisionamiento normal:

1. **Bootstrap, una sola vez** (identidades y almacenamiento del estado, imposibles de crear
   desde un pipeline que aún no tiene identidad):
   ```bash
   SUBSCRIPTION_ID=<id> GITHUB_REPO=<owner/repo> ./infra/bootstrap/bootstrap.sh
   ```
   Es idempotente. Registra los proveedores de recursos, crea la cuenta de almacenamiento del estado
   (sin llaves, con versionado) y tres identidades OIDC: `infra` (Contributor, solo desde `main` y el
   entorno `infra`), `plan` (Reader, para pull requests) y `deploy` (Virtual Machine Contributor).
2. **Configuración de GitHub** con los valores que imprime el bootstrap:
   - Variables: `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_INFRA_CLIENT_ID`,
     `AZURE_PLAN_CLIENT_ID`, `AZURE_DEPLOY_CLIENT_ID`, `TFSTATE_RESOURCE_GROUP`,
     `TFSTATE_STORAGE_ACCOUNT`, `TFSTATE_CONTAINER`, `TF_DNS_LABEL`, `TF_SSH_PUBLIC_KEY`,
     `TF_BUDGET_START_DATE`.
   - Secrets (datos personales; GitHub los enmascara en logs públicos): `TF_ADMIN_CIDR`
     (IP pública autorizada para SSH, `/32`) y `TF_ALERT_EMAILS` (lista JSON de correos).
   - Entornos `infra`, `dev`, `prod`; `infra` y `prod` con aprobador requerido.
   - Protección de `main`: PR obligatorio con aprobación.

Ningún secreto vive en el repositorio. Con OIDC no existe contraseña que guardar.

## 3. Crear la infraestructura

Por pull request (flujo normal): un cambio en `infra/terraform/**` ejecuta `plan` en el PR; al unir
a `main`, el job `apply` espera la aprobación del entorno `infra`.

Sin cambios de código (por ejemplo, tras una destrucción): *Actions → Infra ops → Run workflow →
action = `apply`*. También exige aprobación del entorno `infra`.

La VM instala K3s sola en el primer arranque (cloud-init, con cifrado de secretos activado). Para
verificar:

```bash
ssh -i ~/.ssh/notifier_azure azureuser@<TF_DNS_LABEL>.northcentralus.cloudapp.azure.com
cloud-init status --wait          # espera a que termine la instalación
sudo k3s kubectl get nodes        # el nodo debe estar Ready
sudo k3s kubectl get pods -A
```

La API de Kubernetes (6443) no está expuesta: el firewall solo abre 80, 443 y SSH desde la IP
autorizada. Si cambia la IP de quien administra, se actualiza el secret `TF_ADMIN_CIDR` y se aplica.

## 4. Apagar, encender y destruir (control de costos)

Todo desde *Actions → Infra ops → Run workflow* (solo desde `main`):

| Acción | Efecto | Aprobación |
|---|---|---|
| `deallocate` | Apaga y desasigna la VM: **deja de cobrarse el cómputo**. El disco y la IP pública siguen cobrando. | No |
| `start` | Enciende la VM. K3s y los Pods arrancan solos; los datos persisten en el disco. | No |
| `apply` | Crea o actualiza la infraestructura. | Entorno `infra` |
| `destroy` | Elimina toda la infraestructura de Terraform. Exige escribir `DESTRUIR`. | Entorno `infra` |

Reglas del equipo: **apagar la VM al terminar cada sesión**. Además, la VM se apaga sola cada noche
(`shutdown_time`, 23:00 hora de América Central), pero ese apagado automático no sustituye lo anterior.

Las alertas de presupuesto (50, 80 y 100 % de US$100) solo envían correo: **no detienen nada por sí
mismas**. Por eso el apagado es manual y está documentado aquí.

Tras `destroy` los datos de PostgreSQL se pierden. Un rollback de Deployment tampoco restaura datos.

## 5. Limpieza total (fin del proyecto)

`destroy` no elimina lo que creó el bootstrap. Para dejar la suscripción sin cargos:

```bash
az group delete -n rg-notifier-tfstate --yes        # estado remoto
for app in sp-notifier-infra sp-notifier-plan sp-notifier-deploy; do
  az ad app delete --id "$(az ad app list --display-name "$app" --query '[0].appId' -o tsv)"
done
```

## 6. Evidencia

Hecho:

- `plan` revisado: [DEV-06-plan.png](../evidencias/DEV-06-plan.png).
- `apply` aprobado: [DEV-06-apply.png](../evidencias/DEV-06-apply.png).

Pendiente:

- Salida de `kubectl get nodes` con el nodo en `Ready`.
- Cargos observados en *Cost Management* tras la primera semana (alimenta `DEV-14-costos.md`).
- Prueba de reconstrucción completa: `destroy` seguido de `apply`, con el tiempo que tarda.
