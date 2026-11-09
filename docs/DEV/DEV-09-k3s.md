# DEV-09: Instalar y operar K3s en una o más máquinas virtuales de Azure.

> **Cubierto.**

| | |
|---|---|
| **Responsable** | Melissa |
| **Estado** | Cubierto |
| **Evidencia mínima que se revisa** | Nodos y workloads verificables mediante Kubernetes. |

## Qué hay y qué falta

K3s se instala por cloud-init (con cifrado de secretos). El nodo está `Ready` y Traefik, CoreDNS y el
almacenamiento local corren, también tras apagar y encender la VM. Los workloads de la
aplicación en `notifier-dev` (api, worker, mailpit y postgres) están en `Running` (2026-11-08).

## Evidencia

- [DEV-09-nodo-ready.txt](../evidencias/DEV-09-nodo-ready.txt): `kubectl get nodes -o wide` y `get pods -A`.
- [DEV-09-k3s-workloads.txt](../evidencias/DEV-09-k3s-workloads.txt): nodo `Ready`, todos los Pods y los
  Deployments `api` y `worker` con la imagen del commit.
- Acceso público con TLS: [COM-02-tls.txt](../evidencias/COM-02-tls.txt).
