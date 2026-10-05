"""Orquestador de la canalización completa.

Uso:
    python src/ejecutar.py --area encarnacion
    python src/ejecutar.py --area jersey_city                 (modelos M1 y M2)
    python src/ejecutar.py --area jersey_city --modelo M2
    python src/ejecutar.py --area encarnacion --prueba        (muestra reducida)

Produce `resultados/tablas/mediciones_<area>.csv`, entrada única del análisis,
y `resultados/tablas/estructura_<area>.json` con las medidas del grafo, la
preparación de los datos, la asignación de severidad y la verificación.
"""
from __future__ import annotations

import argparse
import json
import time

from config import CFG, RAIZ, RES_TABLAS, area as cfg_area
import entorno
import experimento as exp
import grafo as gr
import preparacion as prep
import verificacion as ver


def semilla_replica(replica: int) -> int:
    """Semilla de cada sorteo del modelo 1, derivada de la semilla maestra."""
    return CFG["semilla_maestra"] + 1000 * (replica + 1)


def registros_de(area_cfg: dict, modelo: str, replica: int = 0,
                 radio: float | None = None) -> tuple[list[dict], dict]:
    """Lee la fuente, la depura y asigna la clase según el modelo."""
    ruta = RAIZ / area_cfg["fuente_baches"]
    regs = prep.leer_kml(str(ruta)) if area_cfg["formato"] == "kml" else prep.leer_csv(str(ruta))
    regs, info = prep.depurar(regs, area_cfg["bbox"])

    if modelo == "observado":
        if any(r["clase"] is None for r in regs):
            raise ValueError("el modelo «observado» exige que la fuente publique la clase")
        info["clases"] = {c: sum(1 for r in regs if r["clase"] == c)
                          for c in CFG["clases"]["baches_representados"]}
    elif modelo == "M1":
        regs, info["modelo"] = prep.modelo_proporcion(regs, semilla_replica(replica))
    elif modelo == "M2":
        regs, info["modelo"] = prep.modelo_radio(regs, area_cfg["epsg_metrico"], radio)
    else:
        raise ValueError(f"modelo desconocido: {modelo}")
    return regs, info


def main() -> None:
    p = argparse.ArgumentParser(description="Canalización de la MTFG")
    p.add_argument("--area", default="encarnacion", choices=list(CFG["areas"]))
    p.add_argument("--modelo", nargs="+", default=None,
                   help="por omisión, los modelos del área en config.yaml")
    p.add_argument("--prueba", action="store_true",
                   help="muestra reducida (5 pares, 1 réplica), para comprobar que todo corre")
    args = p.parse_args()

    a = cfg_area(args.area)
    modelos = args.modelo or a["modelos"]
    for m in modelos:
        if m not in a["modelos"]:
            raise SystemExit(f"el modelo {m} no corresponde a {args.area}: {a['modelos']}")
    pares_n = 5 if args.prueba else CFG["experimento"]["pares_od"]

    print(f"== {a['nombre']} ({a['rol']}) · modelos {', '.join(modelos)}")
    t0 = time.time()
    G = gr.construir(a)
    correcciones = gr.aplicar_correcciones_sentido(G)
    est = gr.resumen(G)
    print(f"   grafo: {est['nodos']} nodos, {est['aristas']} aristas, "
          f"{est['long_total_km']} km  [{time.time() - t0:.1f} s]")

    # Los pares se sortean una sola vez con la semilla maestra y son los mismos
    # para los tres algoritmos, todos los α, todos los modelos y todas las
    # réplicas: la dispersión entre réplicas del modelo 1 mide solo el sorteo
    # de clases.
    pares = exp.generar_pares(G, pares_n, CFG["semilla_maestra"])
    print(f"   {len(pares)} pares origen-destino a ≥ {CFG['experimento']['distancia_minima_m']} m")

    filas: list[dict] = []
    informe = {"area": a["nombre"], "estructura": est, "entorno": entorno.describir(),
               "correcciones_sentido": correcciones, "pares": len(pares), "corridas": []}

    for modelo in modelos:
        replicas = 1 if args.prueba or modelo != "M1" else CFG["modelos"]["M1"]["replicas"]
        for replica in range(replicas):
            t1 = time.time()
            regs, info = registros_de(a, modelo, replica)
            G, asig = gr.asignar_severidad(G, regs, a["epsg_metrico"])
            verif_costos = []
            for alfa in CFG["costo"]["alfas"]:
                G = gr.ponderar(G, alfa)
                verif_costos.append(exp.ejecutar(G, pares, args.area, modelo, replica, alfa, filas))
            discrep = sum(v["discrepancias"] for v in verif_costos)
            corrida = {"modelo": modelo, "replica": replica, "preparacion": info,
                       "asignacion": asig, "verificacion_costos": verif_costos}
            if replica == 0:
                G = gr.ponderar(G, CFG["costo"]["alfas"][-1])
                muestra = pares[:5]
                corrida["verificacion"] = {
                    "integridad": ver.integridad_grafo(G),
                    "admisibilidad": ver.admisibilidad(G, muestra[:2]),
                    "sentidos_respetados": ver.sentidos_respetados(G, muestra),
                    "trazas_coherentes": ver.trazas_coherentes(G, muestra),
                }
            informe["corridas"].append(corrida)
            print(f"   {modelo} réplica {replica + 1}/{replicas}: {asig['registros_asignados']} registros, "
                  f"{asig['aristas_con_deterioro']} aristas con baches, d95 = {asig['d95_baches_por_m']}; "
                  f"discrepancias de costo: {discrep}  [{time.time() - t1:.1f} s]")
            if discrep:
                print("   *** ATENCIÓN: la serie no supera la verificación de costos ***")

    csv_ruta = RES_TABLAS / f"mediciones_{args.area}{'_prueba' if args.prueba else ''}.csv"
    exp.volcar(filas, csv_ruta)
    json_ruta = RES_TABLAS / f"estructura_{args.area}{'_prueba' if args.prueba else ''}.json"
    with open(json_ruta, "w", encoding="utf-8") as fh:
        json.dump(informe, fh, ensure_ascii=False, indent=2, default=str)

    print(f"   {len(filas)} mediciones -> {csv_ruta.name}")
    print(f"   estructura y verificación -> {json_ruta.name}")
    print(f"   total {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
