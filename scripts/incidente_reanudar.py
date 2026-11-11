"""Completa el análisis de una corrida de incidente.py desde la base de datos (MET-07).

Se usa cuando incidente.py se interrumpe después del tráfico (la lista de envíos vivía en memoria).
Las notificaciones de la corrida se reconocen por su asunto ("Incidente <corrida>") y la fase se
asigna por created_at con las marcas de la línea de tiempo guardada. Hace lo mismo que el final de
incidente.py: resumen antes de mitigar, reproceso de las fallidas por la API (admin), resumen
después de mitigar y reporte en docs/evidencias/MET-07-incidente-<corrida>.md y .json.

    source ~/notifier.env   # RESOURCE_GROUP, VM_NAME, API_URL
    export ADMIN_KEY=ntf_...
    python scripts/incidente_reanudar.py docs/evidencias/MET-07-linea-de-tiempo-2699b5ea.txt

Las consultas van a PostgreSQL dentro de la VM con scripts/vm.sh: la salida de run-command se
recorta a 4 KB, por eso se agregan en SQL y los IDs fallidos se leen por páginas.
Con SQL_LOCAL=1 usa psql local (NOTIFIER_DATABASE_URL), solo para probar el script.
"""

import base64
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parent.parent
API_URL = os.environ.get("API_URL", "http://localhost:8000")
ADMIN_KEY = os.environ.get("ADMIN_KEY", "")
NS = os.environ.get("NAMESPACE", "notifier-dev")
OBJETIVO_S = float(os.environ.get("OBJETIVO_S", "30"))
COLUMNAS = [
    "fase",
    "canal",
    "aceptadas",
    "entregadas",
    "fallidas",
    "sin_terminar",
    "sli_entrega_oportuna_pct",
    "intentos_promedio",
    "e2e_p50_s",
    "e2e_p95_s",
]


