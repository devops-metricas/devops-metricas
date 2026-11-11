# Demo en vivo: guion completo, de principio a fin

Copia y pega los bloques **en orden**, en una sola terminal. No hay nada que reemplazar: los valores ya
están escritos. Todo sale del repo (README, `sesion-vm.md`, DEV-13, MET-05, MET-07).

Duración: ≈ 7 min de demo, más ≈ 5 min de preparación **antes** de presentar (secciones A y B).
La VM cobra mientras está encendida: apágala al terminar (sección F).

---

## Pestañas del navegador (ábrelas antes)

| Qué | Enlace |
|---|---|
| Infra ops (encender y apagar) | https://github.com/devops-metricas/devops-metricas/actions/workflows/infra-ops.yml |
| Entrega (versión desplegada, rollback) | https://github.com/devops-metricas/devops-metricas/actions/workflows/entrega.yml |
| CI y demás ejecuciones | https://github.com/devops-metricas/devops-metricas/actions |
| Pull requests | https://github.com/devops-metricas/devops-metricas/pulls |
| Salud de la API | https://notifier-melissa-esen.northcentralus.cloudapp.azure.com/dev/readyz |
| **Grafana** (el dashboard "Notificaciones - operacion") | https://notifier-melissa-esen.northcentralus.cloudapp.azure.com/grafana |
| Definición de la API (JSON; `/dev/docs` falla, no lo abras) | https://notifier-melissa-esen.northcentralus.cloudapp.azure.com/dev/openapi.json |
| Costos | https://portal.azure.com → Cost Management (ámbito: la suscripción) |
| Deck | https://claude.ai/artifact/V4n43y6nSWGhdk7LyE8oQZ |

Grafana: rango **Last 15 minutes** y refresco **10 s**.

---

## A. Preparación (antes de presentar)

### A1. Encender la VM
Pestaña *Infra ops* → **Run workflow** → `action = start` → aprobar si lo pide. Esperar 2 a 3 minutos.
Si no ves el botón *Run workflow*, pídele a Diego que lo ejecute.

### A2. Terminal lista
```bash
cd ~/Documents/2026/ciclo3/devops-metricas
source .venv/bin/activate
az login
```
Si `.venv` no existe: `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`.

### A3. Variables
```bash
export FQDN=notifier-melissa-esen.northcentralus.cloudapp.azure.com
export API_URL=https://$FQDN/dev
export RESOURCE_GROUP=rg-notifier VM_NAME=vm-notifier
curl -fsS $API_URL/readyz
```
Debe imprimir `{"status":"ready"}`. Si da error de conexión o tiempo agotado, espera 1 minuto y repite.

### A3b. Comprobar que no quedó una falla activa (importante)
Una sesión anterior pudo dejar el correo degradado. Si es así, el paso 3 da `{'delivered': 50, 'failed': 50}`.
```bash
./scripts/vm.sh "k3s kubectl -n notifier-dev get deploy worker -o jsonpath='{.spec.template.spec.containers[0].env}'"
```
El resultado **no** debe contener `NOTIFIER_EMAIL_FAULT_RATE`. Si aparece, quitarla:
```bash
./scripts/vm.sh "k3s kubectl -n notifier-dev set env deploy/worker NOTIFIER_EMAIL_FAULT_RATE- && k3s kubectl -n notifier-dev rollout status deploy/worker"
```

### A4. Claves de cliente (se guardan solas en variables; no van al repo)
```bash
export API_KEY=$(./scripts/vm.sh "k3s kubectl -n notifier-dev exec deploy/api -- python -m notifier.cli create-client app-demo-$RANDOM" | grep -o 'ntf_[A-Za-z0-9_-]*' | head -1)
export ADMIN_KEY=$(./scripts/vm.sh "k3s kubectl -n notifier-dev exec deploy/api -- python -m notifier.cli create-client operaciones-demo-$RANDOM --admin" | grep -o 'ntf_[A-Za-z0-9_-]*' | head -1)
echo "API_KEY=${API_KEY:0:8}...  ADMIN_KEY=${ADMIN_KEY:0:8}..."
```
Cada línea tarda 20 a 40 s. Debe mostrar dos prefijos `ntf_...`. Si salen vacíos, repite el bloque.

### A5. Preparar Postman y Grafana
Ver las secciones "Preparar Postman" y "Grafana" más abajo (hacerlo antes de presentar).

### A6. Dejar listos los comandos de la VM (para no esperar)
Los pasos 4, 5 y 8 usan `vm.sh` (20 a 40 s cada llamada). Ya están escritos abajo; solo pégalos.

---

## B. Antes de empezar a hablar

- Grafana abierto en la pestaña (rango 15 min).
- Terminal limpia (`clear`) con el entorno activado y las variables exportadas (A3 y A4).
- Deck abierto en la lámina 9 (Demostración en vivo).

---

## Preparar Postman (una vez, antes de presentar)

