# DEV-02: Distribuir los componentes ejecutables mediante imágenes de contenedor.

> **Cubierto.**

| | |
|---|---|
| **Responsable** | Melissa |
| **Estado** | Cubierto |
| **Evidencia mínima que se revisa** | Dockerfiles o equivalentes, imágenes versionadas y trazables. |

## Qué hay y qué falta

`Dockerfile` con el argumento `GIT_SHA`, que queda como etiqueta OCI `org.opencontainers.image.revision`.
El workflow `Publicar imagen` ([publicar-imagen.yml](../../.github/workflows/publicar-imagen.yml), DEV-04)
publica en `ghcr.io/devops-metricas/notifier` con la etiqueta igual al SHA completo del commit, y
`scripts/desplegar.sh` despliega esa misma etiqueta. Así, desde la imagen en ejecución se llega al código:

| Pregunta | Cómo se responde |
|---|---|
| ¿Qué versión corre en un ambiente? | La etiqueta de la imagen del Deployment es el SHA del commit |
| ¿Qué código contiene esa imagen? | `docker inspect` o la página del paquete: etiqueta `org.opencontainers.image.revision` |
| ¿Cómo se vuelve a una versión previa? | `Entrega` manual con el SHA anterior (DEV-12) |

## Evidencia

- [DEV-02-etiqueta-revision.txt](../evidencias/DEV-02-etiqueta-revision.txt): consulta al registro GHCR
  (anónima, el paquete es público) de la imagen `…/notifier:e0a768b…`; su etiqueta OCI
  `org.opencontainers.image.revision` es el mismo SHA del commit.
- [DEV-09-k3s-workloads.txt](../evidencias/DEV-09-k3s-workloads.txt): los Deployments `api` y `worker` de
  `dev` usan esa misma imagen, el HEAD de `main` en ese momento.
