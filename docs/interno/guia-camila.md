# Guía paso a paso: Camila (MET-01, 02, 04, 07, EVIDENCIAS y costos)

Rama: `feat/met-trazas-y-analisis`. Lo que ya está hecho y probado en local, y lo que falta, en orden.

## Qué trae la rama

| Archivo | Para qué |
|---|---|
| `k8s/observability/` | Colector OpenTelemetry 0.114.0 + Jaeger 1.62.0 (namespace `observability`, sin exposición pública). Configuración del colector validada con `otelcol-contrib validate`. |
| `k8s/base/kustomization.yaml` | Una variable nueva: `OTEL_EXPORTER_OTLP_ENDPOINT`. Sin ella la app no exporta trazas. |
| `scripts/vm.sh` | Ejecuta cualquier comando dentro de la VM con `az vm run-command`. |
| `scripts/aplicar-observabilidad.sh` | Instala colector y Jaeger en la VM. |
| `scripts/correlacion.sh` | Dado un `notification_id`: logs de API y worker → `trace_id` → traza en Jaeger. Guarda la evidencia. |
| `scripts/incidente.py` | Incidente controlado completo (MET-07) con línea de tiempo y resultados por fase. |
| `docs/MET/MET-01, 02, 04, 07` | Documentos redactados. Lo que depende del clúster está marcado ⟨completar⟩ o como casilla `[ ]`. |
| `docs/evidencias/MET-0*-local*` | Evidencia real generada en local (logs correlacionados y una traza con reintentos). |
| `docs/DEV/DEV-14-costos.md` | Requests del colector y Jaeger sumados a la tabla de dimensionamiento. |

Probado en local: las 23 pruebas pasan, `ruff` sin errores, kustomize renderiza `observability`, `dev` y
`prod`, la cadena app → colector → Jaeger entrega trazas de ambos servicios, y `incidente.py` corrió de
punta a punta.

## Paso 1. Entender lo que vas a defender (1-2 h, sin VM)

La defensa es individual y sin IA: lee y prueba esto hasta poder explicarlo sin notas.

1. Lee `src/notifier/observability.py` completo y busca dónde se usa cada métrica
   (`grep -rn "NOTIFICATIONS_FINISHED\|END_TO_END" src/`).
2. En `api/app.py`, encuentra la línea `propagate.inject(carrier)`; en `worker/main.py`,
   `propagate.extract(...)`. Esa pareja es **toda** la propagación asíncrona de MET-04.
3. Lee tus cuatro documentos. Para cada SLI, debes poder responder: población, numerador, denominador,
   exclusiones y por qué.
4. Practica la cuenta del presupuesto de error: "con 99,5 % y 2 000 solicitudes, ¿cuántos 5xx tolero?"
   (10) y la hipótesis del incidente: "¿por qué 21,6 %?" (0,6³).

## Paso 2. Probar todo en tu máquina (1 h, sin VM)

```bash
git fetch && git checkout feat/met-trazas-y-analisis
python -m venv .venv && source .venv/bin/activate && pip install -e '.[dev]'
docker compose up -d
export NOTIFIER_DATABASE_URL=postgresql://notifier:notifier@localhost:5432/notifier
python -m notifier.migrate
python -m notifier.cli create-client app-pruebas         # copia la clave
python -m notifier.cli create-client ops --admin         # copia la clave
```

Trazas en local (Jaeger acepta OTLP directo; no hace falta el colector para probar):

```bash
docker run -d --name jaeger -p 16686:16686 -p 4318:4318 jaegertracing/all-in-one:1.62.0
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 NOTIFIER_RETRY_BACKOFF_SECONDS=1
uvicorn notifier.api.app:app --port 8000                          # terminal 1
NOTIFIER_EMAIL_FAULT_RATE=0.7 python -m notifier.worker.main      # terminal 2
```

Envía unas notificaciones de correo y abre http://localhost:16686 → servicio `notifier-api` →
*Find Traces*. Abre una con varios `notification.process`: es la traza de MET-04. Compara con
`docs/evidencias/MET-04-traza-local.txt`.

**Ojo:** las pruebas de integración (`pytest` con `NOTIFIER_DATABASE_URL`) vacían la base; vuelve a
crear las claves después.

## Paso 3. Pull request

1. Revisa el diff completo (`git diff main`) y cambia lo que no te convenza: es tu trabajo.
2. Abre el PR con el título `MET-01/02/04/07: trazas, SLIs e incidente controlado`.
3. Pide revisión a **Diego** (otra área, y es quien mantiene los manifiestos y el pipeline). Explícale
   que el cambio en `k8s/base` agrega una variable al ConfigMap: el próximo despliegue reinicia API y
   worker.
4. Cuando CI esté en verde y esté aprobado, se fusiona y Diego despliega `dev` con *Entrega*.

## Paso 4. Coordinar con Rene antes de la sesión

| Tema | Qué acordar |
|---|---|
| Prometheus | Que recolecte las anotaciones `prometheus.io/*` de `api` y `worker` en `notifier-dev` y `notifier-prod`, y las métricas de cAdvisor (CPU y memoria, I-13 e I-14). |
| Paneles | Que el dashboard incluya SLI-1, SLI-2, I-6 (tasa de error pasajero) e I-9 (pendiente más viejo); tú pones las consultas de MET-01. |
| Alertas | Que una alerta sea por SLI-2 o I-6: es la que tu incidente va a disparar. Acordar umbral y ventana para que dispare en 3 minutos. |
| Grafana + Jaeger (opcional) | Agregar Jaeger como *data source* (`http://jaeger.observability.svc.cluster.local:16686`) para ver trazas desde Grafana. |
| Requests | Que anote los requests de Prometheus y Grafana en `DEV-14-costos.md`. |

