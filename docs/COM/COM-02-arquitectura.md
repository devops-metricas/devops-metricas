# Arquitectura

## Visión general

```
                     Internet
                        │  80/443
                 ┌──────▼───────┐        SSH (22) solo desde TF_ADMIN_CIDR
                 │  NSG + IP    │◀──────────────────────────  quien administra
                 │  pública     │        6443 (API K8s): cerrada
                 └──────┬───────┘
  ┌─────────────────────▼─────────────────────────────────────────────┐
  │ VM Ubuntu 24.04 (Standard_B2as_v2) · K3s de un solo nodo          │
  │                                                                   │
  │  namespace notifier-dev          namespace notifier-prod          │
  │  ┌─────┐ ┌────────┐ ┌───────┐    ┌─────┐ ┌────────┐ ┌───────┐     │
  │  │ api │ │ worker │ │mailpit│    │ api │ │ worker │ │mailpit│     │
  │  └──┬──┘ └───┬────┘ └───────┘    └──┬──┘ └───┬────┘ └───────┘     │
  │     └───┬────┘                      └───┬────┘                    │
  │   ┌─────▼──────┐                   ┌────▼───────┐                 │
  │   │ PostgreSQL │ (StatefulSet+PVC) │ PostgreSQL │                 │
  │   └────────────┘                   └────────────┘                 │
  └───────────────────────────────────────────────────────────────────┘
```

Dev y prod son el mismo manifiesto base (`k8s/base`) con un overlay por ambiente
(`k8s/overlays/dev|prod`): cambian el namespace y `NOTIFIER_ENVIRONMENT`. Cada ambiente tiene su
propia base de datos y su propio Mailpit.

## Aplicación

| Pieza | Qué hace |
|---|---|
| **API** (FastAPI) | Autentica con `X-API-Key`, valida la solicitud, aplica idempotencia y guarda la notificación como `pending`. Responde `202` ("recibida", no "entregada"). |
| **Worker** | Toma trabajos de la cola, entrega por el canal, registra el intento y reintenta o termina la notificación. |
| **PostgreSQL** | Fuente única de verdad: clientes, notificaciones, eventos, intentos y mensajes internos. También es la cola. |
| **Mailpit** | Servidor SMTP de pruebas para el canal de correo; permite ver los correos en su interfaz web. |

Una sola imagen (`Dockerfile`) sirve para los tres comandos (API, worker, migraciones); corre como
usuario no root (UID 10001).

### Modelo de datos

`clients` (con `api_key_hash`, nunca la clave) → `notifications` (estado, intentos, `next_attempt_at`,
`locked_until`, `traceparent`) → `notification_events` (cada transición) y `delivery_attempts` (cada
intento, con su resultado). `internal_messages` guarda las notificaciones del canal interno para que el
destinatario las consulte.

### Ciclo de vida de una notificación

```
POST ──▶ pending ──claim──▶ processing ──éxito──────────────────▶ delivered
            ▲                   │
            │  error pasajero   ├── error pasajero, intentos < 3 ─▶ pending (con espera)
            └───────────────────┤
                                └── error permanente o 3er intento fallido ─▶ failed
                                                                       │
                                            reproceso por admin ◀──────┘
```

- **Cola:** filas `pending`/`processing` en PostgreSQL. El worker las reclama con
  `FOR UPDATE SKIP LOCKED`, así que varios workers no toman el mismo trabajo.
- **Reinicio a medias:** un trabajo `processing` cuyo `locked_until` venció vuelve a ser elegible; el
  estado está en la base, no en memoria, y no se pierde.
- **Reintentos:** hasta 3 intentos en total, con espera exponencial (5 s, 10 s). Un destinatario
  inválido (`…@invalid.test`) es error permanente y no se reintenta.
- **Idempotencia:** índice único parcial por (cliente, canal, clave). Repetir la solicitud devuelve la
  referencia original; la misma clave con otro contenido (hash distinto) se rechaza con `409`.
- **Canal interno:** se guarda el mensaje y se marca `delivered` en la misma transacción.

### Observabilidad incluida en el código

Logs estructurados, métricas Prometheus (`/metrics` en la API y el puerto 9100 del worker: cola,
intentos, duración, tiempo extremo a extremo) y trazas OpenTelemetry. El `traceparent` se guarda con
la notificación, de modo que la traza continúa de la API al worker. El stack que las recoge
(Prometheus, Grafana, colector) pertenece al área de métricas.

## Infraestructura (Azure)

Todo está en `infra/terraform` y se crea desde el pipeline; solo el bootstrap es manual
(ver [DEV-13-reconstruccion.md](../DEV/DEV-13-reconstruccion.md)).

| Recurso | Detalle |
|---|---|
| Grupo de recursos `rg-notifier` | `northcentralus` (región permitida por la suscripción) |
| Red | VNet `10.10.0.0/16`, subred `10.10.1.0/24` |
| IP pública | Estática, con nombre DNS `<TF_DNS_LABEL>.northcentralus.cloudapp.azure.com` |
| NSG | Permite 80, 443 y SSH solo desde `admin_cidr`; el resto cae en `DenyAllInbound`. La API de Kubernetes (6443) no se expone |
| VM | Ubuntu 24.04, `Standard_B2as_v2` (2 vCPU, 8 GB), disco de 64 GB, solo autenticación por clave SSH |
| K3s | Se instala en el primer arranque con cloud-init, versión fijada, con cifrado de Secrets |
| Apagado automático | Todos los días a las 23:00 (hora de América Central) |
| Presupuesto | US$100 a nivel de suscripción, alertas por correo al 50, 80 y 100 % (solo notifican) |

El estado de Terraform vive en una cuenta de almacenamiento de Azure (sin llaves, con versionado),
creada por el bootstrap.

### Identidades y acceso desde GitHub

GitHub se autentica en Azure con OIDC, sin contraseñas guardadas. Hay tres identidades con permisos
mínimos:

| Identidad | Permiso | Cuándo se puede usar |
|---|---|---|
| `infra` | Contributor | Solo desde `main` y el entorno `infra` |
| `plan` | Reader | Pull requests (un PR puede editar el workflow, por eso no puede escribir) |
| `deploy` | Virtual Machine Contributor | Entornos `dev` y `prod` |

### Pipelines de infraestructura

- `terraform.yml`: `plan` en cada PR; `apply` al unir a `main`, con aprobación del entorno `infra`.
- `infra-ops.yml`: apagar, encender, aplicar y destruir a demanda.

## Estado actual y pendientes

- El tráfico externo entra por 80/443 hacia Traefik (incluido en K3s), pero **aún no hay manifiestos de
  Ingress ni TLS** en `k8s/`. Mientras tanto la API se prueba por SSH o con `kubectl port-forward`.
- Los workflows de CI, publicación de imagen y entrega a dev/prod, y los Secrets de Kubernetes
  (`notifier-secrets`) los define el área de CI/CD.
- Un solo nodo y una réplica por componente: no hay alta disponibilidad. Es una decisión consciente
  de costo (ver [COM-06-decisiones.md](COM-06-decisiones.md)).
