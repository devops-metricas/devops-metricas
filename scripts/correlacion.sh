#!/usr/bin/env bash
# Sigue UNA notificación de extremo a extremo (MET-02, MET-04, ESC1 P1-5):
#   1. logs de la API y del worker que mencionan su notification_id,
#   2. el trace_id que aparece en esos logs,
#   3. la traza completa en Jaeger (consultada por el proxy de la API de Kubernetes, sin exponer nada).
#
#   RESOURCE_GROUP=... VM_NAME=... ./scripts/correlacion.sh <notification_id> [dev|prod]
#
# Guarda todo en docs/evidencias/MET-02-correlacion-<id>.txt y MET-04-traza-<trace_id>.txt.

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
TRAZA="$RAIZ/docs/evidencias/MET-04-traza-${TRACE_ID:0:12}.txt"

# La salida de run-command se recorta a 4 KB y una traza completa pesa más: se resume dentro de la VM
# (servicio, operación, intento y error de cada span; sin los spans de SQL ni los internos de HTTP).
RESUMEN="$(base64 -w0 <<'PY'
import json, sys
d = json.load(sys.stdin)
for t in d.get("data", []):
    pr = {k: v["serviceName"] for k, v in t["processes"].items()}
    t0 = min(s["startTime"] for s in t["spans"])
    print(f"traza {t['traceID']}: {len(t['spans'])} spans")
    for s in sorted(t["spans"], key=lambda s: s["startTime"]):
        if s["operationName"] in ("SELECT", "INSERT", "UPDATE") or " http " in s["operationName"]:
            continue
        tg = {x["key"]: x["value"] for x in s["tags"]}
        err = "ERROR" if tg.get("error") or tg.get("otel.status_code") == "ERROR" else ""
        print(f"{(s['startTime'] - t0) / 1e6:9.2f} s +{s['duration'] / 1000:8.1f} ms "
              f"{pr[s['processID']]:<16} {s['operationName']:<26} "
              f"{tg.get('notification.attempt', '')} {err}")
PY
)"
"$RAIZ/scripts/vm.sh" "echo $RESUMEN | base64 -d > /tmp/resumen_traza.py; k3s kubectl get --raw \
  /api/v1/namespaces/observability/services/jaeger:16686/proxy/api/traces/$TRACE_ID \
  | python3 /tmp/resumen_traza.py" | tee "$TRAZA"
echo "Evidencia: $SALIDA y $TRAZA"
