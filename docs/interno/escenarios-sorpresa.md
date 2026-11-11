# Escenarios sorpresa: qué hacer si el docente pide algo (§5.12)

El docente puede cambiar datos de entrada, pedir interpretar una salida, detener un Pod o simular una
dependencia fallida, siempre con cambios reversibles. Aquí está qué hacer en cada caso.

Requisitos: haber hecho la preparación de [practica-demo-en-vivo.md](practica-demo-en-vivo.md) (VM
encendida, claves, Postman con las variables guardadas, `az login`, y en la terminal
`export RESOURCE_GROUP=rg-notifier VM_NAME=vm-notifier`). Importar la colección **nueva** de Postman: trae la
carpeta **9. Escenarios sorpresa**.

Regla de oro: **diagnostica en voz alta** (qué esperas, qué ves, cuál es la causa probable) y **revierte** lo que
cambies. El diagnóstico pesa más que la demo (30 de 100 puntos en la rúbrica individual).

---

## 1. "Cambia los datos de entrada"
**Postman → 9h. Enviar libre.** Pestaña *Body*: cambiar destinatario, canal (`email` o `internal`), asunto o
contenido → *Send*. Luego consultar con **1b. Estado** (usa la última `id`).

Qué decir: "202 es recibida, no entregada; el estado final lo da el worker".

| Pedido | Postman | Esperado |
|---|---|---|
| Dirección inválida | **9a** y luego **9b** | `failed` con **1 solo intento**: error permanente, no se reintenta |
| Canal que no existe | **9d** | `422` (validación) |
| Contenido vacío | **9e** | `422` |
| Consultar un id que no existe | **9f** | `404` |
| Repetir una solicitud | **2a** | `200` y el mismo id |
| Misma clave, otro contenido | **2b** | `409` |

Diferencia clave: error **transitorio** (503, se reintenta hasta 3 veces con espera de 5 s y 10 s) frente a
**permanente** (destinatario `@invalid.test`, SMTP 5xx: `failed` de inmediato).

---

## 2. "Reprocesa una notificación"
- Solo las `failed`, y solo con rol admin.
- **Postman → 9c** (reprocesar una entregada) → `409`: "solo se pueden reprocesar notificaciones en estado 'failed'".
- **Postman → 9g** (cliente sin rol admin) → `403`.
- Reproceso correcto: hacer fallar un correo (pasos 4a a 4c de la demo) y luego **4e**.

---

## 3. "Detén un Pod y explica qué se recupera y qué no"
Worker (lo recrea Kubernetes):
```bash
./scripts/vm.sh "k3s kubectl -n notifier-dev delete pod -l app=worker"
./scripts/vm.sh "k3s kubectl -n notifier-dev get pods"
```
API:
```bash
./scripts/vm.sh "k3s kubectl -n notifier-dev delete pod -l app=api"
./scripts/vm.sh "k3s kubectl -n notifier-dev get pods"
```
Repetir `get pods` hasta `Running` y `1/1`. Comprobar con **Postman → 0. Salud** (`ready`).

Qué decir:
- **Se recupera:** el Pod, porque el Deployment lo recrea. Con una sola réplica hay un corte breve de la API.
- **No se pierde:** los datos y los trabajos pendientes, porque viven en PostgreSQL, no en el Pod.
- **Qué puede repetirse:** un envío en curso cuando muere el worker vuelve a la cola y puede entregarse dos
  veces ("al menos una vez").

---

## 4. "Simula una dependencia fallida"
Es el paso 4 de la demo: activar `NOTIFIER_EMAIL_FAULT_RATE=1.0`, enviar un correo y un interno, ver `failed`
frente a `delivered`, quitar la falla y reprocesar. Falla parcial: usar `0.5` y enviar varios correos con **9h**.
**Al terminar, la falla debe quedar quitada** (sección 7).

---

## 5. "Un Pod no inicia: diagnostica por qué"
Solo lectura:
```bash
./scripts/vm.sh "k3s kubectl -n notifier-dev get pods"
./scripts/vm.sh "k3s kubectl -n notifier-dev describe pod -l app=worker"
./scripts/vm.sh "k3s kubectl -n notifier-dev logs deploy/worker --tail=30"
./scripts/vm.sh "k3s kubectl -n notifier-dev get events --sort-by=.lastTimestamp"
```
En `describe`, mirar **Events** y el **State** del contenedor.

