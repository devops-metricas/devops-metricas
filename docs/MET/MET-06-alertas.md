# MET-06: Configurar alertas vinculadas a condiciones justificadas.

> **Parcial.**

| | |
|---|---|
| **Responsable** | Rene |
| **Estado** | Parcial |
| **Evidencia mínima que se revisa** | Regla, evidencia de activación y explicación de posibles falsos positivos. |

## Qué hay y qué falta

Dos reglas en [monitoring/alerts.yml](../../monitoring/alerts.yml), grupo `notifier-alerts`, intervalo de
evaluación 30 s. `promtool` las aceptó: `SUCCESS: 2 rules found`.

| Regla | Expresión | Umbral | Ventana de la consulta | Intervalo de evaluación | Periodo pendiente (`for`) | Severidad | Justificación | Falsos positivos |
|---|---|---|---|---|---|---|---|---|
| `NotifierDeliveryFailureRatioHigh` | `sum by (channel) (rate(notifier_delivery_attempts_total{outcome!="success"}[2m])) / sum by (channel) (rate(notifier_delivery_attempts_total[2m]))` y `sum by (channel) (rate(notifier_delivery_attempts_total[2m]))` | ratio > 0,20 y tráfico > 0,02 intentos/s | 2 min (8 scrapes de 15 s; basta para que `rate()` no oscile) | 30 s (evaluar más rápido que el scrape de 15 s no aporta datos nuevos) | 1 min (no dispara por un pico corto) | critical | Más del 20 % de los intentos del canal fallan, con un mínimo de tráfico para no reaccionar al vacío | Con poco tráfico un solo fallo da un ratio alto; el mínimo de 0,02 intentos/s lo recorta |
| `NotifierQueueDelayHigh` | `max(notifier_oldest_pending_age_seconds)` | > 30 s | instantáneo | 30 s | 2 min | warning | El máximo normal observado fue unos 2,3 s; 30 s es más de diez veces lo habitual | Un solo trabajo viejo basta, aunque el resto de la cola esté al día |

Limitaciones de `NotifierQueueDelayHigh`, ya escritas en la regla:

- Esa métrica solo la publica el worker. Si el worker se detiene, la serie desaparece y la regla no
  dispara. Se vio en el panel de backlog de [MET-05](MET-05-dashboards.md): hueco entre ~23:34 y ~23:38.
- Solo cuenta trabajos listos para procesar (`next_attempt_at <= now()`). Los reintentos en espera de
  backoff (5 s, 10 s) no suben el valor.

La regla está definida y justificada. Su disparo no se demostró.

Otros falsos positivos de la regla de entregas: la alerta se cierra sola si el tráfico cae por debajo del
mínimo, y un fallo transitorio que luego se reintenta con éxito cuenta como intento fallido. La regla
mira intentos, no el estado final de la notificación.

**Falta** repetir la demostración de recuperación sosteniendo tráfico mientras se corrige la causa, y
demostrar el disparo de `NotifierQueueDelayHigh`.

## Evidencia

Demostración de `NotifierDeliveryFailureRatioHigh` con el worker local en
`NOTIFIER_EMAIL_FAULT_RATE=1.0` y `NOTIFIER_EMAIL_FAULT_KIND=503`. Las capturas no muestran el reloj del
sistema. La hora se toma del campo *Active Since* y de la serie `ALERTS` de Prometheus.

Antes de la falla las dos reglas están inactivas (Inactive 2, Pending 0, Firing 0), cargadas desde
`/etc/prometheus/alerts.yml`, grupo `notifier-alerts`.

![Alertas inactivas antes de la falla](../evidencias/MET-06-01-alertas-inactivas-antes.png)

`NotifierDeliveryFailureRatioHigh` pasa a pending para `channel=email` y `severity=critical`. *Active
Since* es `2026-11-10T05:29:45Z`, es decir las 23:29:45 del 9/11/2026 en El Salvador (UTC−6).
`NotifierQueueDelayHigh` sigue en 0 active.

![Alerta en pending](../evidencias/MET-06-02-alerta-pending.png)

La misma alerta en firing. El *Active Since* no cambia: el paso a firing no tiene otro reloj en la
imagen. `NotifierQueueDelayHigh` sigue inactiva.

![Alerta en firing](../evidencias/MET-06-03-alerta-firing.png)

Consulta de los intentos, eje en UTC, *Use local time* desmarcado:

```
sum by (channel, outcome) (increase(notifier_delivery_attempts_total[5m]))
```

En el canal `email`, la serie `success` cae a 0 hacia las 05:24 UTC y la serie `transient_error` sube a
partir de las 05:29 UTC (23:29 hora local).

![Intentos fallidos del canal email](../evidencias/MET-06-04-consulta-intentos-fallidos.png)

Después, las dos reglas vuelven a inactive. Esta captura tampoco muestra una hora.

![Alerta de nuevo inactiva](../evidencias/MET-06-06-alerta-recuperada.png)

Línea de tiempo de la corrida del 9/11/2026, hora local de El Salvador (UTC−6):

| Hora local | Hecho |
|---|---|
| 23:29:00 | El worker arranca con la falla |
| 23:29:45 | La alerta pasa a pending (*Active Since* `2026-11-10T05:29:45Z`) |
| ~23:30:45 | Pasa a firing: el pending más el `for` de 1 min |
| ~23:32:20 | La serie firing termina, según `ALERTS` |

Corrida anterior, leída de la misma serie `ALERTS`:

| Hora local | Hecho |
|---|---|
| 23:09:01 | Arranque con la falla |
| 23:10:45 | Pending |
| ~23:11:45 | Firing |
| ~23:13:15 | Fin de firing |

## Interpretación

En las dos corridas la alerta dejó de estar en firing cuando el lote con falla terminó y los intentos
cayeron por debajo del mínimo de tráfico (0,02 intentos/s), antes de reiniciar el worker sin falla. La
recuperación demostrada es por falta de tráfico, no una recuperación limpia tras corregir la causa con
tráfico sano todavía presente. Es una limitación de la regla y de esta demostración.

## Hipótesis

No está verificado que `NotifierDeliveryFailureRatioHigh` se recupere al quitar la falla si el tráfico
sigue por encima de 0,02 intentos/s. Lo pendiente es repetir la demostración sosteniendo tráfico durante
la corrección.

Tampoco está verificado el disparo de `NotifierQueueDelayHigh`. En las capturas de esta corrida permanece
en 0 active; eso muestra que aquí no disparó, no que la condición no pueda cumplirse.
