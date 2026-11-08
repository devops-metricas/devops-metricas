# Sesión con la VM: orden de pruebas (Melissa)

Una sola sesión cubre COM-01, COM-03, COM-04, COM-05, DEV-09 y ESC1 contra `dev`. La VM cobra mientras
está encendida: tener todo listo antes de encenderla y apagarla al terminar.

## 0. Antes de encender

- Diego confirma qué SHA está en `dev` (o se despliega con `Entrega`, manual, sobre `main`).
- Definir `FQDN` = `<TF_DNS_LABEL>.northcentralus.cloudapp.azure.com`. La API de `dev` queda en
  `https://$FQDN/dev`.
- Tener lista una carpeta para capturas con los prefijos `COM-01-`, `COM-03-`, etc. en
  `docs/evidencias/`.

## 1. Encender y comprobar

1. Encender la VM con la acción `Infra ops` (la ejecuta una persona, cobra).
2. `curl -fsS https://$FQDN/dev/readyz` responde `ok` y el SHA desplegado coincide con el de `main`.
3. **DEV-09**: captura de `k3s kubectl get nodes,pods -A` (vía `az vm run-command`, la API 6443 no se
   expone) con los workloads de `notifier-dev` en `Running`.

## 2. Claves de cliente (no se guardan en el repo)

Crear una clave de aplicación y otra de admin dentro del Pod de la API y exportarlas solo en la terminal:

```bash
kubectl -n notifier-dev exec deploy/api -- python -m notifier.cli create-client app-pruebas
kubectl -n notifier-dev exec deploy/api -- python -m notifier.cli create-client operaciones --admin
export API_URL=https://$FQDN/dev API_KEY=ntf_... ADMIN_KEY=ntf_...
```

`kubectl` va dentro de la VM (`az vm run-command invoke ... --scripts "k3s kubectl ..."`).

## 3. Pruebas (en este orden)

| Orden | Comando | Requisito | Esperado |
|---|---|---|---|
| 1 | `python scripts/smoke.py access` | COM-05, ESC1-02 | sin clave, clave inválida y rol insuficiente rechazados |
| 2 | `python scripts/smoke.py batch` | COM-01, ESC1 P1-1 | 100 solicitudes aceptadas, todas terminales |
| 3 | `python scripts/smoke.py idempotency` | COM-01, ESC1 P1-3 | 5 repeticiones, un solo efecto |
| 4 | `python scripts/smoke.py email-failure` | COM-04 | `failed` sin reintentos |
| 5 | **COM-03** (ver abajo) | COM-03 | datos íntegros tras reiniciar Pods |
| 6 | `RESTART_CMD="..." python scripts/smoke.py recovery` | COM-04, ESC1 P1-4 | pendientes se entregan tras reiniciar el worker (ver abajo) |
| 7 | `email-degraded` (ver abajo) | COM-04, ESC1 P1-2 | reintenta 3 veces, canal interno vivo |

Cada prueba termina con código distinto de cero si falla: guardar la salida completa como evidencia.

### COM-03: persistencia al reiniciar

1. Crear notificaciones con `batch` y anotar `GET /v1/stats` (admin).
2. Reiniciar `deploy/api`, `deploy/worker` y el Pod de PostgreSQL.
3. Repetir `GET /v1/stats` y consultar un par de IDs: los conteos y los estados deben coincidir.
4. Guardar ambas salidas como `COM-03-antes.txt` y `COM-03-despues.txt`.

### `recovery`: dejar el worker detenido antes

En el clúster el worker despacha más rápido de lo que el script lee el estado y la prueba falla con
"hay trabajos pendientes". Escalar a 0 antes y usar "escalar a 1" como `RESTART_CMD`:

```bash
kubectl -n notifier-dev scale deploy/worker --replicas=0
RESTART_CMD='<run-command que ejecuta: kubectl -n notifier-dev scale deploy/worker --replicas=1>' python scripts/smoke.py recovery
```

### `email-degraded` (requiere cambiar el worker)

`NOTIFIER_EMAIL_FAULT_RATE` vive en el ConfigMap generado `notifier-config`. Para la prueba:
`kubectl -n notifier-dev set env deploy/worker NOTIFIER_EMAIL_FAULT_RATE=1.0`, esperar el rollout, correr
`email-degraded` y **volver atrás al terminar** con `set env deploy/worker NOTIFIER_EMAIL_FAULT_RATE-`. Es un cambio reversible (regla 5.12); no dejarlo así en `dev`.

## 4. Al terminar

1. Confirmar que `NOTIFIER_EMAIL_FAULT_RATE` volvió a `0`.
2. Apagar la VM con `Infra ops`.
3. Actualizar el estado en `docs/EVIDENCIAS.md` y enlazar las capturas en cada documento.
