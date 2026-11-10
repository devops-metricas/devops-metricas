# MET-07: Analizar al menos una degradación inducida y una recuperación.

| | |
|---|---|
| **Responsable** | Camila |
| **Estado** | Parcial: procedimiento probado en local; falta la corrida en `dev` y completar las secciones marcadas ⟨completar⟩ |
| **Evidencia mínima que se revisa** | Secuencia temporal, evidencia, interpretación y limitaciones. |

Cubre la condición 5.11, el punto 8 del Anexo II y la prueba P1-5 del escenario.

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
| CPU del worker | baja | sin cambio relevante | los intentos fallidos son rápidos (503 inmediato), no hay saturación |

Si se cumple, el SLO-B (≥ 95 %) se incumple durante la degradación: el presupuesto de error de la
ventana se agota ((1 − 0,78) / 0,05 ≈ 4,4 veces el presupuesto).

## 3. Procedimiento reproducible

Requisitos: VM encendida, versión vigente desplegada en `dev`, colector y Jaeger instalados
(`scripts/aplicar-observabilidad.sh`), Prometheus y Grafana de Rene funcionando, y las claves de prueba
exportadas en la terminal (nunca en el repo).

```bash
export RESOURCE_GROUP=... VM_NAME=... API_URL=https://<fqdn>/dev API_KEY=ntf_... ADMIN_KEY=ntf_...
export FAULT_CMD='./scripts/vm.sh "k3s kubectl -n notifier-dev set env deploy/worker NOTIFIER_EMAIL_FAULT_RATE=0.6 && k3s kubectl -n notifier-dev rollout status deploy/worker"'
export RESTORE_CMD='./scripts/vm.sh "k3s kubectl -n notifier-dev set env deploy/worker NOTIFIER_EMAIL_FAULT_RATE- && k3s kubectl -n notifier-dev rollout status deploy/worker"'
python scripts/incidente.py      # ≈ 12 minutos: 3 fases de 3 min + espera + reproceso
```

`scripts/incidente.py` envía 2 solicitudes por segundo (2 de cada 3 por correo, 1 interna como grupo de
control) durante tres fases (base, degradación, recuperación), reprocesa las que quedaron `failed` y
calcula los resultados por fase desde la API. Guarda `evidencias/MET-07-incidente-<fecha>.md` y `.json`.

`kubectl set env` sobrescribe la variable del ConfigMap solo en el worker y provoca un reinicio
controlado. `NOTIFIER_EMAIL_FAULT_RATE-` la elimina y vuelve al valor del ConfigMap (0). El siguiente
despliegue normal también lo revierte, porque el manifiesto versionado no tiene la variable.

## 4. Línea de tiempo ⟨completar con la salida del script y Grafana⟩

| Hora (UTC) | Qué pasó | Señal |
|---|---|---|
| | Inicio de la fase base | |
| | Se activa la falla (`FAULT_CMD`) | |
| | Primera señal visible: sube `transient_error` | Panel de intentos por resultado |
| | Se dispara la alerta de Rene (MET-06) | Alertmanager / Grafana |
| | Se quita la falla (`RESTORE_CMD`) | |
| | La tasa de error vuelve a la base; la alerta se resuelve | |
| | Reproceso de las fallidas | `notification_reprocessed` en logs |
| | Verificación: todas `delivered` | Salida del script |

## 5. Detección y diagnóstico

1. **Síntoma:** sube la tasa de error pasajero del correo (I-6) y baja SLI-2.
2. **¿Es el proveedor o somos nosotros?** Se compara por canal: el interno sigue sano y la aceptación
   (SLI-1) no cambia → el problema está después de la cola y solo en el correo.
3. **¿Lento o rechazando?** El p95 de duración de intento (I-7) sigue en milisegundos → el proveedor
   rechaza rápido (503), no hay timeouts. Coincide con los spans `email.send` cortos y en error.
4. **¿Hay atraso de capacidad?** La CPU del worker (I-13) no sube y la antigüedad del pendiente más viejo
   (I-9) solo refleja el backoff → no es falta de capacidad; escalar el worker no ayudaría.
5. **Mecanismo causal:** el proveedor rechaza → el worker reintenta con backoff (5 s, 10 s) → el 60 %
   de los correos tarda más y ≈ 22 % agota los intentos → baja SLI-2.

Evidencia a enlazar ⟨completar⟩:

