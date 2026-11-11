# MET-07: Analizar al menos una degradación inducida y una recuperación.

| | |
|---|---|
| **Responsable** | Camila |
| **Estado** | Cubierto: corrida `2699b5ea` en `dev`, 2026-11-11 00:36–01:04 UTC |
| **Evidencia mínima que se revisa** | Secuencia temporal, evidencia, interpretación y limitaciones. |

Cubre la condición 5.11, el punto 8 del Anexo II y la prueba P1-5 del escenario. Las alertas de la
misma corrida están en [MET-06](MET-06-alertas.md) (Rene).

## 1. Qué se degrada y por qué

**Falla:** el proveedor de correo responde `503` en el 60 % de los envíos
(`NOTIFIER_EMAIL_FAULT_RATE=0.6`, `NOTIFIER_EMAIL_FAULT_KIND=503`).

Es la falla más probable del escenario (un proveedor externo inestable) y la única que ejercita a la vez
reintentos, backoff, estados `failed`, reproceso y aislamiento entre canales. Es reversible y no
destruye datos (condición 5.12).

## 2. Hipótesis inicial (escrita antes de correr)

Con 3 intentos y una probabilidad de fallo de 0,6 por intento, independiente:

| Señal | Base | Degradación esperada | Por qué |
|---|---|---|---|
| Correos que terminan `failed` | ≈ 0 % | ≈ 21,6 % | 0,6³: fallan los tres intentos |
| Intentos promedio por correo | 1,0 | ≈ 1,96 | 1 + 0,6 + 0,6² |
| SLI-2 (entrega en ≤ 30 s), correo | ≈ 100 % | ≈ 78 % | las que se entregan lo hacen en el intento 2 (≈ 5 s) o 3 (≈ 15 s), dentro de 30 s; las que fallan no |
| p95 de extremo a extremo, correo | < 2 s | ≈ 15 s | el percentil cae en entregas al tercer intento |
| Canal interno | 100 % | **sin cambio** | no usa el proveedor de correo: si cambia, la hipótesis de aislamiento es falsa |
| SLI-1 (aceptación) | ≈ 100 % | **sin cambio** | la API solo registra; no depende del proveedor |

Si se cumple, el SLO-B (≥ 95 %) se incumple durante la degradación: el presupuesto de error de la
ventana se agota ((1 − 0,78) / 0,05 ≈ 4,4 veces el presupuesto).

## 3. Procedimiento reproducible

Requisitos: VM encendida, `main` desplegado en `dev` con *Entrega*, colector y Jaeger instalados
(`scripts/aplicar-observabilidad.sh`), Prometheus y Grafana de Rene funcionando, y las claves de prueba
exportadas en la terminal (nunca en el repo).

```bash
export RESOURCE_GROUP=rg-notifier VM_NAME=vm-notifier API_URL=https://<fqdn>/dev API_KEY=ntf_... ADMIN_KEY=ntf_...
export FAULT_CMD='./scripts/vm.sh "k3s kubectl -n notifier-dev set env deploy/worker NOTIFIER_EMAIL_FAULT_RATE=0.6 && k3s kubectl -n notifier-dev rollout status deploy/worker"'
export RESTORE_CMD='./scripts/vm.sh "k3s kubectl -n notifier-dev set env deploy/worker NOTIFIER_EMAIL_FAULT_RATE- && k3s kubectl -n notifier-dev rollout status deploy/worker"'
PHASE_SECONDS=300 python scripts/incidente.py      # ≈ 20 min
```

`scripts/incidente.py` envía 2 solicitudes por segundo (2 de cada 3 por correo, 1 interna como grupo de
control) durante tres fases de 5 minutos (base, degradación, recuperación), reprocesa las que quedaron
`failed` y calcula los resultados por fase.

`kubectl set env` sobrescribe la variable solo en el worker y provoca un reinicio controlado.
`NOTIFIER_EMAIL_FAULT_RATE-` la elimina y vuelve al valor del ConfigMap (0).

**Qué pasó en esta corrida.** El tráfico y las fases se completaron, pero el script terminó con un
`KeyError` al calcular la tabla: al cortar el tráfico, una solicitud en vuelo (la número 1646) se
registró después de tomar la lista de IDs. Se corrigió (el script ahora espera ese hilo) y los
resultados se calcularon desde la base de datos con `scripts/incidente_reanudar.py`, que identifica las
notificaciones por su asunto (`Incidente 2699b5ea`) y asigna la fase por `created_at` con las marcas de
la línea de tiempo. No hubo que repetir el incidente: al momento del cálculo nada se había reprocesado,
así que el estado de la base era exactamente el "antes de mitigar".

## 4. Línea de tiempo (UTC, 2026-11-11)

