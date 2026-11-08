# DEV-02: Distribuir los componentes ejecutables mediante imágenes de contenedor.

> **Parcial. Completa Melissa.**

| | |
|---|---|
| **Responsable** | Melissa |
| **Estado** | Parcial |
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

Falta enlazar las capturas (abajo) para dar el requisito por cubierto.

## Evidencia

Pendiente de capturar y enlazar en [evidencias/](../evidencias) con el prefijo `DEV-02-`:

1. Página del paquete en GitHub con la etiqueta del SHA.
2. `docker inspect` (o `crane config`) de esa imagen mostrando `org.opencontainers.image.revision`.
3. Misma etiqueta en el Deployment de `dev` (`kubectl get deploy api -o jsonpath` dentro de la VM, en la
   sesión descrita en [interno/sesion-vm.md](../interno/sesion-vm.md)).
