# Notificaciones multicanal (Escenario 1)

Proyecto de cátedra (DevOps + Métricas). API + worker en Python sobre PostgreSQL, desplegados en K3s en
una VM de Azure con Terraform. Descripción general en [README.md](README.md).

## Comandos

```bash
source .venv/bin/activate
ruff check . && ruff format --check .
pytest                                    # unitarias
docker compose up -d                      # PostgreSQL + Mailpit para pruebas de integración
NOTIFIER_DATABASE_URL=postgresql://notifier:notifier@localhost:5432/notifier pytest   # + integración
```

`scripts/smoke.py` prueba una API en ejecución (ver README).

## Estructura

- `src/notifier/`: API, worker, canales, migraciones SQL. `tests/`: pruebas.
- `k8s/`: kustomize, `base/` y `overlays/dev|prod`. `infra/`: Terraform y bootstrap.
- `.github/workflows/`: `terraform.yml` (plan/apply) e `infra-ops.yml` (apagar, encender, destruir).
- `docs/`: un documento por requisito, con su ID al inicio del nombre (`COM-02-arquitectura.md`,
  `COM-06-decisiones.md`, `DEV-13-reconstruccion.md`, `DEV-14-costos.md`). Capturas en `docs/evidencias/`
  con el mismo prefijo. Lo interno del equipo va en `docs/interno/`: el enunciado completo es
  `docs/interno/proyecto.md`; léelo por secciones solo cuando haga falta (es largo).

## Reglas

- Todo cambio entra por pull request; `main` está protegido.
- Nunca secretos, claves ni kubeconfigs en el repo. La IP de administración y los correos son *secrets*
  de GitHub, no variables.
- No ejecutar `terraform apply`/`destroy` ni acciones de `Infra ops` sin que lo pida la persona: crean
  o destruyen recursos que cobran. La VM se apaga al terminar cada sesión.
- Texto y comentarios en español, como el resto del repo.
