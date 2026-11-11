# DEV-11: Configurar salud y recursos de workloads según sus características.

> **Cubierto.**

| | |
|---|---|
| **Responsable** | Diego |
| **Estado** | Cubierto |
| **Evidencia mínima que se revisa** | Probes apropiadas, requests y límites justificados. |

## Qué hay y qué falta

Definidos en `k8s/base/`. Justificación del diseño:

| Workload | Probes | Recursos |
|---|---|---|
| `api` | **readiness** `/readyz` (depende de la base: sin PostgreSQL no recibe tráfico). **liveness** `/healthz` (solo el proceso: una caída de la base no debe reiniciar la API) | requests 50m CPU y 96Mi; límite de memoria 256Mi |
| `worker` | solo **liveness** `/metrics` (no recibe tráfico, no hay readiness que aplicar) | igual que la API |
| `postgres` | `pg_isready` en readiness y liveness (`initialDelaySeconds: 20` solo en liveness, para el arranque) | requests 100m CPU y 256Mi; límite 512Mi |

- **Sin límite de CPU** a propósito: evita el *throttling* que añade latencia a una API pequeña; los requests
  bastan para que el planificador reparta.
- **Límite de memoria** para que un fallo no agote la VM; es el doble o el triple del request.
- Los pods corren como no root, con sistema de archivos de solo lectura y sin capacidades.

**Consumo observado** (`kubectl top pods -n notifier-dev`, metrics-server de K3s), en reposo y durante
`scripts/smoke.py batch` (100 notificaciones, las 100 entregadas):

| Pod | Request CPU / mem | Límite mem | En reposo | Pico durante la carga | Tras la carga |
|---|---|---|---|---|---|
| `api` | 50m / 96Mi | 256Mi | 2m / 54Mi | **37m** / 54Mi | 7m / 54Mi |
| `worker` | 50m / 96Mi | 256Mi | 1m / 39Mi | **26m** / 43Mi | 1m / 43Mi |
| `postgres` | 100m / 256Mi | 512Mi | 5m / 29Mi | **12m** / 41Mi | 5m / 39Mi |
| `mailpit` | 25m / 32Mi | 128Mi | 1m / 5Mi | 8m / 12Mi | 1m / 12Mi |

El nodo pasó de 54m (2 %) a 65m (3 %) de CPU y se mantuvo en 1,7 GiB (21 %) de memoria.

**Lectura**
- **CPU:** el pico de la API (37m) y del worker (26m) queda por debajo de su request (50m): el request refleja el
  uso real bajo carga, sin quedarse corto. No hay límite de CPU, así que un pico no se estrangula.
- **Memoria:** el consumo (39 a 54 Mi) es la mitad del request de 96Mi y una quinta parte del límite de 256Mi. Hay
  holgura amplia antes de un `OOMKilled`, y el límite sigue acotando una fuga.
- **PostgreSQL:** usa 29 a 41 Mi frente a un request de 256Mi, sobredimensionado para este volumen. Se conserva
  porque la base es el componente que no debe expulsarse por falta de memoria, y el nodo lo soporta (21 %).
- **Reinicios:** ningún pod se reinició durante la carga (el contador no cambió; los que hay vienen del apagado y
  encendido de la VM). Las probes no se dispararon.

**Límites de esta medición**: 100 notificaciones es una carga ligera, no una prueba de capacidad. Valida que los
valores no están por debajo del uso, no que sean los óptimos. Si crece el volumen, el primero en revisarse es el
request de CPU de la API. Mediciones completas y fecha de captura en la sección de evidencia.

## Evidencia

Medidas del 2026-11-09 (UTC) con la API de dev detrás de HTTPS:

```
== En reposo (00:09:24)             == Durante la carga (00:16:42)
api       2m    54Mi                 api       37m   54Mi
mailpit   1m    5Mi                  mailpit   1m    5Mi
postgres  5m    29Mi                 postgres  8m    29Mi
worker    1m    39Mi                 worker    2m    39Mi
nodo      54m 2%  1714Mi 21%         nodo      65m 3%  1719Mi 21%

== Durante la carga (00:17:14)      == Después (00:17:46)
api       27m   54Mi                 api       7m    54Mi
mailpit   8m    12Mi                 mailpit   1m    12Mi
postgres  12m   41Mi                 postgres  5m    39Mi
worker    26m   43Mi                 worker    1m    43Mi
```

Resultado de `smoke.py batch`: 100 solicitudes aceptadas (202), 100 identificadores distintos, todas en estado
final, `{'delivered': 100}`. Las probes y los recursos están en [k8s/base/](../../k8s/base).
