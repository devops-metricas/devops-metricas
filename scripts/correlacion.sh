#!/usr/bin/env bash
# Sigue UNA notificación de extremo a extremo (MET-02, MET-04, ESC1 P1-5):
#   1. logs de la API y del worker que mencionan su notification_id,
#   2. el trace_id que aparece en esos logs,
#   3. la traza completa en Jaeger (consultada por el proxy de la API de Kubernetes, sin exponer nada).
#
#   RESOURCE_GROUP=... VM_NAME=... ./scripts/correlacion.sh <notification_id> [dev|prod]
#
# Guarda todo en docs/evidencias/MET-02-correlacion-<id>.txt y MET-04-traza-<trace_id>.json.

set -euo pipefail
NID="${1:?uso: correlacion.sh <notification_id> [dev|prod]}"
ENTORNO="${2:-dev}"
NS="notifier-$ENTORNO"
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
SALIDA="$RAIZ/docs/evidencias/MET-02-correlacion-${NID:0:8}.txt"

echo ">> Logs de api y worker con notification_id=$NID ($NS)"
LOGS="$("$RAIZ/scripts/vm.sh" "k3s kubectl -n $NS logs deploy/api --since=24h | grep '$NID' || true
echo '---- worker ----'
k3s kubectl -n $NS logs deploy/worker --since=24h | grep '$NID' || true")"
{ echo "# Correlación de la notificación $NID ($NS), $(date -u +%FT%TZ)"; echo "$LOGS"; } > "$SALIDA"
echo "$LOGS"

TRACE_ID="$(grep -o '"trace_id": *"[0-9a-f]\{32\}"' <<<"$LOGS" | head -1 | grep -o '[0-9a-f]\{32\}' || true)"
if [[ -z "$TRACE_ID" ]]; then
  echo "No se encontró trace_id en los logs (¿OTEL_EXPORTER_OTLP_ENDPOINT configurado?)." >&2
  exit 1
fi
echo ">> trace_id=$TRACE_ID; consultando Jaeger"
TRAZA="$RAIZ/docs/evidencias/MET-04-traza-${TRACE_ID:0:12}.json"
"$RAIZ/scripts/vm.sh" "k3s kubectl get --raw \
  /api/v1/namespaces/observability/services/jaeger:16686/proxy/api/traces/$TRACE_ID" > "$TRAZA"

# Resumen legible: servicio, operación y duración de cada span.
python3 - "$TRAZA" <<'PY'
import json, re, sys
texto = open(sys.argv[1]).read()
datos = json.loads(texto[texto.index("{"):texto.rindex("}") + 1])
for t in datos.get("data", []):
    procesos = {k: v["serviceName"] for k, v in t["processes"].items()}
    inicio = min(s["startTime"] for s in t["spans"])
    for s in sorted(t["spans"], key=lambda s: s["startTime"]):
        print(f'{(s["startTime"]-inicio)/1000:9.1f} ms  +{s["duration"]/1000:8.1f} ms  '
              f'{procesos[s["processID"]]:<16} {s["operationName"]}')
PY
echo "Evidencia: $SALIDA y $TRAZA"
