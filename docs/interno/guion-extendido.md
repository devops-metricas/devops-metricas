# Guion extendido (material de respaldo, 20 diapositivas)

Versión larga previa. El guion vigente es [guion-presentacion.md](guion-presentacion.md), alineado con el deck de 10 láminas.

Para quien arme las diapositivas (otra instancia de Claude, con este archivo adjunto). Público final: el
docente que evalúa DevOps y Métricas de Software en la defensa.

## Instrucciones para quien arma las diapositivas

- Idioma: español. Tono técnico y directo; frases cortas, sin relleno.
- Una idea por diapositiva. Máximo 5 viñetas de pocas palabras. El detalle va en las notas del orador.
- **No inventar cifras, nombres ni resultados.** Todo número de este guion viene de los documentos del
  repositorio. Donde dice `⟨PENDIENTE⟩`, dejar un recuadro visible con ese texto, no rellenarlo.
- Usar los diagramas y capturas de `docs/evidencias/` indicados en cada diapositiva. No usar
  `DEV-14-cost-analysis.png` ni `DEV-14-presupuesto.png` hasta que estén recortadas (muestran un nombre
  completo, un ID de suscripción y un correo).
- Duración total prevista: unos 20 minutos más la demo. Ajustar si el docente fija otro tiempo.
- Cada diapositiva lleva abajo, en letra pequeña, el ID del requisito que respalda (por ejemplo `DEV-05`).
- Las diapositivas 9b y 13b se insertan después de la 9 y la 13. Numerar de corrido al armar el
  documento (20 en total) y ajustar las referencias del reparto.

## 1. Portada
Notificaciones multicanal (Escenario 1). DevOps y Métricas de Software. Integrantes y fecha.
Notas: presentarse y decir qué se va a mostrar: la solución, cómo se entrega y cómo se observa.

## 2. El problema y el alcance
- Varias aplicaciones notifican a sus usuarios, cada una por su lado.
- Los errores de los proveedores son difíciles de investigar.
- Solución: una plataforma compartida que recibe, ejecuta y permite consultar cada entrega.
- Dos canales: correo de prueba y notificaciones internas. Dos clientes registrados como mínimo.

Notas: el valor está en que **una respuesta HTTP exitosa no es una entrega exitosa**. Esa idea guía el diseño.

## 3. Arquitectura
Usar el diagrama de `docs/COM/COM-02-arquitectura.md`: Internet → NSG e IP pública → VM con K3s →
namespaces `notifier-dev` y `notifier-prod`, cada uno con API, worker, Mailpit y PostgreSQL.
- API (FastAPI): autentica, valida, guarda y responde `202`.
- Worker: entrega, registra intentos, reintenta.
- PostgreSQL: fuente de verdad y también la cola.
- Un solo nodo; dev y prod separados por namespace. **COM-02**

## 4. Qué pasa con una notificación
Diagrama de estados: `pending` → `processing` → `delivered`; reintento vuelve a `pending`; `failed`;
reproceso por un admin.
- `202` = recibida y registrada, no entregada.
- Hasta 3 intentos, espera de 5 s y 10 s entre ellos.
- Error permanente (destinatario inválido): no se reintenta.
- Cada transición e intento queda registrado y se consulta por API. **ESC1-05 a 08**

## 5. Decisiones y compromisos
Tabla de tres columnas: decisión, por qué, qué se acepta.
- Cola en PostgreSQL | una pieza menos y estado y trabajo en una transacción | rendimiento limitado por la base.
- Una sola imagen para API, worker y migraciones | se construye una vez y se promueve | un solo artefacto para todo.
- K3s en un nodo | cabe en US$100 | sin alta disponibilidad.
- Semántica "al menos una vez" | un trabajo no se pierde si el worker muere | un correo podría repetirse.
**COM-06**

## 6. Idempotencia y control de acceso
- Clave por (cliente, canal, clave): repetir devuelve la original (`200`); otro contenido da `409`.
- Funciona también con repeticiones simultáneas: lo garantiza un índice único en la base.
- Clave de API con hash SHA-256; se muestra una sola vez.
- Un cliente solo ve lo suyo; `reprocess` y `stats` son solo para `admin`. **ESC1-02, 09; COM-05**

