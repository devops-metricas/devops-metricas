# MET-01: Definir indicadores técnicos y de comportamiento del sistema pertinentes al escenario.

| | |
|---|---|
| **Responsable** | Camila |
| **Estado** | Parcial: definiciones completas; falta la medición en el clúster (sección 5) |
| **Evidencia mínima que se revisa** | Catálogo con definición, unidad, fuente, forma de cálculo y propósito. |

Cubre también los puntos 1, 2 y 4 del Anexo II (preguntas operativas, SLIs/SLOs y métricas de
aplicación). La instrumentación está en `src/notifier/observability.py`; la recolección y los paneles
son de Rene ([MET-03](MET-03-metricas-de-aplicacion.md), [MET-05](MET-05-dashboards.md)).

## 1. Preguntas operativas

| # | Pregunta | Qué decisión permite tomar | Indicadores |
|---|---|---|---|
| P1 | ¿Cuántas notificaciones aceptadas se entregan dentro del objetivo (30 s)? | Si se consume el presupuesto de error: congelar despliegues e investigar antes de seguir cambiando. | SLI-2 |
| P2 | ¿Qué canal o dependencia explica los reintentos y retrasos? | Distinguir un problema del proveedor de correo (escalar o ajustar reintentos y backoff) de uno propio (código, base de datos, capacidad). | I-5, I-6, I-7, trazas |
| P3 | ¿El worker da abasto o la cola crece? | Escalar el worker o subir sus requests/límites, frente a esperar a que la cola se vacíe sola. | I-8, I-9, I-12, I-13 |

## 2. SLIs

Las ventanas de prueba (1 h) sirven para la demostración; las de 7 días son las que se usarían en
operación real. No se exige demostrar un SLO mensual (Anexo II, punto 2).

### SLI-1: Disponibilidad de la aceptación

| Campo | Definición |
|---|---|
| Población | `POST /v1/notifications` recibidas por la API (ambos canales, todos los clientes). |
| Numerador | Respuestas `2xx` (202 aceptada y 200 repetición idempotente). |
| Denominador | Respuestas `2xx` + `5xx`. |
| Exclusiones | `4xx` (clave inválida, validación, conflicto de idempotencia): son errores del cliente, no del servicio. `/healthz`, `/readyz` y `/metrics` no se instrumentan. |
| Fuente | `http_requests_total{handler="/v1/notifications",method="POST"}` (prometheus-fastapi-instrumentator, agrupa el código en `2xx`/`4xx`/`5xx`). |
| Cálculo | `sum(increase(http_requests_total{handler="/v1/notifications",method="POST",status="2xx"}[1h])) / sum(increase(http_requests_total{handler="/v1/notifications",method="POST",status=~"2xx\|5xx"}[1h]))` |

### SLI-2: Entrega oportuna (específico del escenario)

Es el comportamiento distintivo del escenario: una respuesta 202 **no** es una entrega (ESC1). Mide lo
que le importa a quien envía la notificación.

| Campo | Definición |
|---|---|
| Población | Notificaciones aceptadas que llegaron a un estado final (`delivered` o `failed`) en la ventana. |
| Numerador | Entregadas en 30 s o menos desde la aceptación (`created_at` → `delivered_at`). |
| Denominador | Estados finales menos los errores permanentes. |
| Exclusiones | Errores permanentes (destinatario inválido, `@invalid.test`): son culpa del dato de entrada y el sistema actúa bien al no reintentar. Las notificaciones aún pendientes no cuentan hasta que terminan (ver limitación). |
| Fuente | Worker: `notifier_end_to_end_seconds` (histograma), `notifier_notifications_finished_total`, `notifier_delivery_attempts_total`. |
| Cálculo | `sum(increase(notifier_end_to_end_seconds_bucket{le="30"}[1h])) / (sum(increase(notifier_notifications_finished_total[1h])) - sum(increase(notifier_delivery_attempts_total{outcome="permanent_error"}[1h])))` |
| Por qué 30 s | Con 3 intentos y backoff de 5 s y 10 s, una notificación que falla dos veces por error pasajero y entra al tercer intento tarda ≈ 15 s más el procesamiento: sigue dentro del objetivo. El SLI tolera fallas pasajeras aisladas, pero no una degradación sostenida. |
| Limitación | Una notificación atascada en `pending` no baja el SLI hasta que termina. Por eso se vigila junto con I-9 (antigüedad del pendiente más viejo). El reproceso manual de una fallida cuenta el tiempo desde la aceptación original, así que casi nunca entra en 30 s: es lo correcto, porque el usuario sí esperó. |

