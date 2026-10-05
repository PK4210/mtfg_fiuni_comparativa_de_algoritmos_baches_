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
import csv
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


def _partes(area: str, prueba: bool):
    """Carpeta donde cada (modelo, réplica) deja su resultado apenas termina."""
    d = RES_TABLAS / "partes" / (area + ("_prueba" if prueba else ""))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _replicas(modelo: str, prueba: bool) -> int:
    return 1 if prueba or modelo != "M1" else CFG["modelos"]["M1"]["replicas"]


def unir(area: str, a: dict, modelos: list[str], prueba: bool, base: dict) -> bool:
    """Si están todas las partes, las une en mediciones_<area>.csv y estructura_<area>.json."""
    d = _partes(area, prueba)
    esperadas = [(m, r) for m in modelos for r in range(_replicas(m, prueba))]
    faltan = [(m, r) for m, r in esperadas if not (d / f"{m}_r{r:02d}.csv").exists()]
    if faltan:
        print(f"   faltan {len(faltan)} de {len(esperadas)} partes; se unirán cuando estén todas", flush=True)
        return False
    filas, corridas = [], []
    for m, r in esperadas:
        with open(d / f"{m}_r{r:02d}.csv", encoding="utf-8") as fh:
            filas += list(csv.DictReader(fh))
        corridas.append(json.loads((d / f"{m}_r{r:02d}.json").read_text(encoding="utf-8")))
    sufijo = "_prueba" if prueba else ""
    exp.volcar(filas, RES_TABLAS / f"mediciones_{area}{sufijo}.csv")
    informe = dict(base, corridas=corridas)
    (RES_TABLAS / f"estructura_{area}{sufijo}.json").write_text(
        json.dumps(informe, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    discrep = sum(v["discrepancias"] for c in corridas for v in c["verificacion_costos"])
    print(f"   unidas {len(esperadas)} partes: {len(filas)} mediciones -> mediciones_{area}{sufijo}.csv; "
          f"discrepancias de costo en total: {discrep}", flush=True)
    return True


def main() -> None:
    p = argparse.ArgumentParser(description="Canalización de la MTFG")
    p.add_argument("--area", default="encarnacion", choices=list(CFG["areas"]))
    p.add_argument("--modelo", nargs="+", default=None,
                   help="por omisión, los modelos del área en config.yaml")
    p.add_argument("--replicas", nargs=2, type=int, metavar=("DESDE", "HASTA"), default=None,
                   help="solo para M1: corre las réplicas DESDE..HASTA-1 (por tandas)")
    p.add_argument("--prueba", action="store_true",
                   help="muestra reducida (5 pares, 1 réplica), para comprobar que todo corre")
    args = p.parse_args()

    a = cfg_area(args.area)
    modelos = args.modelo or a["modelos"]
    for m in modelos:
        if m not in a["modelos"]:
            raise SystemExit(f"el modelo {m} no corresponde a {args.area}: {a['modelos']}")
    pares_n = 5 if args.prueba else CFG["experimento"]["pares_od"]

    print(f"== {a['nombre']} ({a['rol']}) · modelos {', '.join(modelos)}", flush=True)
    t0 = time.time()
    G = gr.construir(a)
    correcciones = gr.aplicar_correcciones_sentido(G)
    est = gr.resumen(G)
    print(f"   grafo: {est['nodos']} nodos, {est['aristas']} aristas, "
          f"{est['long_total_km']} km  [{time.time() - t0:.1f} s]", flush=True)

    # Los pares se sortean una sola vez con la semilla maestra y son los mismos
    # para los tres algoritmos, todos los α, todos los modelos y todas las
    # réplicas: la dispersión entre réplicas del modelo 1 mide solo el sorteo
    # de clases. Como el sorteo es determinista, cada tanda obtiene los mismos.
    pares = exp.generar_pares(G, pares_n, CFG["semilla_maestra"])
    print(f"   {len(pares)} pares origen-destino a ≥ {CFG['experimento']['distancia_minima_m']} m", flush=True)

    base = {"area": a["nombre"], "estructura": est, "entorno": entorno.describir(),
            "correcciones_sentido": correcciones, "pares": len(pares)}
    d = _partes(args.area, args.prueba)

    # Cada (modelo, réplica) se guarda apenas termina: si la corrida se interrumpe,
    # al relanzarla se saltean las partes ya hechas.
    for modelo in modelos:
        total = _replicas(modelo, args.prueba)
        rango = range(total)
        if args.replicas and modelo == "M1":
            rango = range(max(0, args.replicas[0]), min(total, args.replicas[1]))
        for replica in rango:
            destino = d / f"{modelo}_r{replica:02d}.csv"
            if destino.exists():
                print(f"   {modelo} réplica {replica + 1}/{total}: ya estaba hecha, se saltea", flush=True)
                continue
            t1 = time.time()
            filas: list[dict] = []
            regs, info = registros_de(a, modelo, replica)
            G, asig = gr.asignar_severidad(G, regs, a["epsg_metrico"])
            verif_costos = []
            for alfa in CFG["costo"]["alfas"]:
                G = gr.ponderar(G, alfa)
                verif_costos.append(exp.ejecutar(G, pares, args.area, modelo, replica, alfa, filas))
            discrep = sum(v["discrepancias"] for v in verif_costos)
            corrida = {"modelo": modelo, "replica": replica, "preparacion": info,
                       "asignacion": asig, "verificacion_costos": verif_costos,
                       "segundos": round(time.time() - t1, 1)}
            if replica == 0:
                G = gr.ponderar(G, CFG["costo"]["alfas"][-1])
                muestra = pares[:5]
                corrida["verificacion"] = {
                    "integridad": ver.integridad_grafo(G),
                    "admisibilidad": ver.admisibilidad(G, muestra[:2]),
                    "sentidos_respetados": ver.sentidos_respetados(G, muestra),
                    "trazas_coherentes": ver.trazas_coherentes(G, muestra),
                }
            # primero el JSON y al final el CSV: la parte cuenta como hecha solo si existe el CSV
            (d / f"{modelo}_r{replica:02d}.json").write_text(
                json.dumps(corrida, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            tmp = destino.with_suffix(".tmp")
            exp.volcar(filas, tmp)
            tmp.replace(destino)
            print(f"   {modelo} réplica {replica + 1}/{total}: {asig['registros_asignados']} registros, "
                  f"{asig['aristas_con_deterioro']} aristas con baches, d95 = {asig['d95_baches_por_m']}; "
                  f"discrepancias de costo: {discrep}  [{time.time() - t1:.1f} s]", flush=True)
            if discrep:
                print("   *** ATENCIÓN: la serie no supera la verificación de costos ***", flush=True)

    unir(args.area, a, modelos, args.prueba, base)
    print(f"   total {time.time() - t0:.1f} s", flush=True)


if __name__ == "__main__":
    main()
