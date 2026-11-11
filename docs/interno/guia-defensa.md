# Guía de estudio para la defensa

Cada afirmación de esta guía se verificó contra el código, los manifiestos, los workflows o los
documentos del repositorio, y lleva su fuente entre paréntesis para poder comprobarla. Si algo cambia en
el código, esta guía debe actualizarse: no se fíe de ella sin mirar la fuente.

La defensa es individual y puede abordar cualquier componente, aunque lo haya hecho otra persona
(enunciado, sección 7). No se permite IA. Lo que cuenta es explicar con autonomía qué pasa, por qué, qué
límite tiene y cómo se comprueba.

Estado de las evidencias: [../EVIDENCIAS.md](../EVIDENCIAS.md). La sección 9 de esta guía dice qué está
demostrado en el clúster y qué todavía no.

## 1. La solución en un minuto

Una plataforma que recibe solicitudes de notificación de aplicaciones cliente, las guarda de forma
durable, las entrega por dos canales (correo de prueba e interno) y permite consultar el resultado.

- **API** (FastAPI): autentica, valida, aplica idempotencia, guarda la notificación como `pending` y
  responde `202` (`src/notifier/api/app.py`).
- **Worker**: toma trabajos de la cola, entrega, registra cada intento y reintenta o termina
  (`src/notifier/worker/main.py`).
- **PostgreSQL**: única fuente de verdad y también la cola.
- **Mailpit**: servidor SMTP de pruebas para el canal de correo.
- Todo corre en **K3s de un solo nodo** en una VM de Azure; **dev y prod son namespaces**
  (`notifier-dev`, `notifier-prod`) del mismo manifiesto base.

Idea central: **`202` significa "recibida y registrada", no "entregada"**. La entrega es asíncrona.

## 2. Aplicación

### Ciclo de vida de una notificación

`pending` → el worker la reclama → `processing` → `delivered`; o vuelve a `pending` con espera si el
error es transitorio y quedan intentos; o `failed` si el error es permanente o se agotan los intentos.
Cada transición queda en `notification_events` y cada intento en `delivery_attempts`
(`worker/main.py`, función `_finish`).

### La cola vive en PostgreSQL

- El worker reclama con `FOR UPDATE SKIP LOCKED ... LIMIT 1`, ordenando por `next_attempt_at, created_at`
  (`worker/main.py`, `CLAIM_SQL`). Dos workers no toman el mismo trabajo.
- Es elegible un trabajo `pending` con `next_attempt_at <= now()`, **o** uno `processing` cuyo
  `locked_until` ya venció.
- El reclamo hace tres cosas en una sola sentencia: cambia a `processing`, **suma 1 a `attempts`** y fija
  `locked_until = now() + 60 s`.
- El worker consulta cada 1 s (`poll_interval_seconds`, `config.py`).
- **Descartado:** Redis, RabbitMQ y Service Bus, por ser otra pieza que operar y pagar (COM-06).
- **Se acepta:** el rendimiento depende de PostgreSQL.

### Si el worker muere a mitad de un intento

El trabajo queda `processing`. Cuando pasan 60 s de `locked_until`, otro reclamo lo recupera y lo anota
como "recuperado: el worker anterior no terminó". Consecuencias, que son las que preguntan:

- **El intento interrumpido cuenta**, porque `attempts` ya se había incrementado al reclamar. Un trabajo
  puede perder un intento de sus tres por una caída.
- **Semántica "al menos una vez":** si el correo ya había salido y el worker murió antes de guardar el
  resultado, se reenvía. No se garantiza "exactamente una entrega externa"; el enunciado lo admite.
- Los estados no se pierden porque están en la base, no en memoria.

### Reintentos y tipos de error

- `max_attempts = 3` cuenta el intento inicial más dos reintentos (`config.py`).
- Espera tras fallar el intento *n*: `5 s × 2^(n−1)`, es decir 5 s tras el primero y 10 s tras el segundo
  (`backoff_seconds`). La espera evita presionar a un proveedor que ya falla.
- **Permanente** (no se reintenta, termina `failed`): destinatario del dominio `@invalid.test`, o una
  respuesta SMTP 5xx (`channels/email.py`).
- **Transitorio** (se reintenta): respuesta SMTP no 5xx, errores de conexión o timeout (`OSError`) y,
  además, **cualquier excepción inesperada**, que se trata como transitoria para no perder el trabajo.
- El canal interno no usa el proveedor: guarda el mensaje y marca `delivered` en la misma transacción.