1. Postman → **Import** → archivo `docs/interno/demo.postman_collection.json`.
2. Clic en el **nombre de la colección** → pestaña **Variables**. En **Current value**:
   - `api_key` = la clave de app (en la terminal: `echo $API_KEY`).
   - `admin_key` = la clave de admin (`echo $ADMIN_KEY`).
   - `base_url` ya viene con `https://notifier-melissa-esen.northcentralus.cloudapp.azure.com/dev`.
   - Los `id...` se llenan solos: déjalos vacíos.
3. **Save** (Cmd+S). Sin guardar, las peticiones dan `401`.
4. Probar: carpeta **0. Salud** → *Send* → debe responder `{"status":"ready"}`.

Cada petición lleva su nombre con el paso de la demo. Se envían con **Send** y se lee la respuesta abajo
(código HTTP en verde arriba a la derecha).

## Grafana (para mostrar al lado)

Contraseña (usuario `admin`), desde la terminal:
```bash
./scripts/vm.sh "k3s kubectl -n monitoring get secret grafana-admin -o jsonpath='{.data.password}' | base64 -d"
```
Abrir https://notifier-melissa-esen.northcentralus.cloudapp.azure.com/grafana → entrar → **Dashboards** →
**Notificaciones - operacion** → **Last 15 minutes**, refresco **10s**.

## C. La demo (Postman para la API, terminal para el clúster)

Deja **Postman y Grafana visibles**. La terminal solo se usa en los pasos que cambian el clúster.

### Paso 1 (Melissa): una notificación, de punta a punta
**Postman → 1. Una notificación**
1. **1a. Enviar** → `202`. Decir: "202 significa recibida y registrada, no entregada".
2. **1b. Estado e historial** → `delivered`, con el `history` (pending → processing → delivered) e intentos.
3. **1c. Bandeja del destinatario** → la notificación interna.

### Paso 2 (Melissa): idempotencia
**Postman → 2. Idempotencia**
1. **2a. Repetir igual** → `200` y el **mismo id**. No se duplicó.
2. **2b. Misma clave, otro contenido** → `409`.

### Paso 3 (Diego): carga de 100 con el dashboard en vivo
**Terminal:**
```bash
python scripts/smoke.py batch
```
Mientras corre, señalar en **Grafana** cómo suben aceptadas, intentos y la cola. Esperado: 100 aceptadas,
`{'delivered': 100}`.

### Paso 4 (Camila): proveedor de correo degradado
**Qué demuestra:** si el proveedor de correo se cae, el correo falla pero el canal interno sigue
funcionando. Cómo usar Postman: abrir la carpeta, clic en una petición y pulsar **Send** (arriba a la
derecha); abajo se ve la respuesta con su código. Se envía cada petición una vez, en orden.

1. **Terminal: romper el correo** (≈ 30 s; esperar a que termine):
```bash
./scripts/vm.sh "k3s kubectl -n notifier-dev set env deploy/worker NOTIFIER_EMAIL_FAULT_RATE=1.0 && k3s kubectl -n notifier-dev rollout status deploy/worker"
```
2. **Postman, carpeta "4. Correo degradado":**
   - **4a. Enviar correo** → *Send* → `202`.
   - **4b. Enviar interno** → *Send* → `202`.
3. **Esperar 20 s** (el worker intenta el correo 3 veces, con pausas de 5 s y 10 s).
4. **Postman, ver qué pasó:**
   - **4c. Estado del correo** → *Send* → `"status": "failed"` y 3 elementos en `delivery_attempts`.
   - **4d. Estado del interno** → *Send* → `"status": "delivered"`.
   - Decir: "el correo falló, pero el canal interno siguió funcionando".
5. **Terminal: arreglar el correo** (≈ 30 s):
```bash
./scripts/vm.sh "k3s kubectl -n notifier-dev set env deploy/worker NOTIFIER_EMAIL_FAULT_RATE- && k3s kubectl -n notifier-dev rollout status deploy/worker"
```
6. **Postman, reprocesar el correo fallido:**
   - **4e. Reprocesar el correo** → *Send* → `202`.
   - Esperar 5 s. **4f. Estado del correo tras reprocesar** → *Send* → `"status": "delivered"`.
   - Decir: "reprocesar es una acción explícita, solo de un admin".

Si algo no sale: `401` = faltó guardar las claves en las variables de la colección; `4c` aún sin `failed` =
esperar unos segundos y pulsar *Send* otra vez; `4e` con error = `admin_key` tiene la clave de app, no la de admin.

### Paso 5 (Camila): el worker se cae y no se pierde nada
**Terminal** (detener el worker):
```bash
./scripts/vm.sh "k3s kubectl -n notifier-dev scale deploy/worker --replicas=0"
```
**Postman → 5. Worker caído:** **5a. Enviar con worker caido** → `202`; **5b. Estado** → `pending`.
(Pulsa 5a dos o tres veces si quieres varios pendientes: cada envío lleva idempotency distinta o ninguna.)

**Terminal** (encender el worker):
```bash
./scripts/vm.sh "k3s kubectl -n notifier-dev scale deploy/worker --replicas=1"
```
Esperar ≈ 10 s. **Postman: 5b. Estado** → `delivered`.
Decir: "la cola vive en PostgreSQL, por eso no se pierde ningún trabajo".

