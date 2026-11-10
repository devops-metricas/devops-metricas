#!/usr/bin/env bash
# Despliega Prometheus y Grafana en el namespace monitoring.
# El manifiesto se renderiza aquí y se aplica DENTRO de la VM con `az vm run-command`
# (sin SSH ni puertos abiertos). run-command no propaga el código de salida: se exige MONITOREO_OK.
#
#   RESOURCE_GROUP=rg-notifier VM_NAME=vm-notifier FQDN=<dns> GRAFANA_ADMIN_PASSWORD=<clave> ./scripts/desplegar-monitoreo.sh
#
# Requiere: az con sesión iniciada, kustomize y curl.
# No usar set -x: la contraseña no debe aparecer en la traza ni en la salida.

set -euo pipefail

: "${RESOURCE_GROUP:?falta RESOURCE_GROUP}" "${VM_NAME:?falta VM_NAME}" "${FQDN:?falta FQDN}" \
  "${GRAFANA_ADMIN_PASSWORD:?falta GRAFANA_ADMIN_PASSWORD}"
case "$FQDN" in
  *[!A-Za-z0-9.-]*) echo "FQDN inválido." >&2; exit 1 ;;
esac
[ "${#GRAFANA_ADMIN_PASSWORD}" -ge 24 ] || { echo "GRAFANA_ADMIN_PASSWORD debe tener al menos 24 caracteres." >&2; exit 1; }
command -v az >/dev/null && command -v kustomize >/dev/null && command -v curl >/dev/null \
  || { echo "Se necesita az, kustomize y curl." >&2; exit 1; }

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo ">> Renderizando el monitoreo"
kustomize build "$RAIZ/k8s/monitoring" --load-restrictor LoadRestrictionsNone \
  | sed "s/REPLACE_FQDN/$FQDN/g" > "$TMP/manifiesto.yaml"
if grep -q REPLACE_FQDN "$TMP/manifiesto.yaml"; then
  echo "El manifiesto todavía contiene REPLACE_FQDN." >&2
  exit 1
fi

MANIFIESTO_B64="$(base64 < "$TMP/manifiesto.yaml" | tr -d '\n')"
if [ "${#MANIFIESTO_B64}" -ge 200000 ]; then
  echo "El manifiesto en base64 pesa ${#MANIFIESTO_B64} bytes; run-command admite menos de 200000." >&2
  exit 1
fi
PASS_B64="$(printf '%s' "$GRAFANA_ADMIN_PASSWORD" | base64 | tr -d '\n')"

# Script que corre en la VM (como root). La contraseña viaja en base64 y no se imprime.
{
  echo 'set -eu'
  echo 'k3s kubectl create namespace monitoring --dry-run=client -o yaml | k3s kubectl apply -f - >/dev/null'
  echo "PASS=\$(printf '%s' '$PASS_B64' | base64 -d)"
  echo 'pf=$(mktemp)'
  echo 'chmod 600 "$pf"'
  echo 'printf %s "$PASS" > "$pf"'
  echo 'unset PASS'
  echo 'k3s kubectl -n monitoring create secret generic grafana-admin \'
  echo '  --from-file=password="$pf" \'
  echo '  --dry-run=client -o yaml | k3s kubectl apply -f - >/dev/null'
  echo 'rm -f "$pf"'
  echo "printf '%s' '$MANIFIESTO_B64' | base64 -d | k3s kubectl apply -f -"
  # Grafana solo lee la contraseña al arrancar.
  echo 'k3s kubectl -n monitoring rollout restart deploy/grafana >/dev/null'
  echo 'k3s kubectl -n monitoring rollout status deploy/prometheus --timeout=240s'
  echo 'k3s kubectl -n monitoring rollout status deploy/grafana --timeout=240s'
  echo 'k3s kubectl -n monitoring get pods'
  echo 'echo MONITOREO_OK'
} > "$TMP/en-la-vm.sh"

echo ">> Aplicando en la VM $VM_NAME"
SALIDA="$(az vm run-command invoke -g "$RESOURCE_GROUP" -n "$VM_NAME" --command-id RunShellScript \
  --scripts @"$TMP/en-la-vm.sh" --query 'value[0].message' -o tsv)"
# Solo líneas de estado; nunca el script ni la contraseña (ni su base64).
grep -E 'deployment "|Waiting for deployment|exceeded its progress deadline|^NAME[[:space:]]|^prometheus-|^grafana-|^MONITOREO_OK$' <<<"$SALIDA" \
  | grep -v -F -e "$GRAFANA_ADMIN_PASSWORD" -e "$PASS_B64" || true
grep -q MONITOREO_OK <<<"$SALIDA" || { echo "El despliegue del monitoreo falló." >&2; exit 1; }

echo ">> Comprobando https://$FQDN/grafana/api/health"
curl -fsS --retry 12 --retry-delay 10 --retry-all-errors "https://$FQDN/grafana/api/health"
echo
echo "Monitoreo desplegado: https://$FQDN/grafana"
