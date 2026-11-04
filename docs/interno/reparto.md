# Reparto de tareas

Equipo: Melissa, Diego, Rene y Camila. Escenario 1 (Notificaciones multicanal).

| Quién | Área | Qué incluye | Requisitos |
|---|---|---|---|
| **Melissa** | Base + infraestructura | Estructura del repo, API, worker, esquema de la base y Dockerfile. Terraform, estado remoto, OIDC GitHub→Azure, VM con K3s, firewall y alertas de presupuesto. | COM-*, ESC1-*, DEV-02, 06, 07, 09, 13, 14 |
| **Diego** | CI/CD y operación en Kubernetes | Workflows de GitHub Actions (CI, publicar imagen, entrega a dev y luego a prod con aprobación, rollback), protección de rama, secretos, probes, requests y límites, y namespaces. | DEV-01, 03, 04, 05, 08, 10, 11, 12 |
| **Rene** | Métricas: stack y dashboards | Prometheus y Grafana en el clúster, dashboard de 6 o más paneles, 2 alertas (una demostrada disparando y recuperándose) y pruebas de carga. | MET-03, 05, 06 |
| **Camila** | Métricas: análisis y documentación | Logs correlacionados, trazas OpenTelemetry (colector y backend), SLIs, SLOs y presupuesto de error, incidente controlado con su análisis, `EVIDENCIAS.md` y `costos.md`. | MET-01, 02, 04, 07 y documentos |

## Por qué así

- La infraestructura es lo más difícil y lo que bloquea a los demás (Terraform, estado remoto,
  OIDC y K3s valen 20 puntos de DevOps), por eso va con la base.
- Métricas pesa 20% por sí sola: una persona arma la herramienta y la otra hace el análisis y la evidencia.
- El pipeline y Kubernetes van juntos porque el pipeline despliega los manifiestos que se mantienen.

## Orden

1. Melissa entrega primero el repo base, para trabajar en local con `docker compose`.
2. Diego, Rene y Camila avanzan en paralelo sobre lo local.
3. Con el clúster arriba, despliegan y miden sobre él.

## Reglas del equipo

- Todo cambio entra por pull request, revisado por alguien de **otra** área.
- La defensa individual puede preguntar por cualquier parte del sistema: nadie debe ser el único
  que sabe algo. Cada quien explica su área al resto antes de la entrega.
- Nada de contraseñas, claves ni kubeconfigs en el repo.
