#!/usr/bin/env bash
# Instala o actualiza el colector OpenTelemetry y Jaeger (k8s/observability) en la VM (MET-04).
# Mismo mecanismo que desplegar.sh: se renderiza aquí y se aplica dentro de la VM con run-command.
#
#   RESOURCE_GROUP=rg-notifier VM_NAME=vm-notifier ./scripts/aplicar-observabilidad.sh
#
# Requiere: az con sesión iniciada y kustomize. Para quitarlo: k3s kubectl delete ns observability.

set -euo pipefail
: "${RESOURCE_GROUP:?falta RESOURCE_GROUP}" "${VM_NAME:?falta VM_NAME}"

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
MANIFIESTO="$(kustomize build "$RAIZ/k8s/observability" | base64 | tr -d '\n')"

SCRIPT="set -eu
echo '$MANIFIESTO' | base64 -d | k3s kubectl apply -f -
k3s kubectl -n observability rollout status deploy/otel-collector --timeout=180s
k3s kubectl -n observability rollout status deploy/jaeger --timeout=180s
k3s kubectl -n observability get pods -o wide
echo OBSERVABILIDAD_OK"

SALIDA="$(az vm run-command invoke -g "$RESOURCE_GROUP" -n "$VM_NAME" --command-id RunShellScript \
  --scripts "$SCRIPT" --query 'value[0].message' -o tsv)"
echo "$SALIDA"
grep -q OBSERVABILIDAD_OK <<<"$SALIDA" || { echo "La instalación falló." >&2; exit 1; }