### Reproceso

`POST /v1/notifications/{id}/reprocess`, solo rol `admin`, solo si el estado es `failed` (si no, `409`).
Devuelve la notificación a `pending` y **le concede `max_attempts` intentos más** (`max_attempts =
attempts + 3`). **No reinicia `attempts`**: el historial y la numeración se conservan
(`repository.reprocess_failed`).

### Idempotencia

- Índice único parcial por (`client_id`, `channel`, `idempotency_key`) donde la clave no es nula
  (`migrations/001_init.sql`, `notifications_idempotency_uq`).
- Repetir con los mismos datos devuelve la notificación original con **`200`** y
  `idempotent_replay: true`. La solicitud nueva devuelve `202`.
- Misma clave con contenido distinto (hash distinto) devuelve **`409`** (`app.py`).
- Funciona también con repeticiones concurrentes porque el índice único es atómico.
- No caduca: cumple de sobra las 24 horas del enunciado. **Se acepta** que la clave no se pueda
  reutilizar nunca para el mismo cliente y canal.

### Control de acceso

- Cada cliente tiene una clave `ntf_...` generada con `secrets.token_urlsafe(32)`. En la base solo se
  guarda su **SHA-256** (`security.py`); la clave se muestra una vez al crear el cliente.
- SHA-256 y no bcrypt porque la clave es aleatoria de 256 bits (no hay diccionario que probar) y el hash
  rápido permite buscar por hash en cada solicitud (COM-06).
- Sin cabecera: `401 falta el encabezado X-API-Key`. Clave que no existe: `401 credencial inválida`.
  Rol insuficiente: `403`.
- Un cliente que no es `admin` solo ve lo que él originó: aplica a `GET /v1/notifications/{id}` y a
  `/v1/inbox/{recipient}`. `/v1/stats` y `/reprocess` son solo `admin`.

## 3. Contenedores y CI/CD

### Imagen

- Una sola imagen para API, worker y migraciones: cambia el comando (`Dockerfile`).
- Build en dos etapas sobre `python:3.12-slim`, usuario no root (UID 10001), etiqueta OCI
  `org.opencontainers.image.revision` con el SHA del commit y variable `NOTIFIER_GIT_SHA`.
- **Límite que hay que reconocer:** el CI no escanea la imagen en busca de vulnerabilidades y la imagen
  base no está fijada por digest.

### CI (`.github/workflows/ci.yml`)

En cada PR y en cada push a `main`: `ruff check`, `ruff format --check`, `pytest` y `docker build`.
Permisos: solo `contents: read`. `main` está protegido y bloquea el merge si el CI falla (DEV-03).

### Publicación (`publicar-imagen.yml`)

En cada push a `main` construye y sube la imagen a GHCR con el `GITHUB_TOKEN`. Único permiso extra:
`packages: write`. La etiqueta es el SHA del commit; así se relaciona lo que corre con el commit y el
workflow.

### Entrega (`entrega.yml`)

- Se dispara cuando `Publicar imagen` termina bien en `main` (`workflow_run`), o a mano con un SHA
  (`workflow_dispatch`, solo desde `main`).
- Despliega primero a **dev** (entorno `dev`), espera el rollout de `api` y `worker` y comprueba `/readyz`
  por HTTPS. **prod** va después y exige la **aprobación** del entorno `prod`.
- Si la VM está apagada, el despliegue automático se omite en lugar de fallar.
- El manifiesto se aplica dentro de la VM con `az vm run-command`, porque la API de Kubernetes (6443) no
  se expone. Identidad `deploy`, solo Virtual Machine Contributor.
- Los overlays dejan `newTag: latest` en el repositorio; el pipeline escribe el SHA al desplegar
  (comentario en `k8s/overlays/dev/kustomization.yaml`).

### Rollback

Volver atrás es volver a ejecutar `Entrega` con un SHA anterior: no se reconstruye nada. La versión sana
sigue atendiendo mientras la nueva falla porque la readiness impide que un pod defectuoso reciba tráfico;
el paso `rollout status` hace fallar el workflow y señala el despliegue malo (DEV-12). **El rollback del
Deployment no restaura datos.** Las migraciones corren en un `initContainer` con bloqueo consultivo.

## 4. Infraestructura (Terraform)

- **Recursos** (`infra/terraform/main.tf`): grupo de recursos, red, IP pública estática con etiqueta DNS,
  NSG, VM Ubuntu, apagado automático y presupuesto de suscripción.