## 7. Contenedores y CI
- Una imagen, usuario no root, etiquetada con el SHA del commit.
- En cada PR: `ruff`, formato, `pytest` y construcción de la imagen.
- `main` protegido: no se integra si falla el CI.
Capturas: `DEV-03-ci-en-verde.png` y `DEV-03-pr-bloqueado.png`. **DEV-02, 03**
Notas: decir con honestidad que el CI aún no escanea vulnerabilidades de la imagen.

## 8. Entrega controlada y rollback
- Al publicar en `main`: despliega a **dev** solo y verifica `/readyz`; **prod** espera aprobación.
- Se despliega el SHA del commit, nunca `latest`.
- Rollback: volver a desplegar un SHA anterior. La versión sana atiende mientras la nueva falla (readiness).
- El rollback no restaura datos.
- **Qué versión corre:** la etiqueta de la imagen del Deployment es el SHA del commit; se relaciona con el
  workflow que la construyó y con la etiqueta OCI `revision` de la imagen. Mostrar el SHA en el clúster y
  enlazarlo a su commit.
Capturas: `DEV-05-dev.png`, `DEV-05-aprobacion.png`, `DEV-05-prod.png`. **DEV-02, 04, 05, 12**
Evidencia de trazabilidad: `docs/evidencias/DEV-02-etiqueta-revision.txt`.

## 9. Infraestructura con Terraform
- Recursos de Azure definidos en código: red, IP estática, NSG, VM, apagado automático y presupuesto.
- K3s se instala solo en el primer arranque (cloud-init), con cifrado de Secrets.
- En un PR: `fmt`, `validate` y `plan`. Solo se aplica en `main` con aprobación.
- Estado remoto en Azure, sin llaves.
Capturas: `DEV-06-plan.png`, `DEV-08-pr-plan.png`, `DEV-08-apply-aprobacion.png`. **DEV-06, 07, 08**

## 9b. Reproducibilidad: reconstrucción, pasos manuales y HTTPS
- Reconstruir el ambiente: `destroy` y luego `apply` desde *Infra ops*, sin pasos ocultos.
- Tiempos medidos: `destroy` 2 min 17 s; `apply` 1 min 31 s; K3s con el nodo `Ready` en unos 2 min;
  certificado emitido 34 s después de aplicar la configuración de Traefik.
- El nombre DNS no cambia al reconstruir, así que el certificado y las URL sobreviven.
- **Intervenciones manuales, declaradas y justificadas:** el bootstrap (una sola vez: crea las identidades
  y el almacenamiento del estado que el pipeline necesita para existir), la configuración de GitHub y
  `kubectl apply -f k8s/platform/traefik-acme.yaml` tras el `apply`.
- HTTPS: certificado de Let's Encrypt (HTTP-01) emitido por Traefik, con el nombre DNS de Azure de la IP
  estática; rutas `/dev` y `/prod` bajo el mismo nombre.
Evidencia: `docs/evidencias/DEV-13-reconstruccion.txt`. **DEV-13**
`⟨PENDIENTE: despliegue de la aplicación sobre el clúster reconstruido⟩`
Notas: es la respuesta a "¿puede otra persona recrear esto desde cero?" (rúbrica: Reproducibilidad).

## 10. Identidades y seguridad
- GitHub entra a Azure por OIDC: no hay contraseñas guardadas.
- Tres identidades de mínimo privilegio: `plan` (Reader, para PRs), `infra` (Contributor, solo `main`),
  `deploy` (Virtual Machine Contributor).
- Red: solo 80 y 443 abiertos; SSH desde una IP; la API de Kubernetes (6443) cerrada.
- Secretos fuera del repositorio y de la imagen. **DEV-10, COM-05**
Notas: explicar que un Secret de Kubernetes no es cifrado por sí solo y qué protege `--secrets-encryption`
(el almacén) y qué no (a quien administre el clúster).

## 11. Kubernetes: salud y recursos
Tabla de probes y recursos reales.
- API: readiness `/readyz` (depende de la base), liveness `/healthz` (solo el proceso).
- Requests 50m y 96Mi (API y worker); sin límite de CPU, límite de memoria de 256Mi.
- Medido con 100 solicitudes: CPU máxima de 37m en la API; nodo al 21 % de memoria.
- PostgreSQL con volumen persistente de 5 Gi. **DEV-09, 11; COM-03**

