# DEV-11: Configurar salud y recursos de workloads según sus características.

> **Parcial. Completa Diego.**

| | |
|---|---|
| **Responsable** | Diego |
| **Estado** | Parcial |
| **Evidencia mínima que se revisa** | Probes apropiadas, requests y límites justificados. |

## Qué hay y qué falta

Definidos en `k8s/base/`. Justificación del diseño:

| Workload | Probes | Recursos |
|---|---|---|
| `api` | **readiness** `/readyz` (depende de la base: sin PostgreSQL no recibe tráfico). **liveness** `/healthz` (solo el proceso: una caída de la base no debe reiniciar la API) | requests 50m CPU y 96Mi; límite de memoria 256Mi |
| `worker` | solo **liveness** `/metrics` (no recibe tráfico, no hay readiness que aplicar) | igual que la API |
| `postgres` | `pg_isready` en readiness y liveness (`initialDelaySeconds: 20` para el arranque) | requests 100m CPU y 256Mi; límite 512Mi |

- **Sin límite de CPU** a propósito: evita el *throttling* que añade latencia a una API pequeña; los requests
  bastan para que el planificador reparta.
- **Límite de memoria** para que un fallo no agote la VM; es el doble o el triple del request.
- Los pods corren como no root, con sistema de archivos de solo lectura y sin capacidades.

**Falta**: justificar los números con consumo observado (`kubectl top pod -n notifier-dev` bajo la carga de
`scripts/smoke.py batch`) y ajustarlos si hace falta. Necesita el clúster con pods corriendo.

## Evidencia

Pendiente de enlazar. Guardar las capturas en [evidencias/](../evidencias) con el prefijo `DEV-11-`.
