#!/usr/bin/env bash
# Comprueba que Prometheus, dentro de la VM, ya ve la API, el worker y cAdvisor,
# y que las dos reglas de alerta están cargadas. run-command no propaga el código
# de salida: se exige la marca VERIFICACION_OK.
#
#   RESOURCE_GROUP=rg-notifier VM_NAME=vm-notifier FQDN=<dns> ./scripts/verificar-monitoreo.sh
#
# Requiere: az con sesión iniciada. En la VM no se asume jq ni python.
# No imprime secretos.

set -euo pipefail

: "${RESOURCE_GROUP:?falta RESOURCE_GROUP}" "${VM_NAME:?falta VM_NAME}" "${FQDN:?falta FQDN}"
case "$FQDN" in
  *[!A-Za-z0-9.-]*) echo "FQDN inválido." >&2; exit 1 ;;
esac
command -v az >/dev/null || { echo "Se necesita az." >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# El bucle corre en la VM: hasta 120 s, con 10 s entre intentos, porque el primer
# scrape puede tardar. Se parsea el JSON con grep y sed.
cat > "$TMP/en-la-vm.sh" << 'EOF'
set -eu

consultar() {
  k3s kubectl -n monitoring exec deploy/prometheus -- wget -qO- "$1" 2>/dev/null || true
}

campo() {
  printf '%s' "$1" | sed -n 's/.*"'"$2"'":"\([^"]*\)".*/\1/p'
}

valor_de() {
  printf '%s' "$1" | sed -n 's/.*"value":\[[^]]*,"\([^"]*\)".*/\1/p'
}

# Una línea por serie. Con prefijo "up" actualiza las banderas api_ok, worker_ok y cadvisor_ok.
volcar() {
  prefijo="$1"
  cuerpo="$2"
  hay=0
  tmp=$(mktemp)
  printf '%s\n' "$cuerpo" | sed 's/{"metric":/\n&/g' | grep '^{"metric":' > "$tmp" || true
  while IFS= read -r linea || [ -n "$linea" ]; do
    [ -n "$linea" ] || continue
    hay=1
    job=$(campo "$linea" job)
    environment=$(campo "$linea" environment)
    namespace=$(campo "$linea" namespace)
    pod=$(campo "$linea" pod)
    valor=$(valor_de "$linea")
    if [ "$prefijo" = "up" ]; then
      echo "up job=${job:--} environment=${environment:--} namespace=${namespace:--} pod=${pod:--} valor=${valor:--}"
      if [ "$job" = "notifier-api" ] && [ "$namespace" = "notifier-dev" ] && [ "$valor" = "1" ]; then
        api_ok=1
      fi
      if [ "$job" = "notifier-worker" ] && [ "$namespace" = "notifier-dev" ] && [ "$valor" = "1" ]; then
        worker_ok=1
      fi
      if [ "$job" = "kubelet-cadvisor" ] && [ "$valor" = "1" ]; then
        cadvisor_ok=1
      fi
    else
      echo "$prefijo namespace=${namespace:--} valor=${valor:--}"
    fi
  done < "$tmp"
  rm -f "$tmp"
  if [ "$hay" != 1 ]; then
    echo "$prefijo sin-series"
  fi
}

estado_regla() {
  nombre="$1"
  if ! printf '%s' "$reglas" | grep -q "\"name\":\"$nombre\""; then
    return 1
  fi
  # Prometheus 2.55 pone "state" justo antes de "name". Si no, se toma el primer state posterior.
  estado=$(printf '%s' "$reglas" | sed -n 's/.*"state":"\([^"]*\)","name":"'"$nombre"'".*/\1/p' | head -n 1)
  if [ -z "$estado" ]; then
    ventana=$(printf '%s' "$reglas" | grep -oE "\"name\":\"$nombre\".{0,2000}" | head -n 1 || true)
    estado=$(printf '%s' "$ventana" | grep -o '"state":"[^"]*"' | head -n 1 | sed 's/"state":"//;s/"$//' || true)
  fi
  echo "regla $nombre estado=${estado:--}"
  return 0
}

url_up='http://localhost:9090/api/v1/query?query=up'
url_reglas='http://localhost:9090/api/v1/rules'
# sum by (namespace) (rate(container_cpu_usage_seconds_total{namespace=~"notifier-.*"}[2m]))
url_cpu='http://localhost:9090/api/v1/query?query=sum%20by%20%28namespace%29%20%28rate%28container_cpu_usage_seconds_total%7Bnamespace%3D%7E%22notifier-.*%22%7D%5B2m%5D%29%29'
# sum by (namespace) (container_memory_working_set_bytes{namespace=~"notifier-.*"})
url_mem='http://localhost:9090/api/v1/query?query=sum%20by%20%28namespace%29%20%28container_memory_working_set_bytes%7Bnamespace%3D%7E%22notifier-.*%22%7D%29'

limite=$(($(date +%s) + 120))
api_ok=0
worker_ok=0
cadvisor_ok=0
regla_ratio=0
regla_cola=0
up=""
reglas=""

while :; do
  up=$(consultar "$url_up")
  reglas=$(consultar "$url_reglas")
  api_ok=0
  worker_ok=0
  cadvisor_ok=0
  regla_ratio=0
  regla_cola=0
  volcar up "$up" >/dev/null
  if estado_regla NotifierDeliveryFailureRatioHigh >/dev/null; then
    regla_ratio=1
  fi
  if estado_regla NotifierQueueDelayHigh >/dev/null; then
    regla_cola=1
  fi
  if [ "$api_ok" = 1 ] && [ "$worker_ok" = 1 ] && [ "$cadvisor_ok" = 1 ] \
    && [ "$regla_ratio" = 1 ] && [ "$regla_cola" = 1 ]; then
    break
  fi
  if [ "$(date +%s)" -ge "$limite" ]; then
    break
  fi
  sleep 10
done

volcar up "$up"
if estado_regla NotifierDeliveryFailureRatioHigh; then
  :
else
  echo "Falta: la regla NotifierDeliveryFailureRatioHigh"
fi
if estado_regla NotifierQueueDelayHigh; then
  :
else
  echo "Falta: la regla NotifierQueueDelayHigh"
fi

# Evidencia de métricas de infraestructura (MET-03). No decide la marca final.
volcar cpu "$(consultar "$url_cpu")"
volcar memoria "$(consultar "$url_mem")"

if [ "$api_ok" != 1 ]; then
  echo "Falta: up=1 de job notifier-api en namespace notifier-dev"
fi
if [ "$worker_ok" != 1 ]; then
  echo "Falta: up=1 de job notifier-worker en namespace notifier-dev"
fi
if [ "$cadvisor_ok" != 1 ]; then
  echo "Falta: up=1 de job kubelet-cadvisor"
fi

if [ "$api_ok" = 1 ] && [ "$worker_ok" = 1 ] && [ "$cadvisor_ok" = 1 ] \
  && [ "$regla_ratio" = 1 ] && [ "$regla_cola" = 1 ]; then
  echo VERIFICACION_OK
else
  exit 1
fi
EOF

echo ">> Verificando Prometheus en la VM (Grafana: https://$FQDN/grafana)"
SALIDA="$(az vm run-command invoke -g "$RESOURCE_GROUP" -n "$VM_NAME" --command-id RunShellScript \
  --scripts @"$TMP/en-la-vm.sh" --query 'value[0].message' -o tsv)"
grep -E '^up |^regla |^cpu |^memoria |^Falta|^VERIFICACION_OK$' <<<"$SALIDA" || true
grep -q VERIFICACION_OK <<<"$SALIDA" || { echo "La verificación del monitoreo falló." >&2; exit 1; }