## 12. Costos
- Tope de US$100. Con la VM apagada quedan unos US$8,40 al mes.
- Medidas: apagar cada sesión, apagado a las 23:00, alertas de presupuesto al 50, 80 y 100 %.
- Las alertas solo notifican: no detienen nada.
- Cargo observado en noviembre: US$2,80 en el grupo del proyecto. **DEV-14**
Gráfico opcional: costo fijo vs. cómputo según horas de uso (datos del documento DEV-14).

## 13. Medición: preguntas, SLIs y SLOs
- Tres preguntas operativas: entrega dentro de 30 s, qué dependencia causa los retrasos, si el worker da abasto.
- SLI-1 disponibilidad de la aceptación; SLI-2 entrega oportuna (≤ 30 s); SLI-3 latencia (≤ 500 ms).
- SLO-A ≥ 99,5 % y SLO-B ≥ 95 %, con presupuesto de error calculado.
- Medición real en el clúster (corrida del incidente, `dev`): SLI-1 100 % (1646/1646); SLI-2 95,1 %
  (1565/1646), con 78,7 % en el correo durante los 5 min de degradación. SLI-3 no se midió en esa corrida
  (decirlo si preguntan). **MET-01 §5**

## 13b. Cobertura del escenario
Tabla compacta con una marca por requisito y su prueba.
- ESC1-01 a 10 (clientes, autenticación, solicitudes, canales, estados, intentos, reintentos, reproceso,
  idempotencia, recuentos): implementados, con prueba automática. Referencia: `docs/ESC1/ESC1-requisitos.md`.
- P1-1 carga de 100: pasa en local y en el clúster.
- P1-2 dependencia degradada: pasa en local y en el clúster.
- P1-3 idempotencia secuencial y concurrente: pasa en local y en el clúster.
- P1-4 recuperación al reiniciar el worker: pasa en local y en el clúster.
- P1-5 correlación de extremo a extremo y alerta: pasa en `dev`. La notificación `02e7bade…` se sigue por
  log y por la traza `863f3fdb…`, y la alerta se dispara y se resuelve (MET-07, MET-04, MET-06).
**ESC1**
Notas: mostrar de un vistazo qué parte del escenario está probada. Estado: 28 de 28 requisitos cubiertos.

## 14. Observabilidad en acción
- Nueve métricas de aplicación; dashboard con ocho paneles, cada uno con unidad y ventana.
- Logs estructurados con identificador de notificación para correlacionar.
- Trazas con OpenTelemetry: la traza continúa de la API al worker aunque la entrega sea asíncrona.
- Dos alertas: más del 20 % de intentos fallidos, y pendiente más viejo de más de 30 s.
- **Todo versionado:** el dashboard se carga desde un JSON, las alertas viven en `monitoring/alerts.yml` y
  los manifiestos del monitoreo están en `k8s/monitoring`. Si se reconstruye el ambiente, se restablecen
  con los mismos archivos, sin pasos manuales.
Capturas: `MET-05-dashboard-superior.png`, `MET-05-dashboard-inferior.png`. **MET-02 a 06**
Trazas y logs ya instalados y consultados en `dev`: ejemplo real, traza `863f3fdb…` de la notificación
`02e7bade…` (MET-04, MET-07). Hallazgo para contar: los logs solos no bastaron para el diagnóstico.
Notas: mencionar la limitación de la alerta de cola (no avisa si el worker está caído).

## 15. Incidente controlado
- Falla inducida: el proveedor de correo responde 503 en el 60 % de los envíos.
- Hipótesis previa: unos 21,6 % de correos terminan `failed`, el canal interno no cambia.
- Secuencia: base → degradación → recuperación; alerta, diagnóstico con métricas, logs y trazas, mitigación.
- Corrida real en `dev` (run `2699b5ea`): SLI-1 se mantuvo en 100 %; SLI-2 bajó a 78,7 % en el correo
  durante la degradación y cerró en 95,1 % global (1565/1646). La alerta de fallos disparó y se resolvió;
  `NotifierQueueDelayHigh` no disparó (la cola no llegó a 30 s). **MET-07**