| Lo que ves | Causa probable |
|---|---|
| `ImagePullBackOff` / `ErrImagePull` | La imagen o su etiqueta no existe, o falta permiso para bajarla |
| `CrashLoopBackOff` | El proceso arranca y muere: ver `logs` (y `logs --previous`) |
| `CreateContainerConfigError` | Falta un Secret o una clave referenciada (p. ej. `notifier-secrets`) |
| `Pending` sin nodo | Faltan recursos en el nodo (requests mayores que lo libre) |
| `OOMKilled` en *Last State* | Superó el límite de memoria (256Mi): se reinicia |
| Running pero `0/1` | Falla la readiness probe: no recibe tráfico |

Si piden provocarlo (reversible, solo `dev`), imagen inexistente en el worker:
```bash
./scripts/vm.sh "k3s kubectl -n notifier-dev set image deploy/worker worker=ghcr.io/no-existe/imagen:0"
./scripts/vm.sh "k3s kubectl -n notifier-dev get pods"
./scripts/vm.sh "k3s kubectl -n notifier-dev describe pod -l app=worker"
```
Se verá `ErrImagePull` / `ImagePullBackOff`; el Pod anterior sigue sirviendo mientras el nuevo falla.
**Revertir de inmediato:**
```bash
./scripts/vm.sh "k3s kubectl -n notifier-dev rollout undo deploy/worker"
./scripts/vm.sh "k3s kubectl -n notifier-dev rollout status deploy/worker"
```

---

## 6. "Revierte a la versión anterior y demuestra que la activa es la esperada"
Qué versión corre (la etiqueta de la imagen es el SHA del commit):
```bash
./scripts/vm.sh "k3s kubectl -n notifier-dev get deploy api -o jsonpath='{.spec.template.spec.containers[0].image}'"
```
Rollback del proyecto: GitHub → *Actions* → **Entrega**
(https://github.com/devops-metricas/devops-metricas/actions/workflows/entrega.yml) → **Run workflow** con el
**SHA de una versión anterior** (sale de ejecuciones previas de *Entrega* o de `git log --oneline` en `main`;
**tenlo anotado antes de la defensa**).

Verificar: repetir el comando de la imagen (debe mostrar el SHA elegido), **Postman → 0. Salud** (`ready`) y
**1a** con `delivered`. Decir: "el rollback no restaura datos; solo vuelve el código".
Ejecutarlo consume una entrega real: hacerlo solo si el docente lo pide; si no, explicarlo y mostrar la verificación.

---

## 7. Después de cualquier escenario
```bash
./scripts/vm.sh "k3s kubectl -n notifier-dev get deploy worker -o jsonpath='{.spec.replicas} {.spec.template.spec.containers[0].image} {.spec.template.spec.containers[0].env}'"
```
Debe mostrar `1`, la imagen esperada y **no** contener `NOTIFIER_EMAIL_FAULT_RATE`. Si quedó la falla:
```bash
./scripts/vm.sh "k3s kubectl -n notifier-dev set env deploy/worker NOTIFIER_EMAIL_FAULT_RATE- && k3s kubectl -n notifier-dev rollout status deploy/worker"
```
Si el worker quedó en 0 réplicas:
```bash
./scripts/vm.sh "k3s kubectl -n notifier-dev scale deploy/worker --replicas=1"
```

## 8. Preguntas de interpretación (sin tocar nada)
- **Readiness frente a liveness:** readiness (`/readyz`) depende de la base; si cae, la API sale del tráfico.
  Liveness (`/healthz`) solo mira el proceso: si cae la base, no se reinicia.
- **Límite de memoria menor que el consumo:** `OOMKilled` y reinicio. No hay límite de CPU a propósito.
- **Cifrado de Secrets en K3s:** protege el almacén en disco; no protege de quien administre el clúster.
- **Por qué `202`:** la API solo registra; la entrega es asíncrona.

Más respuestas en [guia-defensa.md](guia-defensa.md).