- **K3s** se instala en el primer arranque con cloud-init: versión fijada, `--secrets-encryption` y
  `--tls-san <fqdn>` (`cloud-init.yaml.tftpl`).
- **Red:** el NSG permite 80 y 443 desde Internet y 22 solo desde `admin_cidr`. El resto cae en
  `DenyAllInbound`, así que el puerto 6443 no es alcanzable.
- **Autenticación de la VM:** solo clave SSH (`disable_password_authentication = true`).
- **Workflow `terraform.yml`:** `terraform fmt -check`, `init -backend=false` y `validate`; luego `plan`.
  En un PR el `plan` usa la identidad `plan` (Reader). El `apply` solo corre con un push a `main` y exige
  el entorno `infra` (aprobación). Un solo plan o apply a la vez (`concurrency: terraform`); el candado del
  estado es la segunda barrera.
- **Estado remoto:** backend `azurerm` en una cuenta de almacenamiento con versionado y acceso por Entra ID,
  sin llaves. Lo crea `infra/bootstrap/bootstrap.sh`, que es la única intervención manual inicial: crea las
  identidades y el almacenamiento que el pipeline necesita para existir.
- **OIDC y tres identidades:**

  | Identidad | Permiso | Uso |
  |---|---|---|
  | `infra` | Contributor | Solo `main` y el entorno `infra` |
  | `plan` | Reader | Pull requests: un PR puede editar el workflow, por eso no escribe |
  | `deploy` | Virtual Machine Contributor | Entornos `dev` y `prod` |

- **Secretos de GitHub:** la IP de administración y los correos son *secrets*, no variables.

## 5. Kubernetes y operación

- **Ambientes:** mismo manifiesto base (`k8s/base`) con un overlay por ambiente. Cada ambiente tiene su
  propia base de datos y su propio Mailpit. Qué versión corre en cada uno lo dice la etiqueta de la imagen
  (el SHA).
- **Configuración:** ConfigMap `notifier-config` (generado con kustomize). Secretos: `notifier-secrets`
  (`database-url`, `postgres-password`), **no versionado**, creado por `crear-secretos.yml`, que no
  imprime valores ni pisa un Secret existente.
- **Qué protege el cifrado de Secrets y qué no:** en Kubernetes un Secret es base64. Con
  `--secrets-encryption` se cifra en el almacén de K3s, pero **quien tenga acceso de administrador a la VM
  puede leerlo**.
- **Persistencia:** PostgreSQL es un StatefulSet con `volumeClaimTemplate` de 5 Gi. Un reinicio del Pod no
  pierde datos.
- **Seguridad de los Pods:** `runAsNonRoot`, `seccompProfile: RuntimeDefault`,
  `allowPrivilegeEscalation: false`, `readOnlyRootFilesystem: true` y `capabilities: drop: [ALL]`
  (`k8s/base/api.yaml`).
- **Red:** servicios internos; Traefik enruta `/dev` y `/prod` bajo el mismo nombre, con certificado de
  Let's Encrypt (HTTP-01).

### Probes (valores reales de los manifiestos)

| Workload | Probe | Configuración | Por qué |
|---|---|---|---|
| `api` | readiness `/readyz` | cada 5 s, falla tras 2 | Comprueba la base: sin PostgreSQL el pod sale de rotación |
| `api` | liveness `/healthz` | espera 10 s, cada 10 s | Solo el proceso: una caída de la base **no** debe reiniciar la API |
| `worker` | liveness `/metrics` | — | No recibe tráfico; no hay readiness que aplicar |
| `postgres` | readiness `pg_isready` | cada 5 s | Recibe tráfico solo cuando acepta conexiones |
| `postgres` | liveness `pg_isready` | espera 20 s, cada 10 s | Reinicia si deja de responder |

Si falla la readiness de una réplica: el Service deja de enviarle tráfico, pero el pod **no** se reinicia.
Si falla la liveness: kubelet reinicia el contenedor.

### Recursos

| Componente | Request | Límite |
|---|---|---|
| `api` y `worker` | 50m CPU, 96Mi | solo memoria: 256Mi |
| `postgres` | 100m CPU, 256Mi | solo memoria: 512Mi |

**No hay límite de CPU**, a propósito, para evitar el *throttling* que añade latencia; el límite de
memoria acota una fuga. Si un contenedor supera su límite de memoria, el kernel lo mata (`OOMKilled`) y
kubelet lo reinicia. Si supera su request de CPU, no pasa nada mientras el nodo tenga CPU libre.