### Paso 6 (Rene): dashboard
En **Grafana**, mostrar lo que quedó de los pasos 3 a 5: pico de aceptadas, fallos del correo, la cola
subiendo con el worker caído y bajando después, y la antigüedad del pendiente más viejo.

### Paso 7 (Rene): acceso rechazado
**Postman → 7. Acceso rechazado:** **7a** `401` (sin clave), **7b** `401` (clave inválida), **7c** `403`
(cliente sin rol admin). Decir: "estadísticas y reproceso son solo de admin".

### Paso 8 (Diego): persistencia
**Postman → 8. Persistencia → Recuentos** → anotar los números.

**Terminal** (borrar el Pod de PostgreSQL; Kubernetes lo recrea):
```bash
./scripts/vm.sh "k3s kubectl -n notifier-dev delete pod -l app=postgres"
./scripts/vm.sh "k3s kubectl -n notifier-dev get pods"
```
Repetir el `get pods` hasta que `postgres-0` esté `Running` y `1/1`.
**Postman: Recuentos** otra vez → los números son iguales.
Decir: "los datos viven en un volumen persistente, no en el Pod".

---

## D. Si el docente pregunta por otras partes (comandos de apoyo)

Estado del clúster (Diego, lámina Infraestructura):
```bash
./scripts/vm.sh "k3s kubectl get nodes"
./scripts/vm.sh "k3s kubectl get pods -A"
```
Qué versión corre (la etiqueta es el SHA del commit):
```bash
./scripts/vm.sh "k3s kubectl -n notifier-dev get deploy api -o jsonpath='{.spec.template.spec.containers[0].image}'"
```
Con ese SHA: `https://github.com/devops-metricas/devops-metricas/commit/<SHA>`.
Rollback: pestaña *Entrega* → **Run workflow** con un SHA anterior (solo explicarlo, no ejecutarlo).

Costos (Rene): pestaña de Azure → *Cost analysis* y *Budgets* (`budget-notifier`, US$100, alertas al 50,
80 y 100 %). Respaldo: `docs/evidencias/DEV-14-presupuesto-gasto.png`, `DEV-14-presupuesto.png`,
`DEV-14-cost-analysis.png`.

Trazas e incidente: Jaeger no tiene URL pública. Mostrar las evidencias `docs/evidencias/MET-04-*`,
`MET-07-*` (dashboard del incidente) y `MET-06-k3s-alerta-*.png` (alerta en K3s).

---

## E. Si algo falla

| Síntoma | Qué hacer |
|---|---|
| `command not found: python` | `source .venv/bin/activate` |
| `Bad hostname` en `curl` | Estás usando `<FQDN>`; usa `$FQDN` tras exportarlo (A3) |
| `readyz` no responde | VM apagada o arrancando: esperar 1 a 2 minutos |
| `/dev/docs` da 404 | Es conocido y no afecta; usar `/dev/openapi.json` o no abrirlo |
| El lote da `{'delivered': 50, 'failed': 50}` | Quedó activa la falla del correo: ver A3b |
| Postman da `401` | Falta guardar las claves en las variables de la colección (Save) |
| Postman da `404 page not found` | `base_url` vacía o mal escrita: debe terminar en `/dev`, sin barra final |
| `API_KEY` o `ADMIN_KEY` vacías | Repetir A4 (confirmar `az login`) |
| `401` en todo | Las claves no están exportadas en esta terminal: repetir A4 |
| `postgres` no vuelve | `./scripts/vm.sh "k3s kubectl -n notifier-dev get pods"` y esperar |
| Todo falla / sin red | Plan B: mostrar `docs/evidencias/` (`COM-01-smoke-batch-idempotency.txt`, `COM-04-smoke-errores-y-recovery.txt`, `COM-05-smoke-access.txt`, `COM-03-stats-antes.txt`, `COM-03-stats-despues.txt`, `MET-05-dashboard-*.png`, `MET-07-dashboard-*.png`) y decir: "la demo en vivo falló; esta es la evidencia de la corrida de noviembre" |

---

## F. Al terminar (obligatorio)

1. Confirmar que no quedó la falla del correo y que el worker está en 1 réplica:
```bash
./scripts/vm.sh "k3s kubectl -n notifier-dev get deploy worker -o jsonpath='{.spec.replicas} {.spec.template.spec.containers[0].env}'"
```
Debe mostrar `1` y **no** contener `NOTIFIER_EMAIL_FAULT_RATE`. Si aparece, repetir el comando de quitar la
falla (paso 4).

2. Apagar la VM: pestaña *Infra ops* → **Run workflow** → `action = deallocate`.
3. Confirmar en Azure que la VM quedó *Stopped (deallocated)*.

---

## Lista rápida

- [ ] A1 VM encendida · [ ] A2 entorno y `az login` · [ ] A3 variables y `readyz`
- [ ] A4 claves · [ ] Postman importado, claves guardadas y Salud en 200 · [ ] Grafana abierto · [ ] deck listo
- [ ] C pasos 1, 2, 3, 7, 4, 5, 6, 8 · [ ] F apagar la VM
