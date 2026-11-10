# MET-04: Instrumentar trazas con OpenTelemetry para operaciones relevantes que atraviesen componentes.

| | |
|---|---|
| **Responsable** | Camila |
| **Estado** | Parcial: cadena completa verificada en local; falta instalar y capturar en el clúster |
| **Evidencia mínima que se revisa** | Trazas consultables y correlación razonable entre señales. |

## 1. Arquitectura de trazas

```
 notifier-dev / notifier-prod                         namespace observability
 ┌────────────┐  OTLP/HTTP :4318   ┌────────────────┐  OTLP/gRPC :4317  ┌─────────────────────┐
 │ api        │───────────────────▶│ otel-collector │──────────────────▶│ jaeger (en memoria) │
 │ worker     │───────────────────▶│ memory_limiter │                   │ UI y API :16686     │
 └────────────┘                    │ batch          │                   └─────────────────────┘
                                   └────────────────┘    ▲ solo ClusterIP: se consulta por el proxy
                                                           de la API de Kubernetes, dentro de la VM
```

| Pieza | Archivo | Decisión |
|---|---|---|
| SDK en la app | `src/notifier/observability.py` | Exporta por OTLP/HTTP solo si existe `OTEL_EXPORTER_OTLP_ENDPOINT`. En local y en CI no exporta, y las pruebas no dependen del colector. |
| Variable de entorno | `k8s/base/kustomization.yaml` | Un solo colector para dev y prod; cada span lleva `deployment.environment`, así se filtra por ambiente. |
| Colector | `k8s/observability/otel-collector.yaml` | Desacopla la app del backend: cambiar a Tempo o agregar muestreo se hace aquí, sin reconstruir la imagen. `memory_limiter` evita que se caiga si Jaeger no responde. |
| Backend | `k8s/observability/jaeger.yaml` | Jaeger all-in-one en memoria (20 000 trazas máximo). Sin disco ni servicio de Azure: costo adicional cero. |
| Instalación | `scripts/aplicar-observabilidad.sh` | Igual que `desplegar.sh`: se renderiza con kustomize y se aplica en la VM con `az vm run-command`. |

## 2. Spans de una notificación

| Span | Servicio | Tipo | Qué representa |
|---|---|---|---|
| `POST /v1/notifications` | notifier-api | SERVER | Solicitud completa: autenticación, validación, idempotencia e INSERT. Automático (FastAPI). |
| `SELECT`, `INSERT` | notifier-api | CLIENT | Consultas a PostgreSQL. Automático (psycopg). |
| `notification.process` | notifier-worker | CONSUMER | Un intento de entrega. Atributos `notification.id`, `notification.channel`, `notification.attempt`. Manual, en `worker/main.py`. |
| `email.send` | notifier-worker | INTERNAL | Conversación con el proveedor SMTP. Queda en error si falla. Manual, en `channels/email.py`. |
| `INSERT`, `UPDATE` | notifier-worker | CLIENT | Registro del intento y cambio de estado. |

**Propagación asíncrona.** La API y el worker no se hablan por HTTP: se comunican a través de la tabla
`notifications`, que hace de cola. La API inyecta el contexto W3C (`traceparent`) y lo guarda en la fila;
el worker lo extrae al tomar el trabajo y crea `notification.process` como hijo. Resultado: **una sola
traza** contiene la aceptación y todos los intentos, aunque estén separados por segundos o minutos.

## 3. Lectura de una traza real

Entorno local, mismo código y mismas versiones que el clúster (colector 0.114.0, Jaeger 1.62.0), falla
del proveedor inyectada al 70 % y backoff de 1 s (en el clúster es de 5 s y 10 s). Archivos:
[MET-04-traza-local.txt](../evidencias/MET-04-traza-local.txt) y
[MET-04-traza-local.json](../evidencias/MET-04-traza-local.json) (respuesta de la API de Jaeger).

| Inicio | Duración | Servicio | Span | Intento |
|---|---|---|---|---|
| 0 ms | 95,6 ms | api | `POST /v1/notifications` | |
| 13–16 ms | ≈ 3 ms | api | `SELECT` + 3 `INSERT` | |
| 241,9 ms | 3,4 ms | worker | `notification.process` → `email.send` **error** | 1 |
| 1 270,3 ms | 1,9 ms | worker | `notification.process` → `email.send` **error** | 2 |
| 3 291,9 ms | 4,6 ms | worker | `notification.process` → `email.send` ok | 3 |