Consumo observado (DEV-11, 2026-11-09, 100 solicitudes): CPU máxima de 37m en la API y 26m en el worker;
memoria de 39 a 54 Mi; nodo al 21 % de memoria. Es una carga ligera: valida que los valores no están por
debajo del uso, no que sean los óptimos.

### Diagnosticar un Pod que no inicia

`kubectl get pods -n <ns>` (estado), `kubectl describe pod` (eventos) y `kubectl logs` (la causa dentro
del proceso). Pistas: `ImagePullBackOff` es la imagen; `CreateContainerConfigError` suele ser un Secret o
ConfigMap que falta; `Pending` suele ser falta de recursos; `CrashLoopBackOff` es el proceso que termina.

## 6. Costos

Tope de US$100. Con precios de lista: VM US$0,0752/h, disco US$4,80/mes, IP US$3,60/mes. Con la VM
apagada quedan unos US$8,40 al mes. Medidas: apagar al terminar cada sesión, apagado automático a las
23:00, presupuesto con alertas al 50, 80 y 100 % y `destroy` al terminar (DEV-14).

- **Las alertas de presupuesto solo notifican; no detienen nada.**
- Una VM desasignada no cobra cómputo, pero el disco y la IP pública sí.
- Cargo observado en noviembre (2026-11-10): US$2,80 en `rg-notifier`, con la VM encendida unas 12 horas.
  El presupuesto `budget-notifier` existe en la suscripción: US$100 al mes, tres alertas de costo real.

## 7. Métricas y observabilidad

Fuentes: `docs/MET/` y `monitoring/`.

- **Preguntas operativas (3):** P1, ¿cuántas se entregan dentro de 30 s?; P2, ¿qué canal o dependencia
  explica reintentos y retrasos?; P3, ¿el worker da abasto o la cola crece? (MET-01).
- **SLIs (3):**
  - SLI-1 disponibilidad de la aceptación: respuestas 2xx / (2xx + 5xx) de `POST /v1/notifications`;
    los 4xx se excluyen porque son errores del cliente.
  - SLI-2 entrega oportuna (el específico del escenario): entregadas en ≤ 30 s / estados finales menos
    errores permanentes. Limitación: una notificación atascada en `pending` no baja el SLI hasta que
    termina, por eso se vigila junto con la antigüedad del pendiente más viejo.
  - SLI-3 latencia de aceptación: respuestas 2xx en ≤ 500 ms. Limitación: el histograma incluye 4xx.
- **SLOs (2):** SLO-A (sobre SLI-1) ≥ 99,5 %; SLO-B (sobre SLI-2) ≥ 95 %; ventana de 7 días, con 1 h para
  la demostración. Presupuesto = (1 − objetivo) × eventos de la ventana: con 2 000 solicitudes se toleran
  10 respuestas 5xx; con 1 000 notificaciones terminadas, 50 fuera de objetivo.
- **Métricas de aplicación:** nueve, definidas en `src/notifier/observability.py` (aceptadas, repeticiones
  y conflictos de idempotencia, intentos por resultado, finalizadas, duración de intento, tiempo extremo a
  extremo, profundidad de la cola y antigüedad del pendiente más viejo).
- **Dashboard:** `Notificaciones - operacion`, ocho paneles, cada uno con unidad y ventana (MET-05).
- **Alertas** (`monitoring/alerts.yml`):
  - `NotifierDeliveryFailureRatioHigh`: más del 20 % de intentos fallidos con más de 0,02 intentos/s,
    ventana de 2 min y `for` de 1 min.
  - `NotifierQueueDelayHigh`: pendiente más viejo de más de 30 s durante 2 min.
  - **Limitación conocida:** la métrica de antigüedad solo la publica el worker. Si el worker se detiene,
    la serie desaparece y la alerta no dispara.
- **Trazas:** el `traceparent` se guarda con la notificación, y el worker lo extrae para continuar la
  traza de la API (`worker/main.py`). Así la traza sobrevive a una entrega asíncrona.