| Hora | Qué pasó | Fuente |
|---|---|---|
| 00:36:13 | Inicio de la fase base (proveedor sano) | [línea de tiempo](../evidencias/MET-07-linea-de-tiempo-2699b5ea.txt) |
| 00:41:13 | Se activa la falla (`FAULT_CMD`) | ídem |
| 00:41:49 | Worker reiniciado con la falla activa (36 s de rollout) | ídem |
| 00:43:33 | Se acepta `02e7bade…`, la notificación usada para correlacionar | log `notification_accepted` |
| 00:43:49 | `02e7bade…` agota su tercer intento y queda `failed` | traza (15,65 s tras la aceptación) |
| ver MET-06 | La alerta `NotifierDeliveryFailureRatioHigh` pasa a pending y firing | capturas de Rene |
| 00:46:49 | Se quita la falla (`RESTORE_CMD`) | línea de tiempo |
| 00:47:25 | Worker reiniciado sin falla | ídem |
| ver MET-06 | La alerta se resuelve | capturas de Rene |
| 00:52:25 | Fin del tráfico: 1646 solicitudes aceptadas, ninguna rechazada | línea de tiempo |
| 01:04:01 | Mitigación: reproceso de las 81 notificaciones fallidas (admin) | log `notification_reprocessed` |
| 01:04:02 | `02e7bade…` se entrega en el intento 4 | log `delivery_attempt` y traza |

## 5. Detección y diagnóstico

1. **Síntoma:** subió la tasa de error pasajero del correo (I-6) y bajó SLI-2 del correo a 78,7 %.
2. **¿Es el proveedor o somos nosotros?** El canal interno siguió al 100 % en todas las fases y la API
   aceptó las 1646 solicitudes sin ningún 5xx (SLI-1 = 100 %) → el problema está después de la cola y
   solo en el correo.
3. **¿Lento o rechazando?** En la traza, cada `email.send` fallido dura 0,2–0,3 ms → el proveedor
   rechaza de inmediato (503), no hay timeouts.
4. **¿Hay atraso de capacidad?** Los intentos fallidos son casi instantáneos y lo que separa un intento
   del siguiente es el backoff (5 s y 10 s en la traza) → no es falta de capacidad; escalar el worker no
   ayudaría.
5. **Mecanismo causal:** el proveedor rechaza → el worker reintenta con backoff (5 s, 10 s) → el 60 %
   de los correos tarda más y ≈ 21 % agota los intentos → baja SLI-2.

### Una notificación de punta a punta

Notificación `02e7bade-b5d4-49f5-9a86-c378e0fa6ce4`, aceptada durante la degradación. Archivos:
[logs](../evidencias/MET-02-correlacion-02e7bade.txt) y
[traza](../evidencias/MET-07-traza-863f3fdb.txt) (`trace_id` `863f3fdbb2bab71b0f637d68bab98aed`).

| Desde la aceptación | Servicio | Span | Intento | Resultado |
|---|---|---|---|---|
| 0 s | api | `POST /v1/notifications` (7,5 ms) | | 202 |
| 0,21 s | worker | `notification.process` → `email.send` | 1 | **error** 503 |
| 5,35 s | worker | `notification.process` → `email.send` | 2 | **error** 503 |
| 15,65 s | worker | `notification.process` → `email.send` | 3 | **error** 503, queda `failed` |
| 1228,65 s (20,5 min) | worker | `notification.process` → `email.send` | 4 | entregada (reproceso) |

Los cuatro intentos están en **una sola traza** aunque los atendieron dos Pods distintos del worker
(los tres primeros el degradado y el cuarto el restaurado, 20 minutos después): el `traceparent` viaja en la fila
de la notificación ([MET-04](MET-04-trazas-opentelemetry.md)). Los huecos de 5 s y 10 s entre intentos
son exactamente el backoff configurado.

**Hallazgo: los logs no bastaron.** Al buscar la notificación en los logs solo aparecieron la
aceptación, el reproceso y el intento 4. Los intentos 1 a 3 se registraron en el Pod del worker que se
reemplazó al quitar la falla, y sus logs se perdieron con él (limitación declarada en
[MET-02](MET-02-logs-estructurados.md)). La traza, guardada fuera del Pod, conservó los cuatro intentos.
El `trace_id` del log de la API fue el puente entre las dos señales.

## 6. Respuesta operativa

1. **Contención:** no se tocó la aplicación; el sistema hizo lo que debía (reintentar y no perder nada).
2. **Corrección de la causa:** se restableció el proveedor (`RESTORE_CMD`, 00:46:49). En un caso real
   sería esperar al proveedor o cambiar a uno alternativo.
3. **Mitigación del daño:** el admin reprocesó las 81 notificaciones `failed`
   (`POST /v1/notifications/{id}/reprocess`, ESC1-08); las 81 respondieron 202 y se entregaron al primer
   intento.

## 7. Comparación antes / durante / después

Fuente: tabla `notifications` de `dev`
([MET-07-incidente-2699b5ea.md](../evidencias/MET-07-incidente-2699b5ea.md) y `.json`). Fase asignada
por hora de aceptación.

### Antes de mitigar

