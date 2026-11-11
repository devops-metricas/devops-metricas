# Guion de la presentación

Sigue el deck de 10 láminas (Artifact "Notificaciones multicanal - Defensa", en orden). El docente pidió
diagramas de la arquitectura y demostraciones en vivo, así que el peso está en los diagramas y la demo.
La versión larga de 20 diapositivas quedó como respaldo en [guion-extendido.md](guion-extendido.md).

Duración prevista: ≈ 14 min de láminas + ≈ 6 min de demo = unos 20 min.
Cada lámina trae las notas del orador en el propio deck; aquí va el resumen, quién la presenta y los datos.

## Reparto

| # | Lámina | Quién | Min | Respalda |
|---|---|---|---|---|
| 1 | Portada | Melissa | 0,5 | COM-02 |
| 2 | Arquitectura | Melissa | 1,5 | COM-02 |
| 3 | Ciclo de una notificación | Melissa | 1,5 | ESC1-05 a 09 |
| 4 | Infraestructura | Diego | 2 | DEV-06, 07, 09, 13 |
| 5 | Entrega controlada | Diego | 2 | DEV-03, 04, 05, 12 |
| 6 | Observabilidad | Rene | 2 | MET-03 a 06 |
| 7 | Objetivos de servicio | Camila | 2 | MET-01 |
| 8 | Costos | Rene | 1,5 | DEV-14 |
| 9 | Demostración en vivo | Todos | ≈ 6 | ESC1, COM |
| 10 | Límites conocidos | Camila | 1,5 | COM-06 |

Ensayo: una corrida completa con la VM encendida. Cada quien estudia las láminas de los demás con
[guia-defensa.md](guia-defensa.md), porque la defensa es individual.

## 1. Portada (Melissa)
Una frase: plataforma que recibe solicitudes de notificación, las guarda y las entrega por correo o canal
interno, con reintentos, desplegada y observada de forma reproducible.

## 2. Arquitectura (Melissa)
Cliente → Traefik (HTTPS) → API → PostgreSQL ← worker → correo o canal interno.
- La API no envía nada: guarda y responde `202` (recibida, no entregada).
- El worker lee la cola de PostgreSQL (`FOR UPDATE SKIP LOCKED`).
- Mensaje clave: la entrega es asíncrona, por eso sobrevive a caídas del worker.

## 3. Ciclo de una notificación (Melissa)
- `pending` → worker toma → intento → `delivered`.
- Reintento transitorio: espera de 5 s y luego 10 s, hasta 3 intentos; si se agotan, `failed`.
- Error permanente (`@invalid.test`, SMTP 5xx): `failed` sin reintentar.
- Idempotencia: misma solicitud → `200`; misma clave con otro contenido → `409`.
- Un admin reprocesa solo las `failed`. Semántica "al menos una vez".

## 4. Infraestructura (Diego)
- Una VM de Azure con K3s; namespaces `notifier-dev` y `notifier-prod`, más `monitoring` y `observability`.
- Traefik con Let's Encrypt. Red: 80 y 443; SSH solo desde la IP de administración; 6443 cerrado.
- Terraform con estado remoto en Azure; único paso manual: el bootstrap inicial (y aplicar
  `k8s/platform/traefik-acme.yaml` tras reconstruir).
- Reconstrucción medida: `destroy` 2 min 17 s, `apply` 1 min 31 s, K3s listo en ≈ 2 min, certificado en 34 s.

## 5. Entrega controlada (Diego)
- PR: ruff, pytest y construcción de la imagen; `main` protegido.
- Merge: imagen en GHCR con el SHA del commit (así se sabe qué versión corre). Dev se despliega solo;
  prod espera aprobación.
- Rollback: entrega manual con el SHA anterior; no restaura datos.
- Terraform: `plan` en el PR con identidad de solo lectura; `apply` solo en `main` con aprobación. OIDC, sin
  secretos de larga duración.

## 6. Observabilidad (Rene)
- Nueve métricas de aplicación; Prometheus lee cada 15 s; Grafana con dashboard de 8 paneles.
- Trazas: API y worker → OTel Collector → Jaeger; el `traceparent` se guarda con la notificación.
- Alertas: más de 20 % de intentos fallidos; pendiente más viejo de más de 30 s. Todo versionado.
- Evidencia real en `dev` (incidente controlado, run `2699b5ea`): la alerta de fallos pasó por pending,
  firing y se resolvió. Una notificación (`02e7bade…`) se siguió por log y por la traza `863f3fdb…`.
- Decir: los logs solos no bastaron para el diagnóstico; hicieron falta métricas y trazas. La alerta de cola
  no disparó (la cola nunca llegó a 30 s) y no avisa si el worker está caído.

## 7. Objetivos de servicio (Camila)
- SLI-1 aceptación (2xx / (2xx + 5xx)), SLO ≥ 99,5 %. SLI-2 entrega en ≤ 30 s (sin errores permanentes),
  SLO ≥ 95 %. SLI-3 latencia de aceptación ≤ 500 ms, sin SLO. Ventana de 7 días (1 h en la demo).
- Medido en el incidente en `dev`: SLI-1 100 % (1646/1646); SLI-2 95,1 % (1565/1646), con 78,7 % en el
  correo durante los 5 min de degradación. SLI-3 no se midió en esa corrida.
- Hipótesis previa: ≈ 21,6 % de correos `failed` (0,6³) y el canal interno sin cambios. La comparación
  medida está en MET-07; leerla antes de la defensa.

## 8. Costos (Rene)
- VM apagada: ≈ US$8,40 al mes (disco e IP). Encendida 24 h todo el mes: US$62,54. Plan real: US$17 a 27.
- Presupuesto `budget-notifier` de US$100 con alertas al 50, 80 y 100 %; solo notifican.
- VM se apaga cada sesión y a las 23:00. Observado al 10 de noviembre: US$2,80 en `rg-notifier`.

## 9. Demostración en vivo (todos)
Requiere la VM encendida. Respaldo: capturas en `docs/evidencias/`.

| Paso | Qué se muestra | Quién |
|---|---|---|
| 1 y 2 | Una notificación (`202`, estado, intentos) y la repetición idempotente (`200`) | Melissa |
| 3 | Lote de 100: `python scripts/smoke.py batch` | Diego |
| 4 y 5 | Correo degradado (`email-degraded`) y reinicio del worker (`recovery`) | Camila |
| 6 | Dashboard en vivo durante los pasos 3 a 5 | Rene |
| 7 | Acceso rechazado: `smoke.py access` (`401`; `403` en `reprocess` sin rol admin) | Rene |
| 8 | Persistencia: anotar `GET /v1/stats`, borrar el Pod de PostgreSQL y comparar | Diego |

Al terminar, apagar la VM (`Infra ops` → `deallocate`).

## 10. Límites conocidos (Camila)
- Un solo nodo y una réplica: sin alta disponibilidad (decisión de costo; reconstrucción en ≈ 2 min).
- "Al menos una vez": la idempotencia protege la entrada, no el envío. Secrets legibles por quien
  administre el clúster.
- Imagen sin escanear en el CI y base sin fijar por digest.
- Carga solo por el canal interno y desde un PC; SLI-3 no medido; alerta de cola no probada en disparo.
- Estado: 28 de 28 requisitos cubiertos. Cierre en una frase y preguntas.
