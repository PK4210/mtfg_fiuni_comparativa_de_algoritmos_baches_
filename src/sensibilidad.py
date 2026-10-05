"""Análisis complementario de sensibilidad a b y al radio del modelo 2.

El valor b = 12 (baches que representa una agrupación) es una estimación
derivada de las cifras del relevamiento de Encarnación (PTFG rev6, limitación
7), y el radio de 10 m del modelo 2 se fijó a partir de la separación entre
marcas individuales. Este script comprueba cuánto de lo concluido depende de
esos dos valores. No forma parte del protocolo principal: lo complementa.

  Encarnación          b ∈ {1, 6, 12, 24}
  Jersey City, M2      b ∈ {1, 6, 12, 24} con radio 10 m, y radio ∈ {5, 10, 15} m con b = 12

Con b = 1 la distinción entre clases desaparece y la severidad de un tramo se
reduce a la cantidad de registros: sirve de caso de referencia.

El script no toca `config.yaml`: modifica la configuración en memoria, y el
archivo sigue siendo la única fuente de verdad del experimento principal.

Uso:
    python src/sensibilidad.py --area encarnacion
    python src/sensibilidad.py --area jersey_city
"""
from __future__ import annotations

import argparse
import time

import pandas as pd

from config import CFG, RES_TABLAS, area as cfg_area
import analisis as an
import ejecutar
import experimento as exp
import grafo as gr


def corrida(G, a: dict, nombre_area: str, modelo: str, pares: list, baches: float,
            radio: float | None) -> list[dict]:
    CFG["clases"]["baches_representados"]["agrupacion"] = baches
    regs, _ = ejecutar.registros_de(a, modelo, 0, radio)
    G, _ = gr.asignar_severidad(G, regs, a["epsg_metrico"])
    filas: list[dict] = []
    for alfa in CFG["costo"]["alfas"]:
        gr.ponderar(G, alfa)
        v = exp.ejecutar(G, pares, nombre_area, modelo, 0, alfa, filas)
        if v["discrepancias"]:
            raise SystemExit(f"discrepancias de costo con b={baches}, radio={radio}, α={alfa}")
    for f in filas:
        f["b"] = baches
        f["radio_m"] = radio
    return filas


def main() -> None:
    p = argparse.ArgumentParser(description="Sensibilidad a b y al radio del modelo 2")
    p.add_argument("--area", default="encarnacion", choices=list(CFG["areas"]))
    args = p.parse_args()

    a = cfg_area(args.area)
    sens = CFG["sensibilidad"]
    if args.area == "encarnacion":
        modelo, radio_base = "observado", None
        barrido = [("b", b, None) for b in sens["baches_agrupacion"]]
    else:
        modelo, radio_base = "M2", CFG["modelos"]["M2"]["radio_m"]
        barrido = [("b", b, radio_base) for b in sens["baches_agrupacion"]]
        barrido += [("radio_m", r, r) for r in sens["radios_m"] if r != radio_base]
    b_base = CFG["clases"]["baches_representados"]["agrupacion"]

    print(f"== {a['nombre']} · sensibilidad ({modelo})")
    G = gr.construir(a)
    gr.aplicar_correcciones_sentido(G)
    pares = exp.generar_pares(G, CFG["experimento"]["pares_od"], CFG["semilla_maestra"])
    filas: list[dict] = []
    t0 = time.time()
    try:
        for variable, valor, radio in barrido:
            t = time.time()
            b = valor if variable == "b" else b_base
            nuevas = corrida(G, a, args.area, modelo, pares, b, radio)
            for f in nuevas:
                f["variable"] = variable
            filas += nuevas
            print(f"   {variable} = {valor:<4} listo  [{time.time() - t:.1f} s]")
    finally:
        CFG["clases"]["baches_representados"]["agrupacion"] = b_base

    df = pd.DataFrame(filas)
    df["replica"] = df["variable"] + "=" + df.apply(
        lambda f: str(f["b"] if f["variable"] == "b" else f["radio_m"]), axis=1)
    df = an.desvio_relativo(df)
    salida = []
    for (variable, rep, alfa, algo), g in df.groupby(["variable", "replica", "alfa", "algoritmo"]):
        e = an._estadisticos(g)
        salida.append({"variable": variable, "valor": rep.split("=")[1], "alfa": alfa,
                       "algoritmo": an.ETIQUETAS[algo], **{k: e[k] for k in (
                           "n_pares", "tiempo_ms_mediana", "expandidos_mediana",
                           "exposicion_media", "desvio_pct_media", "informatividad_media")}})
    res = pd.DataFrame(salida)
    ruta = RES_TABLAS / f"sensibilidad_{args.area}.csv"
    res.round(5).to_csv(ruta, index=False)
    print(f"   {len(filas)} mediciones -> {ruta.name}  [total {time.time() - t0:.1f} s]")


if __name__ == "__main__":
    main()