- Logs de una notificación que agotó sus intentos: `scripts/correlacion.sh <id> dev` (el script de
  incidente imprime tres IDs fallidos al final).
- Traza de esa notificación en Jaeger: tres spans `email.send` en error.
- Consultas antes y después (sección 7).

## 6. Respuesta operativa

1. **Contención:** no se toca la aplicación; el sistema hace lo que debe (reintenta y no pierde nada).
2. **Corrección de la causa:** se restablece el proveedor (`RESTORE_CMD`). En un caso real sería
   esperar al proveedor o cambiar a uno alternativo.
3. **Mitigación del daño:** el admin reprocesa las notificaciones `failed`
   (`POST /v1/notifications/{id}/reprocess`, ESC1-08). No se reprocesan los errores permanentes.

## 7. Comparación antes / durante / después ⟨completar⟩

Consultas en Prometheus (ventanas de 3 min, igual a la duración de cada fase):

```promql
# Tasa de error pasajero del correo
sum(rate(notifier_delivery_attempts_total{channel="email",outcome="transient_error"}[3m]))
  / sum(rate(notifier_delivery_attempts_total{channel="email"}[3m]))

# p95 de extremo a extremo por canal
histogram_quantile(0.95, sum by (le, channel) (rate(notifier_end_to_end_seconds_bucket[3m])))
```

| Indicador | Base | Degradación | Recuperación | Tras reproceso | ¿Coincide con la hipótesis? |
|---|---|---|---|---|---|
| Correos `failed` (%) | | | | | |
| Intentos promedio (correo) | | | | | |
| SLI-2 correo (%) | | | | | |
| p95 extremo a extremo correo (s) | | | | | |
| SLI-2 interno (%) | | | | | |
| SLI-1 (%) | | | | | |
| CPU worker (m) | | | | | |

### Prueba en seco (entorno local, no es la evidencia final)

Se ejecutó el mismo script en local con fases de 20 s, 3 solicitudes/s y backoff de 1 s, para validar el
procedimiento. Resultados (204 solicitudes aceptadas, 2026-11-10 02:13 UTC):

| Fase | Canal | Aceptadas | `failed` antes del reproceso | Intentos promedio | p95 e2e |
|---|---|---|---|---|---|
| base | email | 40 | 1 | 1,05 | 0,98 s |
| degradación | email | 48 | 4 | 1,79 | 3,93 s |
| degradación | internal | 24 | 0 | 1,00 | 1,44 s |
| recuperación | email | 48 | 0 | 1,00 | 1,62 s |

Tras el reproceso, las 204 quedaron `delivered`. Dos observaciones útiles para la corrida real:

- La fase base tuvo 1 correo fallido: se envió segundos antes de activar la falla, pero lo procesó el
  worker ya degradado. Las fases se asignan por **hora de envío**, no de procesamiento (ver
  limitaciones).
- La proporción de `failed` en degradación (8 %) quedó por debajo del 21,6 % esperado porque las fases
  eran muy cortas: muchos reintentos cayeron ya en la fase de recuperación, con el proveedor sano. Con
  fases de 3 min y backoff de 5 s y 10 s el efecto de borde es mucho menor.

## 8. Verificación posterior ⟨completar⟩

- [ ] Todas las notificaciones de la corrida en estado final y las reprocesadas en `delivered`.
- [ ] Tasa de error pasajero y SLI-2 de nuevo en valores de la base.
- [ ] Alerta resuelta.
- [ ] `kubectl -n notifier-dev get deploy/worker -o yaml` sin `NOTIFIER_EMAIL_FAULT_RATE` en `env`.

## 9. Limitaciones

- **Falla sintética:** se inyecta en el propio worker, no en el proveedor. Es independiente por intento;
  una caída real suele ser correlacionada (todo falla durante un rato), que daría más `failed`.
- **Asignación por hora de envío:** una notificación enviada al final de una fase puede procesarse en la
  siguiente. Afecta sobre todo a los bordes de cada fase.
- **Activar la falla reinicia el worker:** `set env` provoca un rollout, con una pausa breve de
  procesamiento que se suma a la degradación. Se ve en la línea de tiempo y no se confunde con ella.
- **Retención:** los logs del Pod anterior al reinicio y las trazas en memoria pueden perderse; por eso
  se exportan en el momento.
- **Ventanas cortas:** 3 minutos por fase bastan para ver el efecto, pero no son una ventana de SLO
  representativa.
