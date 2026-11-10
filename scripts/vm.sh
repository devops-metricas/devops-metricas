#!/usr/bin/env bash
# Ejecuta un comando dentro de la VM de K3s con `az vm run-command` (sin SSH ni puerto 6443).
# Pensado para MET-02, MET-04 y MET-07: leer logs, consultar trazas y cambiar la inyección de fallas.
#
#   RESOURCE_GROUP=rg-notifier VM_NAME=vm-notifier ./scripts/vm.sh "k3s kubectl get pods -A"
#
# Requiere: az con sesión iniciada. run-command tarda ~20-40 s por llamada.

set -euo pipefail
: "${RESOURCE_GROUP:?falta RESOURCE_GROUP}" "${VM_NAME:?falta VM_NAME}"
CMD="${1:?uso: vm.sh \"<comando>\"}"

az vm run-command invoke -g "$RESOURCE_GROUP" -n "$VM_NAME" --command-id RunShellScript \
  --scripts "$CMD" --query 'value[0].message' -o tsv
