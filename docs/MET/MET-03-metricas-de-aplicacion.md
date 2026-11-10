# MET-03: Instrumentar métricas de aplicación y relacionarlas con métricas de infraestructura.

> **Parcial.**

| | |
|---|---|
| **Responsable** | Rene |
| **Estado** | Parcial |
| **Evidencia mínima que se revisa** | Consultas y series temporales verificables. |

## Qué hay y qué falta

Prometheus v2.55.1 y Grafana 11.3.0 están en [docker-compose.monitoring.yml](../../docker-compose.monitoring.yml).
La recolección está en [monitoring/prometheus.yml](../../monitoring/prometheus.yml): `scrape_interval` 15 s y
`evaluation_interval` 15 s. Dos jobs, ambos con la etiqueta `environment=local`:

| Job | Destino |
|---|---|
| `notifier-api` | `host.docker.internal:8000` |
| `notifier-worker` | `host.docker.internal:9100` |

Las métricas de aplicación se definen en [src/notifier/observability.py](../../src/notifier/observability.py):

| Métrica | Tipo | Labels |
|---|---|---|
| `notifier_notifications_accepted_total` | contador | `client`, `channel` |
| `notifier_idempotent_replays_total` | contador | `client`, `channel` |
| `notifier_idempotency_conflicts_total` | contador | `client`, `channel` |
| `notifier_delivery_attempts_total` | contador | `channel`, `outcome` (`success`, `transient_error`, `permanent_error`) |
| `notifier_notifications_finished_total` | contador | `channel`, `status` |
| `notifier_delivery_attempt_duration_seconds` | histograma | `channel` |
| `notifier_end_to_end_seconds` | histograma | `channel`; buckets de 0,5 s a 300 s |
| `notifier_queue_depth` | gauge | `status` |
| `notifier_oldest_pending_age_seconds` | gauge | sin labels |

En Prometheus también se comprobaron las métricas HTTP de `prometheus-fastapi-instrumentator`:
`http_requests_total{handler,method,status}`, con `status` agrupado en `2xx`, `4xx` y `5xx`, y
`http_request_duration_highr_seconds_bucket`, que no trae el label `handler`.

**Falta** relacionarlas con la infraestructura. CPU y memoria del proceso (`process_*`) solo existen en
Linux, así que no aparecen en el Windows local. Tampoco está desplegado el monitoreo en K3s.

## Evidencia

Consulta en Prometheus, ventana de 10 min:

```
sum by (channel, outcome) (increase(notifier_delivery_attempts_total[10m]))
```

La tabla devuelve dos series, las dos en `outcome="success"`, con el mismo valor **51,286…** (51,29):
`channel="email"` y `channel="internal"`. La casilla *Evaluation time* está tapada: la tabla no muestra
la hora de la evaluación.

![Tabla de intentos exitosos por canal](../evidencias/MET-03-consulta-intentos-tabla.png)

La misma consulta en gráfico, con *Use local time* desmarcado. El eje va de 03:00 a 03:55. Las dos series
van superpuestas: permanecen en 0 y suben en un escalón hasta unos 51 entre las 03:45 y las 03:50.

![Serie de intentos exitosos por canal](../evidencias/MET-03-consulta-intentos-serie.png)

## Interpretación

El lote real fue de 50 envíos por canal. `increase()` extrapola en los bordes de la ventana, y por eso el
valor no es 50 sino 51,29. El eje del gráfico está en UTC: las 03:48 UTC son las 21:48, hora de El
Salvador (UTC−6).

## Hipótesis

No hay una hipótesis aparte sobre esa serie: la diferencia entre 50 y 51,29 es el efecto de `increase()`,
ya contrastado con el tamaño del lote.

Lo no verificado es la parte de infraestructura. No está comprobado que `process_*` se vea al desplegar
el monitoreo en K3s; en esta máquina no se pudo observar.
