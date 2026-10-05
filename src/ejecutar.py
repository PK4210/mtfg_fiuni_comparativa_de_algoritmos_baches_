"""Orquestador de la canalización completa.

Uso:
    python src/ejecutar.py --area encarnacion
    python src/ejecutar.py --area jersey_city --config C2 C3
    python src/ejecutar.py --area encarnacion --prueba     (muestra reducida)

Produce `resultados/tablas/mediciones_<area>.csv`, entrada única del análisis,
y `resultados/tablas/estructura_<area>.json` con las medidas del grafo y las
comprobaciones de verificación.
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


def registros_de(area_cfg: dict, nombre_area: str, configuracion: str,
                 semilla: int) -> tuple[list[dict], dict]:
    """Lee la fuente, la depura y resuelve la clase de cada registro."""
    ruta = RAIZ / area_cfg["fuente_baches"]
    if area_cfg["formato"] == "kml":
        regs = prep.leer_kml(str(ruta))
    else:
        regs = prep.leer_csv(str(ruta))
    regs, info = prep.depurar(regs, area_cfg["bbox"])

    if any(r["clase"] is None for r in regs):
        # la fuente no publica clase: se transfiere la de Encarnación
        origen = prep.leer_kml(str(RAIZ / cfg_area("encarnacion")["fuente_baches"]))
        origen, _ = prep.depurar(origen, cfg_area("encarnacion")["bbox"])
        clases = prep.transferir_distribucion(
            [r["clase"] for r in origen], len(regs), semilla, configuracion)
        for r, c in zip(regs, clases):
            r["clase"] = c
        info["clases_transferidas"] = True
    else:
        info["clases_transferidas"] = False
    return regs, info


def main() -> None:
    p = argparse.ArgumentParser(description="Canalización de la MTFG")
    p.add_argument("--area", default="encarnacion", choices=list(CFG["areas"]))
    p.add_argument("--config", nargs="+", default=["C2"],
                   choices=list(CFG["configuraciones"]))
    p.add_argument("--prueba", action="store_true",
                   help="muestra reducida, para comprobar que todo corre")
    args = p.parse_args()

    a = cfg_area(args.area)
    semilla = CFG["semilla_maestra"]
    pares_n = 5 if args.prueba else CFG["experimento"]["pares_od"]
    replicas = 1 if args.prueba else CFG["experimento"]["replicas_asignacion"]
    if args.area == "encarnacion":
        replicas = 1          # su clase es observada: no hay sorteo que replicar

    print(f"== {a['nombre']} ({a['rol']})")
    t0 = time.time()
    G = gr.construir(a)
    correcciones = gr.aplicar_correcciones_sentido(G)
    est = gr.resumen(G)
    print(f"   grafo: {est['nodos']} nodos, {est['aristas']} aristas, "
          f"{est['long_total_km']} km  [{time.time() - t0:.1f} s]")

    filas: list[dict] = []
    informe = {"area": a["nombre"], "estructura": est,
               "entorno": entorno.describir(),
               "correcciones_sentido": correcciones, "corridas": []}

    # Los pares origen-destino se sortean una sola vez, con la semilla maestra,
    # y son los mismos en todas las réplicas y configuraciones. Es lo que
    # permite que la dispersión entre réplicas mida el sorteo de clases de la
    # ecuación (14) y nada más: si cada réplica muestreara pares distintos, esa
    # dispersión combinaría el sorteo con el remuestreo y dejaría de ser
    # atribuible a lo que la Tabla 3.10 declara. El grafo no cambia de
    # estructura entre réplicas, de modo que un único sorteo basta.
    G = gr.ponderar(G, CFG["costo"]["alfas"][0])
    pares = exp.generar_pares(G, pares_n, semilla)
    muestra = exp.generar_pares(G, min(5, pares_n), semilla)
    print(f"   {len(pares)} pares origen-destino, fijos para todas las réplicas")

    for configuracion in args.config:
        for replica in range(replicas):
            sem = semilla + replica * 1000
            regs, info = registros_de(a, args.area, configuracion, sem)
            G, asig = gr.asignar_severidad(G, regs, a["epsg_metrico"])
            if replica == 0:
                print(f"   {configuracion}: {info['retenidos']} registros, "
                      f"{asig['aristas_con_deterioro']} aristas con deterioro "
                      f"({asig['cobertura_aristas_pct']} %)")

            for alfa in CFG["costo"]["alfas"]:
                G = gr.ponderar(G, alfa)
                exp.ejecutar(G, pares, args.area, configuracion, replica,
                             alfa, filas)

            if replica == 0:
                G = gr.ponderar(G, CFG["costo"]["alfas"][-1])
                informe["corridas"].append({
                    "configuracion": configuracion,
                    "preparacion": info,
                    "asignacion": asig,
                    "verificacion": {
                        "integridad": ver.integridad_grafo(G),
                        "optimalidad_cruzada": ver.optimalidad_cruzada(G, muestra),
                        "contra_networkx": ver.contra_networkx(G, muestra),
                        "admisibilidad": ver.admisibilidad(G, muestra[:2]),
                        "sentidos_respetados": ver.sentidos_respetados(G, muestra),
                        "trazas_coherentes": ver.trazas_coherentes(G, muestra),
                        "expansion_dibujable": ver.expansion_dibujable(
                            G, muestra[:2]),
                    },
                })

    csv_ruta = RES_TABLAS / f"mediciones_{args.area}.csv"
    exp.volcar(filas, csv_ruta)
    json_ruta = RES_TABLAS / f"estructura_{args.area}.json"
    with open(json_ruta, "w", encoding="utf-8") as fh:
        json.dump(informe, fh, ensure_ascii=False, indent=2)

    print(f"   {len(filas)} mediciones -> {csv_ruta.name}")
    print(f"   estructura y verificación -> {json_ruta.name}")
    print(f"   total {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