### SLI-3: Latencia de aceptación

| Campo | Definición |
|---|---|
| Población | `POST /v1/notifications` con respuesta `2xx`. |
| Numerador | Las que responden en 500 ms o menos. |
| Denominador | Todas las de la población. |
| Exclusiones | Respuestas `4xx` y `5xx` (las `5xx` ya las mide SLI-1). |
| Fuente | `http_request_duration_seconds_bucket{handler="/v1/notifications",method="POST"}` (buckets 0.1, 0.5, 1). |
| Cálculo | `sum(increase(http_request_duration_seconds_bucket{handler="/v1/notifications",method="POST",le="0.5"}[1h])) / sum(increase(http_request_duration_seconds_count{handler="/v1/notifications",method="POST"}[1h]))` |
| Limitación | El histograma de latencia no separa por código de estado, así que incluye las `4xx` (rápidas): sesga el SLI levemente hacia arriba. Se acepta porque el umbral de 500 ms queda lejos del valor típico (≈ 100 ms medido en local). |

## 3. SLOs y presupuesto de error

| SLO | Objetivo | Ventana | Presupuesto de error | Justificación |
|---|---|---|---|---|
| SLO-A (sobre SLI-1) | ≥ 99,5 % | 7 días (demostración: 1 h) | 0,5 % de las solicitudes | Aceptar es solo registrar en PostgreSQL dentro de la misma VM: no depende del proveedor. Un 5xx implica base caída o despliegue roto. No se pide 99,9 % porque hay un solo nodo, sin alta disponibilidad (sección 4.2 del enunciado). |
| SLO-B (sobre SLI-2) | ≥ 95 % | 7 días (demostración: 1 h) | 5 % de las notificaciones terminadas | Depende de un proveedor externo que puede fallar. Más exigente obligaría a reintentar más rápido y presionar a un proveedor ya degradado. |

**Cálculo del presupuesto.** Presupuesto = (1 − objetivo) × eventos de la ventana.

- SLO-A: con 2 000 solicitudes en la ventana se toleran 0,005 × 2 000 = **10 respuestas 5xx**.
- SLO-B: con 1 000 notificaciones terminadas se toleran 0,05 × 1 000 = **50 fuera de objetivo**.
- Consumido = eventos malos / presupuesto. En PromQL, para SLO-B en la ventana de 1 h:
  `(1 - SLI-2) / 0.05`. Un resultado de 1 significa presupuesto agotado.

**Política.** Si el presupuesto consumido supera el 100 % en la ventana: no se promueven versiones a
`prod` hasta explicar la causa con evidencia (trazas, logs, métricas). Así lo usa el incidente de
[MET-07](MET-07-incidente-controlado.md).

## 4. Catálogo de indicadores

Las etiquetas son de cardinalidad acotada: `client` (aplicaciones registradas, decenas), `channel` (2),
`outcome` (3), `status` (5). **Nunca** se usan como etiqueta el `notification_id`, el destinatario ni el
`request_id`: crecerían sin límite. Esos identificadores van en logs y trazas (MET-02, MET-04).

Frecuencia de recolección: la que fije el `scrape_interval` de Prometheus (MET-03). Los contadores se
consultan siempre con `rate()` o `increase()`, que toleran el reinicio a cero al reiniciar un Pod.