| Fase | Canal | Aceptadas | Entregadas | Fallidas | SLI-2 | Intentos prom. | p50 e2e | p95 e2e |
|---|---|---|---|---|---|---|---|---|
| base | email | 351 | 351 | 0 | 100,0 % | 1,00 | 0,52 s | 0,97 s |
| base | internal | 175 | 175 | 0 | 100,0 % | 1,00 | 0,49 s | 0,93 s |
| **degradación** | **email** | **381** | **300** | **81** | **78,7 %** | **1,94** | **0,99 s** | **16,10 s** |
| degradación | internal | 190 | 190 | 0 | 100,0 % | 1,00 | 0,52 s | 0,97 s |
| recuperación | email | 366 | 366 | 0 | 100,0 % | 1,02 | 0,52 s | 0,99 s |
| recuperación | internal | 183 | 183 | 0 | 100,0 % | 1,00 | 0,50 s | 0,95 s |

### Después de mitigar (reproceso)

| Fase | Canal | Entregadas | Fallidas | SLI-2 | Intentos prom. | p95 e2e |
|---|---|---|---|---|---|---|
| degradación | email | 381 | 0 | 78,7 % | 2,15 | 1324 s |
| demás filas | | sin cambio | 0 | sin cambio | sin cambio | sin cambio |

### Contraste con la hipótesis

| Indicador (correo, degradación) | Hipótesis | Medido | ¿Coincide? |
|---|---|---|---|
| `failed` | 21,6 % | 21,3 % (81/381) | Sí |
| Intentos promedio | 1,96 | 1,94 | Sí |
| SLI-2 | ≈ 78 % | 78,7 % | Sí |
| p95 extremo a extremo | ≈ 15 s | 16,1 s | Sí: 15 s de backoff + espera de sondeo del worker (≤ 1 s por intento) |
| Canal interno | sin cambio | 100 % en las tres fases | Sí: el aislamiento entre canales funciona |
| SLI-1 | sin cambio | 1646 de 1646 aceptadas, sin 5xx | Sí |

Con 381 correos la diferencia de 0,3 puntos en `failed` está dentro de lo esperable por azar: el
intervalo de ±2 desviaciones estándar es 21,6 % ± 4,2 %.

**Presupuesto de error (SLO-B ≥ 95 %).** En la ventana de degradación, el correo tuvo 21,3 % fuera de
objetivo: 4,3 veces el presupuesto. Sobre toda la corrida (1646 notificaciones, 81 fuera de objetivo)
el SLI-2 quedó en 95,1 %: el SLO se cumplió por muy poco, con el 98 % del presupuesto consumido en
5 minutos de degradación. Según la política de [MET-01](MET-01-catalogo-de-indicadores.md), no se
promoverían versiones a `prod` hasta revisar la causa.

**El reproceso no recupera el SLI.** Tras mitigar, las 381 quedaron entregadas, pero el SLI-2 de la
degradación sigue en 78,7 %: las 81 reprocesadas tardaron unos 20 minutos desde la aceptación, y eso es
lo que esperó el usuario. Es el comportamiento buscado del SLI (sección 2 de MET-01): mitigar arregla el
estado, no el tiempo perdido. Por eso los intentos promedio suben de 1,94 a 2,15 (+81/381) y el p95
salta a 1324 s.

## 8. Verificación posterior

- [x] Las 1646 notificaciones de la corrida en estado final; las 81 reprocesadas, `delivered`.
- [x] Fase de recuperación igual a la base en los dos canales (100 %, p95 < 1 s).
- [x] `kubectl -n notifier-dev get deploy/worker -o yaml | grep FAULT` sin resultado: la falla quedó
  revertida.
- [x] VM apagada (`VM deallocated`) al terminar.
- [ ] Alerta resuelta: capturas en [MET-06](MET-06-alertas.md).

## 9. Limitaciones

- **Falla sintética:** se inyecta en el propio worker, no en el proveedor. Es independiente por intento;
  una caída real suele ser correlacionada (todo falla durante un rato), que daría más `failed`.
- **Bordes de fase:** la fase se asigna por hora de aceptación. Los correos aceptados en los 36 s que
  tardó en reiniciarse el worker al quitar la falla todavía los procesó el worker degradado: explica los
  1,02 intentos promedio de la recuperación (≈ 7 reintentos de más) sin ninguna fallida.
- **Activar o quitar la falla reinicia el worker:** cada `set env` provoca un rollout de ≈ 36 s. Además
  se pierden los logs del Pod reemplazado (sección 5): para investigar un incidente pasado hay que
  apoyarse en las trazas o en la tabla `notification_events`.
- **Retención de trazas:** Jaeger guarda en memoria; la traza se exportó a `docs/evidencias/` en el
  momento.
- **Ventanas cortas:** 5 minutos por fase bastan para ver el efecto, pero no son una ventana de SLO
  representativa.
- **Medición desde la base:** los números salen de PostgreSQL y no de Prometheus. Son exactos por
  notificación, pero no muestran la evolución minuto a minuto; para eso están los paneles de MET-05 y
  las alertas de MET-06.