**Interpretación de tiempos.**

- La API respondió en 96 ms; las consultas a la base suman ≈ 3 ms. El resto es el propio framework y el
  cierre de la respuesta, no la base de datos.
- Entre el fin de la API (96 ms) y el primer intento (242 ms) hay ≈ 146 ms **sin span**: es la espera en
  cola hasta que el worker sondea (`poll_interval_seconds` = 1 s como máximo). No aparece como span
  porque nada se ejecuta en ese tiempo; se lee como hueco.
- Cada intento dura menos de 5 ms. Los huecos de ≈ 1 s y ≈ 2 s entre intentos son el **backoff**
  (`retry_backoff_seconds × 2^(intento-1)`).
- Conclusión: el tiempo de extremo a extremo (3,3 s) se explica casi entero por esperas deliberadas, no
  por lentitud de ningún componente. Con el backoff del clúster sería ≈ 15 s, dentro del objetivo de
  30 s de SLI-2 ([MET-01](MET-01-catalogo-de-indicadores.md)).

**Correlación con las otras señales.**

- Logs: el `trace_id` `8dc551ea…` es el mismo de los cuatro registros de
  [MET-02](MET-02-logs-estructurados.md) (aceptación y tres intentos).
- Métricas: cada span `email.send` en error corresponde a un incremento de
  `notifier_delivery_attempts_total{channel="email",outcome="transient_error"}`; el éxito final, a un
  `notifier_end_to_end_seconds` de ≈ 3,3 s.

## 4. Cómo consultar las trazas en el clúster

```bash
# Instalar o actualizar colector y Jaeger (una vez por reconstrucción del ambiente)
RESOURCE_GROUP=... VM_NAME=... ./scripts/aplicar-observabilidad.sh

# Seguir una notificación: logs → trace_id → traza en Jaeger (guarda la evidencia)
RESOURCE_GROUP=... VM_NAME=... ./scripts/correlacion.sh <notification_id> dev

# Buscar trazas recientes con error del worker de dev
./scripts/vm.sh "k3s kubectl get --raw '/api/v1/namespaces/observability/services/jaeger:16686/proxy/api/traces?service=notifier-worker&tags=%7B%22error%22%3A%22true%22%7D&limit=5&lookback=1h'"
```

Para ver la interfaz web de Jaeger (opcional, solo desde la IP de administración autorizada en el NSG):

```bash
ssh -L 16686:localhost:16686 <usuario>@<ip-publica> \
  "sudo k3s kubectl -n observability port-forward svc/jaeger 16686:16686"
# y abrir http://localhost:16686
```

## 5. Muestreo, costos y límites

- **Muestreo:** 100 % de las trazas (`parentbased_always_on`, el valor por defecto del SDK). Con el
  volumen de las pruebas (cientos de solicitudes) no hace falta muestrear. Con tráfico real se
  configuraría muestreo en el colector (`probabilistic_sampler` o `tail_sampling`, para conservar todas
  las trazas con error).
- **Costo:** ≈ 75 m de CPU y 192 Mi de memoria solicitados en la misma VM; nada en Azure.
- **Retención:** en memoria. Si el Pod de Jaeger se reinicia, las trazas anteriores se pierden. Por eso
  la evidencia se exporta a `docs/evidencias/` en el momento.
- **Pérdida en tránsito:** el SDK envía en lotes cada pocos segundos. Si el worker muere de golpe
  (SIGKILL), los spans no enviados se pierden; con un apagado ordenado (SIGTERM) se envían.
- **Huecos:** la espera en cola no es un span. Si se quisiera medir explícitamente, se agregaría al span
  `notification.process` un atributo con la espera (`now() − next_attempt_at`).

## Evidencia

- [x] Cadena completa en local: [MET-04-traza-local.txt](../evidencias/MET-04-traza-local.txt).
- [ ] Pods del colector y Jaeger en `Running`: salida de `aplicar-observabilidad.sh` → `evidencias/MET-04-instalacion.txt`.
- [ ] Traza del clúster con reintentos: `correlacion.sh` → `evidencias/MET-04-traza-<id>.json`.
- [ ] Captura de la traza en la interfaz de Jaeger → `evidencias/MET-04-jaeger.png`.
