"""Carga controlada y repetible contra POST /v1/notifications.

Sirve para observar el dashboard de Grafana y sustentar los umbrales de las alertas.
Usa solo datos ficticios.

    export API_URL=http://localhost:8000 API_KEY=ntf_...
    python scripts/carga.py constante --rate 20 --duration 60
    python scripts/carga.py escalones --rates 5,20,40 --duration 90 --pausa 30

Opciones comunes:
    --canal email|internal|mixto   por defecto mixto (mitad y mitad, como smoke.py batch)
    --salida ruta.csv              opcional; no escribe dentro de docs/ si no se pide
    --esperar N                    segundos máximos para estados finales (por defecto 120)

Advertencia: la carga local en Windows no representa a la VM de Azure. Usar los mismos
parámetros en ambos entornos y anotar en qué entorno se corrió. El canal email local va a Mailpit.

Termina con código 1 si una comprobación falla. Que la cola se acumule no es una falla.
Si falta API_KEY, imprime este uso y sale con código 2.
"""

import argparse
import csv
import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime

import httpx

API_URL = os.environ.get("API_URL", "http://localhost:8000")
API_KEY = os.environ.get("API_KEY", "")
TERMINAL = {"delivered", "failed"}
MUESTRA_MAX = 100


def check(condition: bool, message: str) -> None:
    print(("OK    " if condition else "FALLA ") + message)
    if not condition:
        sys.exit(1)


def hora_local() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def percentil(valores: list[float], p: float) -> float | None:
    if not valores:
        return None
    ordenados = sorted(valores)
    if len(ordenados) == 1:
        return ordenados[0]
    k = (len(ordenados) - 1) * p
    bajo = int(k)
    alto = min(bajo + 1, len(ordenados) - 1)
    return ordenados[bajo] + (ordenados[alto] - ordenados[bajo]) * (k - bajo)


def fmt(valor: float | None, decimales: int) -> str:
    if valor is None:
        return "n/d"
    return f"{valor:.{decimales}f}"


def canal_de(canal: str, indice: int) -> str:
    # Igual que smoke.py batch: los impares van por correo y los pares por interno.
    if canal == "mixto":
        return "email" if indice % 2 else "internal"
    return canal


def destinatario(canal: str, corrida: str, rate: int, indice: int) -> str:
    base = f"carga-{corrida}-{rate}-{indice}"
    if canal == "email":
        return f"{base}@example.test"
    return base


@dataclass
class Envio:
    t_envio: float
    latencia_ms: float
    tarde: bool
    codigo: int | None
    excepcion: bool
    nid: str | None


@dataclass
class Nivel:
    rate: int
    enviadas: int
    tasa_real: float
    n_202: int
    n_4xx: int
    n_5xx: int
    excepciones: int
    tarde: int
    p50_ms: float | None
    p95_ms: float | None
    max_ms: float | None
    delivered: int
    failed: int
    pendientes: int
    mediana_final_s: float | None
    p95_final_s: float | None

    @property
    def errores(self) -> int:
        return self.enviadas - self.n_202


def fila(nivel: Nivel) -> list[str]:
    return [
        str(nivel.rate),
        fmt(nivel.tasa_real, 2),
        str(nivel.enviadas),
        str(nivel.n_202),
        str(nivel.errores),
        fmt(nivel.p50_ms, 1),
        fmt(nivel.p95_ms, 1),
        str(nivel.delivered),
        str(nivel.failed),
        str(nivel.pendientes),
        fmt(nivel.p95_final_s, 2),
    ]


COLUMNAS = [
    "rate objetivo",
    "tasa real",
    "enviadas",
    "202",
    "errores",
    "p50 ms",
    "p95 ms",
    "delivered",
    "failed",
    "pendientes",
    "tiempo final p95 s",
]


def imprimir_tabla(niveles: list[Nivel]) -> None:
    print("delivered, failed y pendientes son de la muestra (hasta 100), no del nivel completo.")
    print("| " + " | ".join(COLUMNAS) + " |")
    print("|" + "|".join("---" for _ in COLUMNAS) + "|")
    for nivel in niveles:
        print("| " + " | ".join(fila(nivel)) + " |")


def escribir_csv(ruta: str, niveles: list[Nivel]) -> None:
    with open(ruta, "w", newline="", encoding="utf-8") as salida:
        escritor = csv.writer(salida, lineterminator="\n")
        escritor.writerow(COLUMNAS)
        for nivel in niveles:
            escritor.writerow(fila(nivel))
    print(f"CSV escrito en {ruta}")


