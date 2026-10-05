"""Compara una reproducción en otro equipo con los resultados de referencia.

El PTFG prevé un segundo equipo para la verificación cruzada de la corrección,
sin producir mediciones que ingresen a la comparación. Todo lo que no depende
del equipo debe coincidir exactamente: costos, rutas (longitud, exposición,
cantidad de tramos), contadores de esfuerzo y resultado de la verificación.
Los tiempos sí dependen del equipo: se informan solo de forma descriptiva.

Uso:
    python src/comparar_reproduccion.py --referencia referencia/tablas --area encarnacion
    python src/comparar_reproduccion.py --referencia referencia/tablas --area jersey_city

Escribe `resultados/tablas/reproduccion_<area>.json` con el informe.
"""
from __future__ import annotations

import argparse
import json
import pathlib

import numpy as np
import pandas as pd

from config import RES_TABLAS
import entorno

CLAVE = ["area", "modelo", "replica", "alfa", "par", "algoritmo"]
EXACTAS = ["origen", "destino", "aristas", "expandidos", "relajaciones", "mejoras", "pasadas", "verificado"]
REALES = ["longitud_m", "exposicion", "costo", "costo_networkx", "informatividad"]


def comparar(ref: pd.DataFrame, nue: pd.DataFrame) -> dict:
    faltan = len(ref.merge(nue[CLAVE], on=CLAVE, how="left", indicator=True).query("_merge == 'left_only'"))
    # filas de la reproducción sin referencia: si la referencia es parcial (por ejemplo,
    # solo algunas réplicas del modelo 1), se informan pero no cuentan como diferencia
    sin_referencia = len(nue.merge(ref[CLAVE], on=CLAVE, how="left", indicator=True).query("_merge == 'left_only'"))
    m = ref.merge(nue, on=CLAVE, suffixes=("_ref", "_nue"))
    columnas = {}
    for c in EXACTAS:
        a, b = m[f"{c}_ref"], m[f"{c}_nue"]
        iguales = (a == b) | (a.isna() & b.isna())
        columnas[c] = {"comparadas": int(len(m)), "distintas": int((~iguales).sum())}
    for c in REALES:
        a, b = m[f"{c}_ref"].astype(float), m[f"{c}_nue"].astype(float)
        iguales = np.isclose(a, b, rtol=1e-9, atol=1e-9) | (a.isna() & b.isna())
        columnas[c] = {"comparadas": int(len(m)), "distintas": int((~iguales).sum()),
                       "max_dif_relativa": float(np.nanmax(np.abs(a - b) / np.maximum(np.abs(a), 1e-12)))
                       if len(m) else 0.0}
    tiempos = (m.groupby("algoritmo")[["tiempo_ms_ref", "tiempo_ms_nue"]].median()
                .rename(columns={"tiempo_ms_ref": "mediana_ms_referencia", "tiempo_ms_nue": "mediana_ms_este_equipo"}))
    total_dist = sum(v["distintas"] for v in columnas.values())
    return {
        "filas_referencia": int(len(ref)), "filas_reproduccion": int(len(nue)),
        "filas_comparadas": int(len(m)),
        "faltan_en_reproduccion": faltan, "filas_sin_referencia": sin_referencia,
        "referencia_parcial": bool(sin_referencia > 0),
        "columnas": columnas,
        "coincide_todo_lo_determinista": bool(total_dist == 0 and faltan == 0 and len(m) > 0),
        "tiempos_descriptivos": tiempos.round(4).reset_index().to_dict(orient="records"),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Comparar una reproducción con la referencia")
    p.add_argument("--referencia", required=True, help="carpeta con mediciones_<area>.csv de referencia")
    p.add_argument("--area", required=True, choices=["encarnacion", "jersey_city"])
    args = p.parse_args()

    ref = pd.read_csv(pathlib.Path(args.referencia) / f"mediciones_{args.area}.csv")
    nue = pd.read_csv(RES_TABLAS / f"mediciones_{args.area}.csv")
    informe = {"area": args.area, "equipo": entorno.describir(), **comparar(ref, nue)}
    ruta = RES_TABLAS / f"reproduccion_{args.area}.json"
    ruta.write_text(json.dumps(informe, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(f"== reproducción {args.area}: {informe['filas_reproduccion']} filas; referencia: {informe['filas_referencia']}; "
          f"comparadas: {informe['filas_comparadas']}")
    if informe["referencia_parcial"]:
        print(f"   referencia parcial: {informe['filas_sin_referencia']} filas de la reproducción todavía no tienen "
              "referencia y no se comparan (no cuentan como diferencia)")
    for c, v in informe["columnas"].items():
        print(f"   {c:<16} distintas: {v['distintas']}")
    print("   RESULTADO:", "todo lo determinista coincide" if informe["coincide_todo_lo_determinista"]
          else "HAY DIFERENCIAS: revisar el informe")
    print(f"   -> {ruta.name}")


if __name__ == "__main__":
    main()