- **Incidente controlado:** el proveedor de correo responde 503 en el 60 % de los envíos
  (`NOTIFIER_EMAIL_FAULT_RATE=0.6`). Hipótesis escrita antes de correr: unos 21,6 % de correos terminan
  `failed` (0,6³), 1,96 intentos promedio por correo, y el canal interno y SLI-1 no cambian (MET-07).
  **Resultado medido** (run `2699b5ea` en `dev`): SLI-1 100 % (1646/1646); SLI-2 95,1 % (1565/1646) y
  78,7 % en el correo durante los 5 min de degradación. La notificación `02e7bade…` se siguió por log y por
  la traza `863f3fdb…`. Hallazgo: los logs solos no bastaron para diagnosticar. La alerta de fallos disparó
  y se resolvió; la de cola no disparó. Revise en MET-07 la tabla de hipótesis contra medido.

## 8. Preguntas para practicar

Responda en voz alta, sin mirar. Cada respuesta está en la sección que se indica.

1. ¿Qué significa `202`? ¿Qué devuelve una repetición idempotente y por qué es distinto? (2)
2. El worker muere a mitad de un intento: ¿qué pasa con esa notificación, cuántos intentos le quedan y
   puede duplicarse el correo? (2)
3. ¿Por qué la cola está en PostgreSQL? ¿Qué se pierde con esa decisión? (2)
4. Misma clave de idempotencia con contenido distinto: ¿qué responde y por qué? (2)
5. ¿Por qué se guarda el hash de la clave y por qué SHA-256 y no bcrypt? (2)
6. Se reprocesa una notificación fallida: ¿cuántos intentos nuevos tiene y se reinicia el contador? (2)
7. ¿Cómo se sabe qué versión corre en prod? ¿Cómo se vuelve a la anterior? ¿Eso restaura los datos? (3)
8. Diferencia entre readiness y liveness de la API: ¿qué pasa con cada una si cae la base? (5)
9. Un Pod supera su límite de memoria: ¿qué ocurre? ¿Y por qué no hay límite de CPU? (5)
10. ¿Qué protege el cifrado de Secrets en K3s y qué no? (5)
11. Un PR modifica el workflow de Terraform: ¿por qué no puede escribir en Azure? ¿Quién aplica y cuándo? (4)
12. ¿Qué intervención manual hay antes del primer `apply` y por qué no se puede automatizar? (4)
13. La VM está apagada: ¿cuánto cuesta al mes y por qué no cae a cero? (6)
14. ¿Qué mide SLI-2 y por qué excluye los errores permanentes? ¿Cuánto presupuesto hay con 1 000
    notificaciones? (7)
15. ¿Por qué la alerta de cola no avisa si el worker está caído? (7)
16. Hay un pico de fallos: ¿qué señal mira primero y cómo distingue un problema del proveedor de uno
    propio? (7)

## 9. Qué está demostrado y qué no

Conviene saberlo antes de que el docente lo pregunte.

**Demostrado en el clúster** (según los documentos): pruebas P1-1 a P1-4 en `dev`; despliegue a dev y
prod con aprobación; rollback; reconstrucción con `destroy` y `apply`; probes y recursos con medición;
secretos; Prometheus y Grafana desplegados con carga a 5, 15 y 30 solicitudes por segundo; costos
observados.

**También demostrado ahora** (los 28 requisitos figuran como Cubierto en `docs/EVIDENCIAS.md`):
- MET-01: SLI-1 100 % y SLI-2 95,1 % medidos en `dev`. SLI-3 no se midió en esa corrida.
- MET-02 y MET-04: logs correlacionados y trazas OpenTelemetry instaladas y consultadas en el clúster.
- MET-06: la alerta de fallos disparó y se resolvió en K3s.
- MET-07: incidente controlado en `dev` con línea de tiempo y comparación contra la hipótesis.
- ESC1 P1-5 y DEV-14 (costos observados y presupuesto de US$100 con alertas).
Pendiente de revisión: el PR #41 con DEV-14 y ESC1 aún debe revisarlo alguien de otra área.

**Límites que el enunciado pide reconocer:**
- Un solo nodo y una réplica por componente: sin alta disponibilidad. Si cae la VM, caen los dos ambientes.
- Semántica "al menos una vez": no se garantiza exactamente una entrega externa.
- Quien administre el clúster puede leer los Secrets.
- Dev y prod comparten CPU y memoria del mismo nodo.
- El canal de correo no se probó con carga en la VM: la medición fue por el canal `internal`.
- La imagen no se escanea en el CI y su base no está fijada por digest.
- La carga medida (100 solicitudes; 30 req/s por 60 s) es ligera y solo por el canal `internal`.
- `NotifierQueueDelayHigh` no disparó en el incidente: la cola nunca superó 30 s.