## Paso 5. Sesión con la VM (≈ 1,5 h; la VM cobra mientras está encendida)

Prepara todo antes de encender. Alguien con permiso enciende con *Actions → Infra ops*.

```bash
export RESOURCE_GROUP=rg-... VM_NAME=vm-... FQDN=<dns>.northcentralus.cloudapp.azure.com
export API_URL=https://$FQDN/dev
```

| # | Qué | Comando | Guardar como |
|---|---|---|---|
| 1 | Instalar trazas | `./scripts/aplicar-observabilidad.sh \| tee docs/evidencias/MET-04-instalacion.txt` | `MET-04-instalacion.txt` |
| 2 | Confirmar que la app tiene la variable | `./scripts/vm.sh "k3s kubectl -n notifier-dev get cm -o yaml \| grep OTEL"` | — |
| 3 | Claves de prueba (solo en la terminal) | ver `docs/interno/sesion-vm.md`, paso 2 | — |
| 4 | Tráfico | `python scripts/smoke.py batch` | — |
| 5 | Correlación de una notificación con reintentos | `./scripts/correlacion.sh <id> dev` | `MET-02-correlacion-*.txt`, `MET-04-traza-*.json` |
| 6 | Captura de la traza en Jaeger (túnel SSH, ver MET-04 §4) | — | `MET-04-jaeger.png` |
| 7 | SLIs en Prometheus (consultas de MET-01) | — | `MET-01-slis.png` |
| 8 | **Incidente** | `python scripts/incidente.py` (variables en MET-07 §3) | `MET-07-incidente-*.md/.json` |
| 9 | Durante el incidente: capturas del dashboard y de la alerta disparada y resuelta | — | `MET-07-dashboard-*.png`, `MET-07-alerta.png` |
| 10 | Logs y traza de una notificación que agotó intentos | `./scripts/correlacion.sh <id-fallido> dev` | `MET-07-correlacion-*.txt` |
| 11 | Consumo real para costos | `./scripts/vm.sh "k3s kubectl top nodes; k3s kubectl top pods -A"` | `DEV-14-top.txt` |
| 12 | **Apagar la VM** | *Infra ops → deallocate* | — |

Si el incidente sale raro (por ejemplo, no hay `failed`), no repitas a ciegas: anota lo que viste y por
qué; una diferencia bien explicada vale más que una corrida perfecta.

## Paso 6. Completar documentos (sin VM)

1. **MET-01 §5:** valores medidos de SLI-1, 2 y 3 y presupuesto consumido.
2. **MET-04:** marcar las casillas y enlazar los archivos del clúster.
3. **MET-07:** llenar la línea de tiempo (§4), la tabla antes/durante/después (§7) comparando con la
   hipótesis, y la verificación (§8). Si algo no coincide con la hipótesis, explicarlo.
4. **DEV-14-costos.md §3 y §4:** cargos observados desde *Azure Portal → Cost Management → Cost
   analysis*, agrupados por recurso (captura `DEV-14-cargos.png`), y el `kubectl top` del paso 11.
5. **EVIDENCIAS.md:** pasar a *Cubierto* cada requisito con su evidencia del clúster y actualizar el
   resumen.
6. Otro PR, revisado por alguien de otra área.

## Paso 7. Defensa: preguntas probables

| Pregunta | Idea central de la respuesta |
|---|---|
| ¿Por qué tu SLI de entrega excluye los errores permanentes? | Son culpa del dato de entrada; el sistema acierta al no reintentar. Incluirlos castigaría un comportamiento correcto. |
| ¿Qué pasa con una notificación atascada en `pending`? | No baja SLI-2 hasta que termina: por eso se vigila con I-9. Es una limitación declarada. |
| ¿Cómo llega el contexto de traza de la API al worker si no hay HTTP entre ellos? | `traceparent` guardado en la fila; el worker lo extrae y abre un span hijo. |
| ¿Por qué no pones `notification_id` como etiqueta de Prometheus? | Cardinalidad sin límite: una serie por notificación. Va en logs y trazas. |
| ¿Qué es el hueco entre la API y el primer intento en la traza? | Espera en cola (sondeo del worker), no ejecución. No es un span. |
| ¿Cómo sabes que el problema era el proveedor y no la capacidad? | Canal interno sano, SLI-1 sano, intentos rápidos (503 inmediato), CPU del worker sin cambio. |
| ¿Por qué Jaeger en memoria? | Costo cero y memoria acotada; se acepta perder trazas al reiniciar y se exporta la evidencia. |
| ¿Qué pasa si el colector se cae? | La app sigue funcionando: el SDK descarta los lotes que no puede enviar. Se pierden trazas, no notificaciones. |
| ¿Muestreo? | 100 % porque el volumen es bajo; con tráfico real, muestreo en el colector conservando las trazas con error. |
| ¿Qué falsos positivos tendría una alerta por tasa de error pasajero? | Con poco tráfico, pocos fallos dan una tasa alta: exigir un mínimo de intentos en la ventana. |