| ID | Indicador | Tipo y unidad | Fuente | Cálculo (PromQL) | Propósito |
|---|---|---|---|---|---|
| I-1 | Solicitudes aceptadas | Contador, solicitudes | API: `notifier_notifications_accepted_total{client,channel}` | `sum by (channel) (rate(...[5m]))` | Volumen de entrada por canal y cliente (ESC1-01). |
| I-2 | Repeticiones idempotentes | Contador, solicitudes | API: `notifier_idempotent_replays_total{client,channel}` | `rate(...[5m])` | Ver si los clientes reintentan mucho (posibles timeouts del lado cliente). |
| I-3 | Conflictos de idempotencia | Contador, solicitudes | API: `notifier_idempotency_conflicts_total{client,channel}` | `increase(...[1h])` | Detectar clientes que reutilizan claves con otro contenido (error del integrador). |
| I-4 | Solicitudes HTTP por código | Contador, solicitudes | API: `http_requests_total{handler,method,status}` | ver SLI-1 | SLI-1 y errores de cliente (`4xx`). |
| I-5 | Intentos de entrega por resultado | Contador, intentos | Worker: `notifier_delivery_attempts_total{channel,outcome}` | `sum by (channel,outcome) (rate(...[5m]))` | P2: qué canal falla y si es pasajero o permanente. |
| I-6 | Tasa de error pasajero | Proporción (0-1) | Derivado de I-5 | `sum(rate(...{outcome="transient_error"}[5m])) by (channel) / sum(rate(...[5m])) by (channel)` | P2: salud del proveedor de correo. Base de la alerta de síntoma (MET-06). |
| I-7 | Duración de un intento | Histograma, segundos | Worker: `notifier_delivery_attempt_duration_seconds{channel}` | `histogram_quantile(0.95, sum by (le,channel) (rate(..._bucket[5m])))` | P2: distinguir un proveedor lento (timeouts) de uno que rechaza rápido (503). |
| I-8 | Notificaciones terminadas | Contador, notificaciones | Worker: `notifier_notifications_finished_total{channel,status}` | `sum by (status) (increase(...[1h]))` | Denominador de SLI-2; tasa de fallidas (ESC1-10). |
| I-9 | Antigüedad del pendiente más viejo | Gauge, segundos | Worker: `notifier_oldest_pending_age_seconds` | valor directo, `max_over_time(...[5m])` | P3: atraso real de la cola; cubre la limitación de SLI-2. |
| I-10 | Profundidad de la cola | Gauge, notificaciones | Worker: `notifier_queue_depth{status}` | valor directo | P3: trabajo acumulado (`pending`, `processing`). |
| I-11 | Tiempo de extremo a extremo | Histograma, segundos | Worker: `notifier_end_to_end_seconds{channel}` | `histogram_quantile(0.95, sum by (le,channel) (rate(..._bucket[5m])))` | P1 y SLI-2: lo que espera el destinatario. |
| I-12 | Latencia de la API | Histograma, segundos | API: `http_request_duration_seconds{handler,method}` | ver SLI-3 | SLI-3. |
| I-13 | CPU del worker y la API | Contador, segundos de CPU | cAdvisor (kubelet): `container_cpu_usage_seconds_total{namespace,pod,container}` | `sum by (container) (rate(...{namespace="notifier-dev"}[5m]))` | P3: si la cola crece, saber si el worker está saturado (CPU) o esperando al proveedor. |
| I-14 | Memoria de trabajo | Gauge, bytes | cAdvisor: `container_memory_working_set_bytes` | valor por contenedor, comparar con el límite (256 Mi) | P3 y DEV-11: margen frente al límite de memoria (riesgo de OOMKilled). |

**Resultado y latencia** (Anexo II, punto 4): de resultado son I-5 e I-8; de latencia o espera, I-7,
I-9, I-11 e I-12.

## 5. Medición en el clúster (pendiente)

Cuando Rene tenga Prometheus en el clúster, ejecutar las consultas de SLI-1, SLI-2 y SLI-3 en una
ventana de 1 h con tráfico (`python scripts/smoke.py batch` o `scripts/incidente.py`) y pegar aquí los
valores y la captura (`evidencias/MET-01-slis.png`).

| SLI | Valor medido | Ventana | Fecha (UTC) | Presupuesto consumido |
|---|---|---|---|---|
| SLI-1 | | 1 h | | |
| SLI-2 | | 1 h | | |
| SLI-3 | | 1 h | | |
