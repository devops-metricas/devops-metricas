# MET-05: Construir dashboards que respondan preguntas operativas concretas.

> **Parcial.**

| | |
|---|---|
| **Responsable** | Rene |
| **Estado** | Parcial |
| **Evidencia mínima que se revisa** | Paneles interpretables, con unidades y ventanas temporales. |

## Qué hay y qué falta

El dashboard **Notificaciones - operacion** (`uid` `notifier-ops`) se provisiona desde
[monitoring/grafana/dashboards/notifier.json](../../monitoring/grafana/dashboards/notifier.json). El rango
por defecto es 30 min y el refresco es de 10 s. Tiene ocho paneles de serie temporal. Cada uno lleva la
unidad y la ventana en el título.

| Panel | Pregunta operativa | Consulta PromQL | Unidad | Ventana |
|---|---|---|---|---|
| 1. Solicitudes aceptadas por canal | ¿A qué ritmo se aceptan solicitudes, por canal? | `sum by (channel) (rate(notifier_notifications_accepted_total[1m]))` | reqps | 1 m |
| 2. Tasa de éxito de entrega por canal | ¿Qué fracción de los finales es una entrega, por canal? | `sum by (channel) (increase(notifier_notifications_finished_total{status="delivered"}[5m])) / sum by (channel) (increase(notifier_notifications_finished_total[5m]))` | percentunit | 5 m |
| 3. Intentos de entrega por resultado | ¿Cómo se reparten los intentos según el resultado? | `sum by (channel, outcome) (rate(notifier_delivery_attempts_total[1m]))` | ops | 1 m |
| 4. Latencia extremo a extremo p95 por canal | ¿Cuál es el p95 desde la aceptación hasta la entrega, por canal? | `histogram_quantile(0.95, sum by (le, channel) (rate(notifier_end_to_end_seconds_bucket[5m])))` | s | 5 m |
| 5. Backlog de la cola por estado | ¿Cuántos trabajos hay en cola, por estado? | `sum by (status) (notifier_queue_depth)` | short | instantáneo |
| 6. Antigüedad del trabajo pendiente más viejo | ¿Cuánto lleva esperando el pendiente más viejo? | `max(notifier_oldest_pending_age_seconds)` | s | instantáneo |
| 7. API: latencia p95 y errores 5xx | ¿Cuál es el p95 de la API y a qué ritmo hay errores 5xx? | `histogram_quantile(0.95, sum by (le) (rate(http_request_duration_highr_seconds_bucket{job="notifier-api"}[5m])))` y `sum(rate(http_requests_total{job="notifier-api",status="5xx"}[5m]))` | s y reqps | 5 m |
| 8. Capacidad: CPU y memoria por componente | ¿Cuánta CPU y memoria residente usa cada componente? | `sum by (job) (rate(process_cpu_seconds_total{job=~"notifier-.*"}[5m]))` y `sum by (job) (process_resident_memory_bytes{job=~"notifier-.*"})` | percentunit y bytes | 5 m en la CPU; la memoria es el valor instantáneo |

**Falta** el panel 8, que en Windows sale vacío, y falta desplegar Grafana en K3s para validarlo.

## Evidencia

Capturas tomadas a las 23:43, hora local del 9/11/2026, con el rango de los últimos 15 minutos (no es el
rango por defecto de 30 min). El recorte muestra los paneles; el selector de tiempo no entra en la imagen.

Mitad superior. A las 23:30 la tasa de éxito del correo cae a 0 % y el canal `internal` sigue en 100 %.
En intentos, el `transient_error` del correo llega a unos 2,5 intentos/s. Hacia las 23:40 el p95 extremo
a extremo de `internal` sube a unos 4,7 min.

![Dashboard, paneles superiores](../evidencias/MET-05-dashboard-superior.png)

Mitad inferior. En el backlog hay un hueco sin datos entre ~23:34 y ~23:38; hacia las 23:39 la serie
`pending` salta a 100. La antigüedad del pendiente más viejo llega a unos 3,8 min en ese mismo momento.
El p95 de la API (la serie visible es «p95 latencia») se mueve entre unos 50 ms y unos 330 ms. El panel
de capacidad muestra **No data**.

![Dashboard, paneles inferiores](../evidencias/MET-05-dashboard-inferior.png)

## Interpretación

El hueco y el backlog de 100 corresponden a que el worker estuvo detenido por el operador, de ~23:32 a
~23:38, durante la demostración de alertas de [MET-06](MET-06-alertas.md). Al reiniciarse procesó de
golpe lo acumulado. Es evidencia real del efecto de una caída del worker, y de que sus series desaparecen
mientras está caído.

El p95 extremo a extremo queda cerca del último bucket del histograma (300 s). Está saturado: no es un
valor exacto.

## Hipótesis

No verificada: durante la falla del correo, el p95 del canal `internal` habría subido a unos 7 s porque
el worker procesa los trabajos en secuencia y los reintentos de correo le compiten el tiempo. Estas dos
capturas no muestran ese valor. En el panel de latencia extremo a extremo, `internal` sigue cerca de 0 s
a las 23:30; el salto que sí se ve es el de unos 4,7 min hacia las 23:39.
