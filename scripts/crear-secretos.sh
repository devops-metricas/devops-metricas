#!/usr/bin/env bash
# Crea el Secret notifier-secrets en cada namespace (DEV-10). Lo ejecuta una persona, una vez por
# reconstrucción del clúster, con la VM encendida. Los valores se generan aquí y NUNCA se versionan ni se imprimen.
#
#   RESOURCE_GROUP=rg-notifier VM_NAME=vm-notifier ./scripts/crear-secretos.sh [dev] [prod]
#
# Requiere: az con sesión iniciada (rol sobre la VM) y openssl. Sin argumentos crea dev y prod.
# Si el Secret ya existe NO se toca: cambiar postgres-password sin cambiar la clave dentro de la base
# dejaría a la API sin acceso. Para rotarlo a propósito: FORZAR=1.
#
# Nota: el script viaja a la VM por az vm run-command, que guarda una copia en la VM (solo root la lee).
# La contraseña es de uso interno del clúster (PostgreSQL no está expuesto) y distinta en cada entorno.

set -euo pipefail

: "${RESOURCE_GROUP:?falta RESOURCE_GROUP}" "${VM_NAME:?falta VM_NAME}"
ENTORNOS=("$@")
[ ${#ENTORNOS[@]} -gt 0 ] || ENTORNOS=(dev prod)
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

{
  echo 'set -eu'
  echo "FORZAR=${FORZAR:-}"
  for e in "${ENTORNOS[@]}"; do
    case "$e" in dev | prod) ;; *) echo "Entorno inválido: $e" >&2; exit 1 ;; esac
    ns="notifier-$e"
    pass="$(openssl rand -hex 24)"
    echo "k3s kubectl create namespace $ns --dry-run=client -o yaml | k3s kubectl apply -f - >/dev/null"
    echo "if k3s kubectl -n $ns get secret notifier-secrets >/dev/null 2>&1 && [ \"\$FORZAR\" != 1 ]; then"
    echo "  echo '$ns: notifier-secrets ya existe, no se modifica'"
    echo "else"
    echo "  k3s kubectl -n $ns create secret generic notifier-secrets \\"
    echo "    --from-literal=postgres-password='$pass' \\"
    echo "    --from-literal=database-url='postgresql://notifier:$pass@postgres:5432/notifier' \\"
    echo "    --dry-run=client -o yaml | k3s kubectl apply -f - >/dev/null"
    echo "  echo '$ns: notifier-secrets creado'"
    echo "fi"
  done
  echo "echo SECRETOS_OK"
} > "$TMP/en-la-vm.sh"

SALIDA="$(az vm run-command invoke -g "$RESOURCE_GROUP" -n "$VM_NAME" --command-id RunShellScript \
  --scripts @"$TMP/en-la-vm.sh" --query 'value[0].message' -o tsv)"
# Solo se muestran las líneas de estado; nunca el script ni los valores.
grep -E "notifier-secrets|SECRETOS_OK" <<<"$SALIDA" || true
grep -q SECRETOS_OK <<<"$SALIDA" || { echo "No se pudieron crear los secretos." >&2; exit 1; }
