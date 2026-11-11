# MET-07: incidente controlado, corrida 2699b5ea

## Línea de tiempo (UTC)

- `2026-11-11T00:36:13Z` corrida 2699b5ea: 2.0 solicitudes/s, fases de 300 s
- `2026-11-11T00:36:13Z` objetivo de entrega oportuna: 30 s
- `2026-11-11T00:36:13Z` fase base (proveedor sano)
- `2026-11-11T00:41:13Z` inicio: activar falla del proveedor de correo
- `2026-11-11T00:41:49Z` fin: activar falla del proveedor de correo
- `2026-11-11T00:46:49Z` inicio: quitar la falla del proveedor de correo
- `2026-11-11T00:47:25Z` fin: quitar la falla del proveedor de correo
- `2026-11-11T00:52:25Z` fin del tráfico: 1645 solicitudes aceptadas
- `2026-11-11T00:54:15Z` todas las notificaciones en estado final (o se agotó la espera)
- `2026-11-11T01:04:01Z` mitigación: reproceso de 81 notificaciones fallidas (admin, 0 respuestas distintas de 202)
- `2026-11-11T01:05:41Z` verificación posterior: estados finales tras el reproceso

## Resultados por fase (fuente: tabla notifications en PostgreSQL de dev)

Fase asignada por created_at: base < 2026-11-11T00:41:13Z ≤ degradación < 2026-11-11T00:46:49Z ≤ recuperación. SLI de entrega oportuna: entregadas en ≤ 30 s desde la aceptación.

### Antes de mitigar

| fase | canal | aceptadas | entregadas | fallidas | sin_terminar | sli_entrega_oportuna_pct | intentos_promedio | e2e_p50_s | e2e_p95_s |
|---|---|---|---|---|---|---|---|---|---|
| base | email | 351 | 351 | 0 | 0 | 100.0 | 1.00 | 0.52 | 0.97 |
| base | internal | 175 | 175 | 0 | 0 | 100.0 | 1.00 | 0.49 | 0.93 |
| degradacion | email | 381 | 300 | 81 | 0 | 78.7 | 1.94 | 0.99 | 16.10 |
| degradacion | internal | 190 | 190 | 0 | 0 | 100.0 | 1.00 | 0.52 | 0.97 |
| recuperacion | email | 366 | 366 | 0 | 0 | 100.0 | 1.02 | 0.52 | 0.99 |
| recuperacion | internal | 183 | 183 | 0 | 0 | 100.0 | 1.00 | 0.50 | 0.95 |

### Después de mitigar

| fase | canal | aceptadas | entregadas | fallidas | sin_terminar | sli_entrega_oportuna_pct | intentos_promedio | e2e_p50_s | e2e_p95_s |
|---|---|---|---|---|---|---|---|---|---|
| base | email | 351 | 351 | 0 | 0 | 100.0 | 1.00 | 0.52 | 0.97 |
| base | internal | 175 | 175 | 0 | 0 | 100.0 | 1.00 | 0.49 | 0.93 |
| degradacion | email | 381 | 381 | 0 | 0 | 78.7 | 2.15 | 5.61 | 1324.36 |
| degradacion | internal | 190 | 190 | 0 | 0 | 100.0 | 1.00 | 0.52 | 0.97 |
| recuperacion | email | 366 | 366 | 0 | 0 | 100.0 | 1.02 | 0.52 | 0.99 |
| recuperacion | internal | 183 | 183 | 0 | 0 | 100.0 | 1.00 | 0.50 | 0.95 |

Ejemplos de notificaciones fallidas para correlacionar (scripts/correlacion.sh):
- 02e7bade-b5d4-49f5-9a86-c378e0fa6ce4
- 082e50f4-b008-43e0-b3e4-1225a7a4f7e0
- 089a3111-7906-4f3d-8abe-299cd9e8a09d