def sql(consulta: str) -> list[list[str]]:
    """Ejecuta la consulta y devuelve filas separadas por '|'."""
    if os.environ.get("SQL_LOCAL"):
        salida = subprocess.run(
            ["psql", os.environ["NOTIFIER_DATABASE_URL"], "-At", "-F|", "-v", "ON_ERROR_STOP=1"],
            input=consulta,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    else:
        b64 = base64.b64encode(consulta.encode()).decode()
        cmd = (
            f"echo {b64} | base64 -d | k3s kubectl -n {NS} exec -i postgres-0 -- "
            "psql -U notifier -d notifier -At -F'|' -v ON_ERROR_STOP=1"
        )
        r = subprocess.run([str(RAIZ / "scripts" / "vm.sh"), cmd], capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"falló vm.sh:\n{r.stdout}\n{r.stderr}")
        salida = r.stdout.split("[stdout]")[-1].split("[stderr]")[0]
        error = r.stdout.split("[stderr]")[-1].strip()
        if "ERROR" in error:
            sys.exit(f"error de PostgreSQL:\n{error}")
    return [linea.split("|") for linea in salida.splitlines() if "|" in linea or linea.strip()]


def marcas(archivo: str) -> tuple[str, str, str, list[str]]:
    texto = Path(archivo).read_text()
    lineas = [x for x in texto.splitlines() if re.match(r"\d{4}-\d\d-\d\dT", x)]
    corrida = re.search(r"corrida ([0-9a-f]{8})", texto).group(1)
    degradacion = next(x.split()[0] for x in lineas if "inicio: activar falla" in x)
    recuperacion = next(x.split()[0] for x in lineas if "inicio: quitar la falla" in x)
    return corrida, degradacion, recuperacion, lineas


def base(corrida: str, t_deg: str, t_rec: str) -> str:
    return f"""
WITH n AS (
  SELECT n.*, CASE WHEN n.created_at < '{t_deg}' THEN 'base'
                   WHEN n.created_at < '{t_rec}' THEN 'degradacion'
                   ELSE 'recuperacion' END AS fase,
         extract(epoch FROM n.delivered_at - n.created_at) AS e2e
  FROM notifications n WHERE n.subject = 'Incidente {corrida}')
"""


def resumen(cte: str) -> list[dict]:
    filas = sql(
        cte
        + f"""
SELECT fase, channel, count(*),
  count(*) FILTER (WHERE status = 'delivered'),
  count(*) FILTER (WHERE status = 'failed'),
  count(*) FILTER (WHERE status NOT IN ('delivered', 'failed')),
  round(100.0 * count(*) FILTER (WHERE e2e <= {OBJETIVO_S}) / count(*), 1),
  round(avg(attempts), 2),
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY e2e)::numeric, 2),
  round(percentile_cont(0.95) WITHIN GROUP (ORDER BY e2e)::numeric, 2)
FROM n GROUP BY fase, channel
ORDER BY array_position(ARRAY['base','degradacion','recuperacion'], fase), channel;"""
    )
    return [dict(zip(COLUMNAS, f, strict=True)) for f in filas if len(f) == len(COLUMNAS)]


def esperar(cte: str, limite_s: float = 300) -> list[dict]:
    """Resumen cuando ya no quedan notificaciones sin estado final (o al agotar el límite)."""
    limite = time.monotonic() + limite_s
    while True:
        filas = resumen(cte)
        pendientes = sum(int(f["sin_terminar"]) for f in filas)
        if pendientes == 0 or time.monotonic() > limite:
            return filas
        print(f"  quedan {pendientes} sin estado final; esperando...")
        time.sleep(15)


def fallidas(cte: str) -> list[str]:
    ids, pagina = [], 0
    while True:
        filas = sql(
            cte + f"SELECT id FROM n WHERE status = 'failed' ORDER BY id LIMIT 80 OFFSET {pagina};"
        )
        nuevos = [f[0].strip() for f in filas if re.fullmatch(r"[0-9a-f-]{36}", f[0].strip())]
        ids += nuevos
        if len(nuevos) < 80:
            return ids
        pagina += 80


def tabla(filas: list[dict], momento: str) -> list[str]:
    salida = [
        f"### {momento}",
        "",
        "| " + " | ".join(COLUMNAS) + " |",
        "|" + "---|" * len(COLUMNAS),
    ]
    salida += ["| " + " | ".join(f[c] for c in COLUMNAS) + " |" for f in filas]
    return salida + [""]


def main() -> None:
    if len(sys.argv) != 2 or not ADMIN_KEY:
        sys.exit(__doc__)
    corrida, t_deg, t_rec, lineas = marcas(sys.argv[1])
    cte = base(corrida, t_deg, t_rec)
    print(f"corrida {corrida}: degradación desde {t_deg}, recuperación desde {t_rec}")

    antes = esperar(cte)
    print("\n".join(tabla(antes, "Antes de mitigar")))
    ids = fallidas(cte)
    print(f"reprocesando {len(ids)} notificaciones fallidas (admin)...")
    inicio_mitigacion = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    errores = 0
    for i in ids:
        r = httpx.post(
            f"{API_URL}/v1/notifications/{i}/reprocess",
            headers={"X-API-Key": ADMIN_KEY},
            timeout=15,
        )
        errores += r.status_code != 202
    print(f"reproceso enviado ({errores} respuestas distintas de 202); esperando a que terminen...")

    time.sleep(15)
    despues = esperar(cte)
    fin_mitigacion = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print("\n".join(tabla(despues, "Después de mitigar")))

    reporte = [
        f"# MET-07: incidente controlado, corrida {corrida}",
        "",
        "## Línea de tiempo (UTC)",
        "",
        *[f"- `{x[:20]}` {x[20:].strip()}" for x in lineas],
        f"- `{inicio_mitigacion}` mitigación: reproceso de {len(ids)} notificaciones fallidas "
        f"(admin, {errores} respuestas distintas de 202)",
        f"- `{fin_mitigacion}` verificación posterior: estados finales tras el reproceso",
        "",
        "## Resultados por fase (fuente: tabla notifications en PostgreSQL de dev)",
        "",
        f"Fase asignada por created_at: base < {t_deg} ≤ degradación < {t_rec} ≤ recuperación. "
        f"SLI de entrega oportuna: entregadas en ≤ {OBJETIVO_S:g} s desde la aceptación.",
        "",
        *tabla(antes, "Antes de mitigar"),
        *tabla(despues, "Después de mitigar"),
        "Ejemplos de notificaciones fallidas para correlacionar (scripts/correlacion.sh):",
        *[f"- {i}" for i in ids[:3]],
    ]
    destino = RAIZ / "docs" / "evidencias" / f"MET-07-incidente-{corrida}"
    destino.with_suffix(".md").write_text("\n".join(reporte) + "\n")
    destino.with_suffix(".json").write_text(
        json.dumps(
            {"corrida": corrida, "antes": antes, "despues": despues, "fallidas": ids},
            indent=1,
            ensure_ascii=False,
        )
    )
    print(f"\nEvidencia: docs/evidencias/MET-07-incidente-{corrida}.md (y .json)")


if __name__ == "__main__":
    main()
