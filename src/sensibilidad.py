"""Análisis de sensibilidad al número de baches que representa una agrupación.

La sección 3.2.4 de la memoria estima en doce los baches que representa cada
marca de agrupación, a partir de la cota que declara el relevamiento: 359
marcas frente a más de setecientos cincuenta baches individuales. Es una
estimación derivada de una cota, no una medición, de modo que corresponde
comprobar cuánto de lo concluido depende de ese valor.

Se corre sobre Encarnación y no sobre la red de contraste, por una razón de
fondo: allí la agrupación es una clase efectivamente observada en el
relevamiento, mientras que en Jersey City es un atributo sintético obtenido por
transferencia de distribución. Variar el parámetro sobre una clase sintética
mediría el efecto de una suposición sobre otra.

El barrido incluye b = 1, que anula la distinción entre clases: con ese valor
toda marca contribuye lo mismo y la severidad de un tramo se reduce a un
conteo de marcas. Sirve de caso degenerado de referencia.

El script no toca `config.yaml`: muta la configuración en memoria, de modo que
el archivo sigue siendo la única fuente de verdad del experimento principal.

Uso:
    python src/sensibilidad.py --area encarnacion
"""
from __future__ import annotations

import argparse
import collections
import csv
import statistics as st
import time

from config import CFG, RES_TABLAS, area as cfg_area
import ejecutar
import experimento as exp
import grafo as gr

VALORES = [1, 6, 12, 24]        # 12 es el adoptado en la memoria
ETIQUETAS = {"dijkstra": "Dijkstra", "a_estrella": "A*",
             "bellman_ford": "Bellman-Ford"}


def corrida(area_cfg: dict, nombre_area: str, baches: int, pares: list) -> list:
    """Una serie completa de mediciones con un valor de b(agrupación)."""
    # la mutación es deliberada y local: `preparacion.contribucion` lee de CFG
    CFG["clases"]["baches_representados"]["agrupacion"] = baches

    G = gr.construir(area_cfg)
    gr.aplicar_correcciones_sentido(G)
    regs, _ = ejecutar.registros_de(area_cfg, nombre_area, "C2",
                                    CFG["semilla_maestra"])
    G, _ = gr.asignar_severidad(G, regs, area_cfg["epsg_metrico"])

    filas: list[dict] = []
    for alfa in CFG["costo"]["alfas"]:
        G = gr.ponderar(G, alfa)
        exp.ejecutar(G, pares, nombre_area, "C2", 0, alfa, filas)
    for f in filas:
        f["baches_agrupacion"] = baches
    return filas


def agregar(filas: list[dict]) -> list[dict]:
    """Media por valor de b, α y algoritmo, sobre los pares comunes."""
    grupos = collections.defaultdict(list)
    for f in filas:
        grupos[(f["baches_agrupacion"], f["alfa"], f["algoritmo"])].append(f)

    # Bellman-Ford corre sobre menos pares: se restringe a la intersección
    por_algo = collections.defaultdict(set)
    for f in filas:
        por_algo[f["algoritmo"]].add(
            (f["baches_agrupacion"], f["alfa"], f["origen"], f["destino"]))
    comunes = set.intersection(*por_algo.values())

    salida = []
    for (b, alfa, algo), g in sorted(grupos.items()):
        g = [f for f in g
             if (f["baches_agrupacion"], f["alfa"], f["origen"],
                 f["destino"]) in comunes]
        if not g:
            continue
        salida.append({
            "baches_agrupacion": b,
            "alfa": alfa,
            "algoritmo": ETIQUETAS.get(algo, algo),
            "n": len(g),
            "tiempo_ms": round(st.mean(f["tiempo_ms"] for f in g), 4),
            "nodos_expandidos": (round(st.mean(f["expandidos"] for f in g), 1)
                                 if algo != "bellman_ford" else None),
            "longitud_m": round(st.mean(f["longitud_m"] for f in g), 1),
            "exposicion": round(st.mean(f["exposicion"] for f in g), 3),
            "informatividad": (round(st.mean(f["informatividad"] for f in g), 4)
                               if algo == "a_estrella" else None),
        })
    return salida


def main() -> None:
    p = argparse.ArgumentParser(description="Sensibilidad a b(agrupación)")
    p.add_argument("--area", default="encarnacion", choices=list(CFG["areas"]))
    args = p.parse_args()

    a = cfg_area(args.area)
    print(f"== {a['nombre']}: sensibilidad a los baches por agrupación")
    original = CFG["clases"]["baches_representados"]["agrupacion"]
    t0 = time.time()

    # los pares son los mismos en todo el barrido: lo único que varía es b
    G = gr.construir(a)
    gr.aplicar_correcciones_sentido(G)
    G = gr.ponderar(G, 0.0)
    pares = exp.generar_pares(G, CFG["experimento"]["pares_od"],
                              CFG["semilla_maestra"])
    print(f"   {len(pares)} pares origen-destino, fijos para todo el barrido")

    filas: list[dict] = []
    try:
        for b in VALORES:
            t = time.time()
            filas += corrida(a, args.area, b, pares)
            marca = "  (adoptado en la memoria)" if b == original else ""
            print(f"   b = {b:<3} listo  [{time.time() - t:.1f} s]{marca}")
    finally:
        CFG["clases"]["baches_representados"]["agrupacion"] = original

    resumen = agregar(filas)
    ruta = RES_TABLAS / f"sensibilidad_{args.area}.csv"
    with open(ruta, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(resumen[0]))
        w.writeheader()
        w.writerows(resumen)
    print(f"   {len(filas)} mediciones -> {ruta.name}")
    print(f"   total {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
