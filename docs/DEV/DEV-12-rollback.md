# DEV-12: Recuperar una versión funcional tras un despliegue defectuoso.

> **Pendiente por Diego.**

| | |
|---|---|
| **Responsable** | Diego |
| **Estado** | Pendiente |
| **Evidencia mínima que se revisa** | Demostración de recuperación y verificación posterior. |

## Qué hay y qué falta

**Mecanismo**: cada commit de `main` tiene su imagen `ghcr.io/kmmelissat/notifier:<sha>`, así que volver atrás es
volver a desplegar un SHA anterior con el workflow [Entrega](../../.github/workflows/entrega.yml) (*Run workflow*,
campo `sha`). No se reconstruye nada.

**Por qué es seguro**: el Deployment actualiza de forma gradual y la *readiness* de la API (`/readyz`) impide que
un pod defectuoso reciba tráfico, de modo que la versión anterior sigue atendiendo mientras la nueva falla. El paso
`rollout status` (180 s) hace fallar el workflow y señala el despliegue malo.

**Demostración planeada**:
1. Con dev sano en el SHA A, mergear un commit B defectuoso a propósito (p. ej. que `/readyz` falle) y dejar que Entrega
   lo despliegue a dev: el workflow falla en `rollout status`.
2. Comprobar que dev sigue respondiendo (pod de A atendiendo).
3. Lanzar Entrega a mano con el SHA de A y verificar `/readyz` y `scripts/smoke.py`.
4. Capturar: el workflow fallido, el pod en `CrashLoop` o sin *ready*, el rollback en verde y la verificación.

Pendiente: ejecutarla. Necesita el clúster con secretos y la VM encendida.

## Evidencia

Pendiente de enlazar. Guardar las capturas en [evidencias/](../evidencias) con el prefijo `DEV-12-`.