def enviar(
    client: httpx.Client, corrida: str, rate: int, indice: int, canal_modo: str, objetivo: float
) -> Envio:
    # El atraso se mide al salir el POST, no al encolarlo: si el pool va lleno, cuenta.
    t_envio = time.monotonic()
    tarde = t_envio - objetivo > 1.0
    canal = canal_de(canal_modo, indice)
    cuerpo = {
        "channel": canal,
        "recipient": destinatario(canal, corrida, rate, indice),
        "subject": f"Carga {corrida}",
        "body": f"m {indice}",
    }
    try:
        respuesta = client.post("/v1/notifications", json=cuerpo)
        latencia_ms = (time.monotonic() - t_envio) * 1000
    except httpx.HTTPError:
        return Envio(t_envio, (time.monotonic() - t_envio) * 1000, tarde, None, True, None)
    nid = None
    if respuesta.status_code == 202:
        try:
            nid = respuesta.json().get("id")
        except ValueError:
            nid = None
    return Envio(t_envio, latencia_ms, tarde, respuesta.status_code, False, nid)


def muestra_uniforme(envios: list[Envio], tope: int = MUESTRA_MAX) -> list[Envio]:
    con_id = [envio for envio in envios if envio.nid]
    if len(con_id) <= tope:
        return con_id
    ultimo = len(con_id) - 1
    indices = [(i * ultimo) // (tope - 1) for i in range(tope)]
    return [con_id[i] for i in indices]


def esperar_muestra(
    client: httpx.Client, muestra: list[Envio], esperar: float
) -> tuple[int, int, int, float | None, float | None]:
    if not muestra:
        print("muestra vacía: ninguna solicitud devolvió id")
        return 0, 0, 0, None, None
    por_id = {envio.nid: envio for envio in muestra if envio.nid}
    estados: dict[str, str] = {}
    t_final: dict[str, float] = {}
    limite = time.monotonic() + esperar

    def leer(nid: str) -> tuple[str, str | None]:
        try:
            respuesta = client.get(f"/v1/notifications/{nid}")
        except httpx.HTTPError:
            return nid, None
        if respuesta.status_code != 200:
            return nid, None
        try:
            return nid, respuesta.json().get("status")
        except ValueError:
            return nid, None

    while por_id:
        with ThreadPoolExecutor(max_workers=min(32, len(por_id))) as pool:
            for nid, estado in pool.map(leer, list(por_id)):
                if estado in TERMINAL:
                    t_final[nid] = time.monotonic()
                    estados[nid] = estado
                    por_id.pop(nid, None)
        if not por_id or time.monotonic() >= limite:
            break
        time.sleep(2)

    delivered = sum(estado == "delivered" for estado in estados.values())
    failed = sum(estado == "failed" for estado in estados.values())
    pendientes = len(muestra) - delivered - failed
    por_nid = {envio.nid: envio for envio in muestra}
    tiempos = [momento - por_nid[nid].t_envio for nid, momento in t_final.items()]
    mediana = percentil(tiempos, 0.50)
    p95 = percentil(tiempos, 0.95)
    print(
        f"muestra {len(muestra)}: delivered {delivered}, failed {failed}, "
        f"pendientes {pendientes}; tiempo final mediana {fmt(mediana, 2)} s, "
        f"p95 {fmt(p95, 2)} s"
    )
    if pendientes:
        print(
            f"quedan {pendientes} de la muestra sin estado final tras {esperar:.0f} s: "
            "la cola se está acumulando (observación, no es un error del script)"
        )
    return delivered, failed, pendientes, mediana, p95


def ejecutar_nivel(
    client: httpx.Client,
    corrida: str,
    rate: int,
    duration: int,
    canal: str,
    esperar: float,
) -> Nivel:
    n = rate * duration
    hilos = min(200, max(10, rate * 2))
    print(
        f"inicio hora={hora_local()} nivel={rate} enviadas=0 tasa_real=0 "
        "p50_ms=n/d p95_ms=n/d max_ms=n/d"
    )
    print(f"plan: {n} solicitudes a {rate}/s durante {duration} s, {hilos} hilos, canal {canal}")
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=hilos) as pool:
        futuros = []
        for indice in range(n):
            objetivo = t0 + indice / rate
            espera = objetivo - time.monotonic()
            if espera > 0:
                time.sleep(espera)
            # Lazo abierto: se encola y se sigue. La respuesta no frena el ritmo.
            futuros.append(pool.submit(enviar, client, corrida, rate, indice, canal, objetivo))
        envios = [futuro.result() for futuro in futuros]
    t_ultimo = max(envio.t_envio for envio in envios)
    tasa_real = n / max(t_ultimo - t0, 1e-9)
    latencias = [envio.latencia_ms for envio in envios]
    n_202 = sum(envio.codigo == 202 for envio in envios)
    n_4xx = sum(envio.codigo is not None and 400 <= envio.codigo < 500 for envio in envios)
    n_5xx = sum(envio.codigo is not None and 500 <= envio.codigo < 600 for envio in envios)
    excepciones = sum(envio.excepcion for envio in envios)
    tarde = sum(envio.tarde for envio in envios)
    p50 = percentil(latencias, 0.50)
    p95 = percentil(latencias, 0.95)
    max_ms = max(latencias) if latencias else None
    print(
        f"fin hora={hora_local()} nivel={rate} enviadas={n} tasa_real={tasa_real:.2f} "
        f"202={n_202} 4xx={n_4xx} 5xx={n_5xx} excepciones={excepciones} "
        f"p50_ms={fmt(p50, 1)} p95_ms={fmt(p95, 1)} max_ms={fmt(max_ms, 1)} "
        f"salieron_mas_de_1s_tarde={tarde}"
    )
    delivered, failed, pendientes, mediana, p95_final = esperar_muestra(
        client, muestra_uniforme(envios), esperar
    )
    return Nivel(
        rate,
        n,
        tasa_real,
        n_202,
        n_4xx,
        n_5xx,
        excepciones,
        tarde,
        p50,
        p95,
        max_ms,
        delivered,
        failed,
        pendientes,
        mediana,
        p95_final,
    )