- Comparar con la hipótesis (21,6 % `failed`, 1,96 intentos): la comparación medida está en MET-07 §
  comparación; leerla antes de la defensa.
Capturas: `MET-07-dashboard-*.png` (incidente en `dev`) y `MET-06-k3s-alerta-*.png` (alerta en K3s).

## 16. Demo en vivo
Requiere la VM encendida. Orden sugerido (cada paso con resultado esperado):
1. Enviar una notificación y mostrar su `202`, su estado y su historial de intentos.
2. Repetir la misma clave de idempotencia: misma notificación, `200`.
3. Lote de 100 solicitudes: `python scripts/smoke.py batch`.
4. Degradar el correo: `python scripts/smoke.py email-degraded`; el canal interno sigue funcionando.
5. Reiniciar el worker con trabajos pendientes: `python scripts/smoke.py recovery`; no se pierde ninguno.
6. Mostrar el dashboard durante el paso 3 o 4.
7. Acceso rechazado: `python scripts/smoke.py access`; una clave inválida da `401` y un cliente sin rol
   `admin` recibe `403` en `reprocess`.
8. Persistencia: anotar `GET /v1/stats`, borrar el Pod de PostgreSQL para que Kubernetes lo recree y
   comprobar que los recuentos son iguales (evidencia previa: `COM-03-stats-antes.txt` y
   `COM-03-stats-despues.txt`).
Plan B si algo falla: usar las capturas y los archivos de `docs/evidencias/`.
Notas: al terminar, apagar la VM (`Infra ops` → `deallocate`).

## 17. Límites y siguientes pasos
- Un solo nodo y una réplica: sin alta disponibilidad.
- Semántica "al menos una vez"; Secrets legibles por quien administre el clúster.
- El correo no se probó con carga en la VM; la imagen no se escanea en el CI.
- Estado final: los 28 requisitos están cubiertos. Límites que quedan: SLI-3 no medido en la corrida, la
  alerta de cola no disparó en el incidente, la carga fue solo por el canal interno desde un PC, imagen sin
  escanear ni fijada por digest.
Notas: reconocer los límites con claridad; el enunciado lo pide y el docente lo valora.

## 18. Cierre
Resumen en tres frases: se recibe y registra sin perder datos, se entrega con reintentos y se puede
investigar cada fallo con evidencia. Preguntas.

## Quién presenta cada diapositiva
Reparto parejo: unos 5 minutos por persona, para unos 20 minutos más la demo. Las diapositivas de su
propia área, según [reparto.md](reparto.md), se marcan con ✔; las demás (marcadas con ↔) las estudia
con la guía [guia-defensa.md](guia-defensa.md), y quien es dueño del tema le explica antes de la entrega.

| Quién | Diapositivas | Tiempo |
|---|---|---|
| **Melissa** | 1 portada ✔, 2 problema ✔, 3 arquitectura ✔, 4 ciclo de una notificación ✔, 9 Terraform ✔, 9b reproducibilidad ✔ | ≈ 6,5 min |
| **Diego** | 7 contenedores y CI ✔, 8 entrega, rollback y versión desplegada ✔, 10 identidades y seguridad ✔, 11 Kubernetes ✔ | ≈ 5,5 min |
| **Rene** | 5 decisiones ↔, 12 costos ↔, 14 observabilidad ✔ | ≈ 4,5 min |
| **Camila** | 6 idempotencia y acceso ↔, 13 SLIs y SLOs ✔, 13b cobertura del escenario ✔, 15 incidente controlado ✔, 17 límites ↔, 18 cierre ↔ | ≈ 6,5 min |

**Demo (diapositiva 16), por pasos:**

| Paso | Quién |
|---|---|
| 1 y 2: una notificación e idempotencia | Melissa |
| 3: lote de 100 solicitudes | Diego |
| 4 y 5: correo degradado y reinicio del worker | Camila |
| 6: dashboard en vivo durante los pasos 3 a 5 | Rene |
| 7: acceso rechazado | Rene |
| 8: persistencia (borrar el Pod de PostgreSQL) | Diego |

Antes de la defensa, ensayar una vez completa con la VM encendida. Como la defensa individual puede
abordar cualquier parte, cada quien debe poder contestar sobre las diapositivas de los demás: usar la
guía de estudio [guia-defensa.md](guia-defensa.md) para eso.
