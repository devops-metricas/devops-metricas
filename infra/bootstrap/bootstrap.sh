#!/usr/bin/env bash
# Bootstrap ÚNICO y manual (5.6 del enunciado): crea lo que Terraform necesita para existir.
#   1. Cuenta de almacenamiento para el estado remoto (sin llaves de acceso, con versionado).
#   2. Tres identidades de Entra ID con credenciales federadas para GitHub (OIDC, sin contraseñas):
#        - infra  : apply de Terraform (main y entorno infra). Contributor en la suscripción.
#        - plan   : plan en pull requests. Solo Reader: un PR puede editar el workflow.
#        - deploy : despliegues. Solo "Virtual Machine Contributor" (az vm run-command).
#
# Requisitos: az CLI con sesión iniciada (`az login`) por alguien con rol Owner en la suscripción.
# Es idempotente: se puede repetir sin duplicar nada.
#
#   SUBSCRIPTION_ID=... GITHUB_REPO=owner/repo ./infra/bootstrap/bootstrap.sh

set -euo pipefail

: "${SUBSCRIPTION_ID:?falta SUBSCRIPTION_ID}"
: "${GITHUB_REPO:?falta GITHUB_REPO (formato owner/repo)}"
case "$GITHUB_REPO" in
  owner/repo | */ | /* | "") echo "GITHUB_REPO debe ser el repo real (usuario/nombre), no el ejemplo." >&2; exit 1 ;;
esac
LOCATION="${LOCATION:-northcentralus}" # la política de la suscripción solo permite 5 regiones
STATE_RG="${STATE_RG:-rg-notifier-tfstate}"
# Nombre global único y determinista (3-24 caracteres, minúsculas y números).
STATE_SA="${STATE_SA:-stnotif$(printf '%s' "$SUBSCRIPTION_ID" | shasum | cut -c1-10)}"
STATE_CONTAINER="tfstate"
SCOPE="/subscriptions/$SUBSCRIPTION_ID"

az account set --subscription "$SUBSCRIPTION_ID"
TENANT_ID=$(az account show --query tenantId -o tsv)

# En Azure for Students estos proveedores vienen sin registrar y la creación de la VM falla.
echo ">> Registrando proveedores de recursos"
for ns in Microsoft.Compute Microsoft.Network Microsoft.Storage Microsoft.DevTestLab \
          Microsoft.Consumption Microsoft.CostManagement; do
  az provider register --namespace "$ns" --wait
done

echo ">> Estado remoto: $STATE_SA en $STATE_RG"
az group create -n "$STATE_RG" -l "$LOCATION" -o none
az storage account create -n "$STATE_SA" -g "$STATE_RG" -l "$LOCATION" \
  --sku Standard_LRS --kind StorageV2 --min-tls-version TLS1_2 \
  --allow-blob-public-access false --allow-shared-key-access false -o none
az storage account blob-service-properties update --account-name "$STATE_SA" -g "$STATE_RG" \
  --enable-versioning true -o none
SA_ID=$(az storage account show -n "$STATE_SA" -g "$STATE_RG" --query id -o tsv)

# Quien ejecuta este script necesita datos de blob para crear el contenedor (sin llaves).
ME=$(az ad signed-in-user show --query id -o tsv)
az role assignment create --assignee-object-id "$ME" --assignee-principal-type User \
  --role "Storage Blob Data Contributor" --scope "$SA_ID" -o none
for i in 1 2 3 4 5 6 7 8 9 10; do
  if az storage container create --account-name "$STATE_SA" -n "$STATE_CONTAINER" \
      --auth-mode login -o none 2>/dev/null; then break; fi
  echo "   esperando que el rol se propague ($i/10)..."; sleep 15
done

ensure_app() { # nombre -> imprime el appId
  local id
  id=$(az ad app list --display-name "$1" --query '[0].appId' -o tsv)
  [ -n "$id" ] || id=$(az ad app create --display-name "$1" --query appId -o tsv)
  az ad sp show --id "$id" >/dev/null 2>&1 || az ad sp create --id "$id" -o none
  echo "$id"
}

ensure_fic() { # appId nombre subject
  local current
  current=$(az ad app federated-credential list --id "$1" --query "[?name=='$2'].subject | [0]" -o tsv)
  [ "$current" = "$3" ] && return 0
  # Si existe con otro subject (p. ej. se corrió con un repo equivocado), se reemplaza.
  if [ -n "$current" ]; then
    az ad app federated-credential delete --id "$1" --federated-credential-id "$2" -o none
  fi
  az ad app federated-credential create --id "$1" -o none --parameters "{
    \"name\": \"$2\",
    \"issuer\": \"https://token.actions.githubusercontent.com\",
    \"subject\": \"$3\",
    \"audiences\": [\"api://AzureADTokenExchange\"]}"
}

assign() { # appId rol scope
  local oid
  oid=$(az ad sp show --id "$1" --query id -o tsv)
  az role assignment create --assignee-object-id "$oid" --assignee-principal-type ServicePrincipal \
    --role "$2" --scope "$3" -o none
}

echo ">> Identidad de infraestructura (Terraform)"
INFRA_ID=$(ensure_app "sp-notifier-infra")
ensure_fic "$INFRA_ID" gh-main "repo:$GITHUB_REPO:ref:refs/heads/main"
ensure_fic "$INFRA_ID" gh-env-infra "repo:$GITHUB_REPO:environment:infra"
assign "$INFRA_ID" "Contributor" "$SCOPE"
assign "$INFRA_ID" "Storage Blob Data Contributor" "$SA_ID"
# Esta identidad ya NO acepta tokens de pull_request (un PR puede modificar el workflow).
if [ -n "$(az ad app federated-credential list --id "$INFRA_ID" --query "[?name=='gh-pr'].name" -o tsv)" ]; then
  az ad app federated-credential delete --id "$INFRA_ID" --federated-credential-id gh-pr -o none
fi

echo ">> Identidad de solo lectura para el plan de los pull requests"
PLAN_ID=$(ensure_app "sp-notifier-plan")
ensure_fic "$PLAN_ID" gh-pr "repo:$GITHUB_REPO:pull_request"
assign "$PLAN_ID" "Reader" "$SCOPE"
assign "$PLAN_ID" "Storage Blob Data Contributor" "$SA_ID" # tomar el candado del estado

echo ">> Identidad de despliegue"
DEPLOY_ID=$(ensure_app "sp-notifier-deploy")
ensure_fic "$DEPLOY_ID" gh-env-dev "repo:$GITHUB_REPO:environment:dev"
ensure_fic "$DEPLOY_ID" gh-env-prod "repo:$GITHUB_REPO:environment:prod"
assign "$DEPLOY_ID" "Virtual Machine Contributor" "$SCOPE"

cat <<EOF

==================== Listo ====================
Variables del repositorio en GitHub (Settings > Secrets and variables > Actions > Variables).
No son secretos: con OIDC no existe ninguna contraseña que guardar.

  AZURE_TENANT_ID           = $TENANT_ID
  AZURE_SUBSCRIPTION_ID     = $SUBSCRIPTION_ID
  AZURE_INFRA_CLIENT_ID     = $INFRA_ID      (apply de Terraform: Contributor)
  AZURE_PLAN_CLIENT_ID      = $PLAN_ID       (plan en pull requests: solo lectura)
  AZURE_DEPLOY_CLIENT_ID    = $DEPLOY_ID     (workflow de entrega y rollback)
  TFSTATE_RESOURCE_GROUP    = $STATE_RG
  TFSTATE_STORAGE_ACCOUNT   = $STATE_SA
  TFSTATE_CONTAINER         = $STATE_CONTAINER

Contenido para infra/terraform/backend.hcl (uso local):
  resource_group_name  = "$STATE_RG"
  storage_account_name = "$STATE_SA"
  container_name       = "$STATE_CONTAINER"
  key                  = "notifier.tfstate"
  use_azuread_auth     = true

Entornos de GitHub a crear (Settings > Environments): infra, dev, prod.
Con aprobadores requeridos en infra y prod.
EOF