def parsear() -> argparse.Namespace:
    comun = argparse.ArgumentParser(add_help=False)
    comun.add_argument("--canal", choices=("email", "internal", "mixto"), default="mixto")
    comun.add_argument("--salida", default=None)
    comun.add_argument("--esperar", type=float, default=120)
    comun.add_argument("--duration", type=int, required=True)
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="modo", required=True)
    constante = sub.add_parser("constante", parents=[comun])
    constante.add_argument("--rate", type=int, required=True)
    escalones = sub.add_parser("escalones", parents=[comun])
    escalones.add_argument("--rates", required=True)
    escalones.add_argument("--pausa", type=float, default=0)
    return parser.parse_args()


def validar(args: argparse.Namespace) -> list[int]:
    if args.modo == "constante":
        rates = [args.rate]
    else:
        try:
            rates = [int(parte) for parte in args.rates.split(",") if parte.strip() != ""]
        except ValueError:
            print("rates debe ser una lista de enteros, por ejemplo 5,20,40", file=sys.stderr)
            sys.exit(2)
        if not rates:
            print("rates no puede estar vacío", file=sys.stderr)
            sys.exit(2)
    for rate in rates:
        if not 1 <= rate <= 200:
            print(f"rate fuera de rango (1..200): {rate}", file=sys.stderr)
            sys.exit(2)
    if not 5 <= args.duration <= 600:
        print(f"duration fuera de rango (5..600): {args.duration}", file=sys.stderr)
        sys.exit(2)
    if args.esperar < 0:
        print(f"esperar no puede ser negativo: {args.esperar}", file=sys.stderr)
        sys.exit(2)
    pausa = getattr(args, "pausa", 0)
    if pausa < 0:
        print(f"pausa no puede ser negativa: {pausa}", file=sys.stderr)
        sys.exit(2)
    return rates


def comprobar_api(client: httpx.Client) -> None:
    try:
        respuesta = client.get("/healthz")
    except httpx.HTTPError as exc:
        print(f"la API no responde en {API_URL}/healthz: {exc}", file=sys.stderr)
        sys.exit(1)
    if respuesta.status_code != 200:
        print(f"la API no responde bien en /healthz ({respuesta.status_code})", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    if not API_KEY:
        print(__doc__)
        sys.exit(2)
    args = parsear()
    rates = validar(args)
    corrida = uuid.uuid4().hex[:8]
    pausa = getattr(args, "pausa", 0)
    print(f"destino {API_URL} corrida {corrida} canal {args.canal} modo {args.modo}")
    limites = httpx.Limits(max_connections=200, max_keepalive_connections=200)
    with httpx.Client(
        base_url=API_URL, headers={"X-API-Key": API_KEY}, timeout=15, limits=limites
    ) as client:
        comprobar_api(client)
        niveles: list[Nivel] = []
        for posicion, rate in enumerate(rates):
            niveles.append(
                ejecutar_nivel(client, corrida, rate, args.duration, args.canal, args.esperar)
            )
            if posicion < len(rates) - 1 and pausa > 0:
                print(f"pausa {pausa:.0f} s sin enviar, hora={hora_local()}")
                time.sleep(pausa)
        if args.modo == "escalones":
            imprimir_tabla(niveles)
        if args.salida:
            escribir_csv(args.salida, niveles)
        for nivel in niveles:
            ratio = nivel.n_202 / nivel.enviadas if nivel.enviadas else 0
            check(
                ratio >= 0.99,
                f"nivel {nivel.rate}: {nivel.n_202}/{nivel.enviadas} respuestas 202 ({ratio:.1%})",
            )
            check(
                nivel.excepciones == 0,
                f"nivel {nivel.rate}: {nivel.excepciones} excepciones de red",
            )


if __name__ == "__main__":
    main()
