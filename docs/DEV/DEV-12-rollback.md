# DEV-12: Recuperar una versión funcional tras un despliegue defectuoso.

> **Cubierto.**

| | |
|---|---|
| **Responsable** | Diego |
| **Estado** | Cubierto |
| **Evidencia mínima que se revisa** | Demostración de recuperación y verificación posterior. |

## Qué hay y qué falta

**Mecanismo**: cada commit de `main` tiene su imagen `ghcr.io/devops-metricas/notifier:<sha>`, así que volver atrás es
volver a desplegar un SHA anterior con el workflow [Entrega](../../.github/workflows/entrega.yml) (*Run workflow*,
campo `sha`). No se reconstruye nada.

**Por qué es seguro**: el Deployment actualiza de forma gradual (`maxUnavailable` 25 % con 1 réplica es 0 pods
caídos) y la *readiness* de la API (`/readyz`) impide que un pod defectuoso reciba tráfico, de modo que la versión
anterior sigue atendiendo mientras la nueva falla. El paso `rollout status` (180 s) hace fallar el workflow y señala
el despliegue malo.

## Evidencia

Demostración en dev (2026-11-09, UTC). La versión defectuosa se construyó desde una rama que no se mergea
(`prueba/rollback-version-mala`): `/readyz` devuelve siempre 503. Se publicó con `Publicar imagen` lanzado a mano
sobre esa rama, así que `main` nunca tuvo código roto.

| Paso | Qué pasó |
|---|---|
| 1. Estado sano | dev corría `e0a768b1…` y `/dev/readyz` respondía 200. |
| 2. Despliegue defectuoso | `Entrega` con el SHA `53a672e4…` ([run 42540108695](https://github.com/devops-metricas/devops-metricas/actions/runs/42540108695)). |
| 3. La versión sana sigue sirviendo | El pod nuevo quedó `Running` con `READY=false`; el anterior siguió `READY=true`. Durante todo el despliegue `/dev/readyz` respondió **200 en cada sondeo**: no hubo caída. |
| 4. El pipeline avisa | El paso *Desplegar a dev* falló por tiempo agotado del rollout (`timed out waiting for the condition`) y `prod` se omitió. |
| 5. Recuperación | `Entrega` a mano con el SHA sano `e0a768b1…` ([run 42540529777](https://github.com/devops-metricas/devops-metricas/actions/runs/42540529777)): `api` y `worker` *rolled out*, `/readyz` ready. |
| 6. Verificación posterior | Pod `api` `READY=true` con la imagen `e0a768b1…`, `worker` en la misma versión, y `/dev/readyz` y `/prod/readyz` en 200. |

Estado de los pods durante el fallo (paso 3):

```
api-867887c777-vh4wx   true    Running   ghcr.io/devops-metricas/notifier:e0a768b1ec19…
api-c46fd9649-dp55p    false   Running   ghcr.io/devops-metricas/notifier:53a672e48b45…
```

Tras la recuperación (paso 6):

```
api-867887c777-zdmmw   true    ghcr.io/devops-metricas/notifier:e0a768b1ec194a071e93bb285eb68c25c78aa044
```

**Nota sobre el desarrollo de la prueba**: mientras duraba el fallo se mergearon otros PR a `main` y el `Entrega`
automático desplegó a dev un commit nuevo (`9c07766…`), así que dev se recuperó primero "hacia adelante". Después se
ejecutó el rollback explícito al SHA anterior (paso 5), que es el que se documenta. La cola de concurrencia del
workflow (`entrega`) serializó ambos despliegues, sin pisarse.

**Límites**: la defectuosa se detecta por la *readiness*; un defecto que no rompa `/readyz` (un error de lógica)
no lo detendría el pipeline, y requeriría pruebas o métricas de negocio. Con 1 réplica el margen es mínimo; con
más réplicas el despliegue sería aún más tolerante.
