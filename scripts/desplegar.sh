#!/usr/bin/env bash
# Despliega un entorno (dev o prod) con la imagen de un commit (DEV-05, DEV-12).
# La API de Kubernetes (6443) no es alcanzable desde Internet: el manifiesto se renderiza aquí y se
# aplica DENTRO de la VM con `az vm run-command` (sin SSH ni puertos abiertos).
#
#   RESOURCE_GROUP=rg-notifier VM_NAME=vm-notifier FQDN=<dns-publico> \
#     ./scripts/desplegar.sh <dev|prod> <sha-de-40-caracteres>
#
# Requiere: az con sesión iniciada, kustomize y curl. Rollback = volver a ejecutarlo con un SHA anterior.

set -euo pipefail

ENTORNO="${1:?uso: desplegar.sh <dev|prod> <sha>}"
SHA="${2:?uso: desplegar.sh <dev|prod> <sha>}"
: "${RESOURCE_GROUP:?falta RESOURCE_GROUP}" "${VM_NAME:?falta VM_NAME}" "${FQDN:?falta FQDN}"

case "$ENTORNO" in dev | prod) ;; *) echo "Entorno inválido: $ENTORNO" >&2; exit 1 ;; esac
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "El SHA debe ser el commit completo (40 hex)." >&2; exit 1; }

NS="notifier-$ENTORNO"
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo ">> Renderizando $ENTORNO con la imagen $SHA"
cp -R "$RAIZ/k8s" "$TMP/k8s" # kustomize edit modifica el overlay: se trabaja sobre una copia
(cd "$TMP/k8s/overlays/$ENTORNO" && kustomize edit set image "ghcr.io/kmmelissat/notifier:$SHA")
kustomize build "$TMP/k8s/overlays/$ENTORNO" | sed "s/REPLACE_FQDN/$FQDN/g" > "$TMP/manifiesto.yaml"
grep -q "ghcr.io/kmmelissat/notifier:$SHA" "$TMP/manifiesto.yaml" || { echo "El manifiesto no usa el SHA pedido." >&2; exit 1; }

# Script que corre en la VM (como root). run-command no propaga el código de salida: se exige la marca final.
{
  echo 'set -eu'
  echo "echo '$(base64 < "$TMP/manifiesto.yaml" | tr -d '\n')' | base64 -d | k3s kubectl apply -f -"
  echo "k3s kubectl -n $NS rollout status deploy/api --timeout=180s"
  echo "k3s kubectl -n $NS rollout status deploy/worker --timeout=180s"
  echo "echo DESPLIEGUE_OK"
} > "$TMP/en-la-vm.sh"

echo ">> Aplicando en la VM $VM_NAME"
SALIDA="$(az vm run-command invoke -g "$RESOURCE_GROUP" -n "$VM_NAME" --command-id RunShellScript \
  --scripts @"$TMP/en-la-vm.sh" --query 'value[0].message' -o tsv)"
echo "$SALIDA"
grep -q DESPLIEGUE_OK <<<"$SALIDA" || { echo "El despliegue de $ENTORNO falló." >&2; exit 1; }

echo ">> Comprobando https://$FQDN/$ENTORNO/readyz"
curl -fsS --retry 12 --retry-delay 10 --retry-all-errors "https://$FQDN/$ENTORNO/readyz"
echo
echo "Desplegado $ENTORNO: ghcr.io/kmmelissat/notifier:$SHA"
