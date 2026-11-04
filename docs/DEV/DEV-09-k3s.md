# DEV-09: Instalar y operar K3s en una o más máquinas virtuales de Azure.

> **Parcial. Completa Melissa.**

| | |
|---|---|
| **Responsable** | Melissa |
| **Estado** | Parcial |
| **Evidencia mínima que se revisa** | Nodos y workloads verificables mediante Kubernetes. |

## Qué hay y qué falta

K3s se instala por cloud-init (con cifrado de secretos). El nodo está `Ready` y Traefik, CoreDNS y el
almacenamiento local corren, también tras apagar y encender la VM. Falta ver los workloads de la
aplicación en el clúster, que depende de la entrega de Diego (DEV-04 y DEV-05).

## Evidencia

- [DEV-09-nodo-ready.txt](../evidencias/DEV-09-nodo-ready.txt): `kubectl get nodes -o wide` y `get pods -A`.
- Acceso público con TLS: [COM-02-tls.txt](../evidencias/COM-02-tls.txt).
