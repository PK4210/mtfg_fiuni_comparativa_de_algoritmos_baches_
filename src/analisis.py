"""Agregación de las mediciones y generación de las salidas del Capítulo 5.

Lee `resultados/tablas/mediciones_<area>.csv` y produce las tablas y figuras
comparativas. No mide nada: solo resume lo que `ejecutar.py` registró.

Uso:
    python src/analisis.py --area encarnacion
"""
from __future__ import annotations

import argparse
import collections
import csv
import statistics as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from config import RES_FIGURAS, RES_TABLAS

ETIQUETAS = {"dijkstra": "Dijkstra", "a_estrella": "A*",
             "bellman_ford": "Bellman-Ford"}
COLORES = {"dijkstra": "#2f5d7c", "a_estrella": "#9c4a21",
           "bellman_ford": "#4f8a5b"}

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 9,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.06,
})
CM = 1 / 2.54


def leer(area: str) -> list[dict]:
    ruta = RES_TABLAS / f"mediciones_{area}.csv"
    if not ruta.exists():
        raise SystemExit(f"Falta {ruta}. Ejecutá primero: python src/ejecutar.py "
                         f"--area {area}")
    with open(ruta, encoding="utf-8") as fh:
        filas = list(csv.DictReader(fh))
    for f in filas:
        for k in ("alfa", "tiempo_ms", "longitud_m", "tiempo_s", "exposicion",
                  "costo", "informatividad"):
            f[k] = float(f[k]) if f[k] not in ("", "None", None) else None
        for k in ("expandidos", "pasadas", "relajaciones", "aristas", "replica"):
            f[k] = int(f[k]) if f[k] not in ("", "None", None) else 0
    return filas


def _agrega(vals: list) -> tuple[float | None, float | None]:
    limpios = [v for v in vals if v is not None]
    if not limpios:
        return None, None
    return (st.mean(limpios),
            st.pstdev(limpios) if len(limpios) > 1 else 0.0)


def clave_condicion(f: dict) -> tuple:
    """Identifica una condición experimental hasta el par origen-destino.

    La réplica forma parte de la clave porque cada una sortea sus propios
    pares: dos réplicas distintas ponderan la red de modo distinto, de manera
    que un mismo par medido en réplicas diferentes no es la misma condición.
    Omitirla permitiría promediar mediciones tomadas sobre grafos distintos.
    """
    return (f["configuracion"], f["replica"], f["alfa"],
            f["origen"], f["destino"])


def pares_comunes(filas: list[dict], algoritmos: tuple = ()) -> set:
    """Pares origen-destino resueltos por todos los algoritmos considerados.

    Bellman-Ford se ejecuta sobre una muestra menor, porque su costo es
    O(n·m). Comparar medias calculadas sobre muestras distintas produciría
    diferencias que no son atribuibles a los algoritmos, de modo que las
    métricas se restringen a la intersección.

    `algoritmos` permite acotar la intersección a un subconjunto: la
    comparación entre Dijkstra y A* dispone de todos los pares del protocolo,
    mientras que la comparación con Bellman-Ford queda limitada a su muestra.
    """
    por_algo = collections.defaultdict(set)
    for f in filas:
        if algoritmos and f["algoritmo"] not in algoritmos:
            continue
        por_algo[f["algoritmo"]].add(clave_condicion(f))
    if not por_algo:
        return set()
    return set.intersection(*por_algo.values())


def tabla_por_algoritmo(filas: list[dict], area: str, algoritmos: tuple = (),
                        sufijo: str = "") -> list[dict]:
    """Una fila por combinación de configuración, alfa y algoritmo."""
    comunes = pares_comunes(filas, algoritmos)
    filas = [f for f in filas
             if clave_condicion(f) in comunes
             and (not algoritmos or f["algoritmo"] in algoritmos)]
    cuales = ", ".join(ETIQUETAS.get(a, a) for a in algoritmos) or "los tres algoritmos"
    print(f"   restringido a {len(comunes)} pares comunes a {cuales}")

    grupos = collections.defaultdict(list)
    for f in filas:
        grupos[(f["configuracion"], f["alfa"], f["algoritmo"])].append(f)

    salida = []
    for (config, alfa, algo), g in sorted(grupos.items(),
                                          key=lambda x: (x[0][0], x[0][1], x[0][2])):
        t_med, t_desv = _agrega([f["tiempo_ms"] for f in g])
        e_med, _ = _agrega([f["expandidos"] for f in g])
        l_med, _ = _agrega([f["longitud_m"] for f in g])
        s_med, _ = _agrega([f["tiempo_s"] for f in g])
        x_med, _ = _agrega([f["exposicion"] for f in g])
        i_med, _ = _agrega([f["informatividad"] for f in g])
        salida.append({
            "configuracion": config, "alfa": alfa,
            "algoritmo": ETIQUETAS.get(algo, algo), "n": len(g),
            "tiempo_ms_media": round(t_med, 4) if t_med else None,
            "tiempo_ms_desv": round(t_desv, 4) if t_desv is not None else None,
            "nodos_expandidos": round(e_med, 1) if e_med else None,
            "longitud_m": round(l_med, 1) if l_med else None,
            "tiempo_trayecto_s": round(s_med, 1) if s_med else None,
            "exposicion": round(x_med, 3) if x_med is not None else None,
            "informatividad": round(i_med, 4) if i_med else None,
        })

    ruta = RES_TABLAS / f"resumen_{area}{sufijo}.csv"
    with open(ruta, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(salida[0]))
        w.writeheader()
        w.writerows(salida)
    print(f"   tabla comparativa -> {ruta.name}")
    return salida


def figura_tiempos(resumen: list[dict], area: str) -> None:
    """Tiempo de cómputo por algoritmo frente al parámetro de penalización."""
    fig, ax = plt.subplots(figsize=(13 * CM, 7.5 * CM))
    for algo in ETIQUETAS.values():
        pts = [(r["alfa"], r["tiempo_ms_media"]) for r in resumen
               if r["algoritmo"] == algo and r["configuracion"] == resumen[0]["configuracion"]
               and r["tiempo_ms_media"] is not None]
        if not pts:
            continue
        pts.sort()
        clave = [k for k, v in ETIQUETAS.items() if v == algo][0]
        ax.plot([p[0] for p in pts], [p[1] for p in pts], marker="o", ms=4,
                lw=1.4, label=algo, color=COLORES[clave])
    ax.set_xlabel("parámetro de penalización α")
    ax.set_ylabel("tiempo de cómputo medio [ms]")
    ax.set_yscale("log")
    ax.grid(alpha=.25, lw=.6)
    ax.legend(frameon=False)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    fig.savefig(RES_FIGURAS / f"tiempos_{area}.png", dpi=300)
    fig.savefig(RES_FIGURAS / f"tiempos_{area}.pdf")
    plt.close(fig)
    print(f"   figura -> tiempos_{area}.png")


def figura_heuristica(resumen: list[dict], area: str) -> None:
    """Informatividad de la heurística y nodos expandidos frente a α.

    Es la figura que contrasta la hipótesis de la sección 2.5.
    """
    base = [r for r in resumen if r["configuracion"] == resumen[0]["configuracion"]]
    inf = sorted((r["alfa"], r["informatividad"]) for r in base
                 if r["algoritmo"] == "A*" and r["informatividad"] is not None)
    if not inf:
        return
    fig, ax = plt.subplots(figsize=(13 * CM, 7.5 * CM))
    ax.plot([p[0] for p in inf], [p[1] for p in inf], marker="o", ms=4, lw=1.4,
            color=COLORES["a_estrella"], label="informatividad de la heurística")
    ax.set_xlabel("parámetro de penalización α")
    ax.set_ylabel("razón h(origen) / costo real")
    ax.set_ylim(0, 1.05)

    ax2 = ax.twinx()
    for algo, clave in (("A*", "a_estrella"), ("Dijkstra", "dijkstra")):
        pts = sorted((r["alfa"], r["nodos_expandidos"]) for r in base
                     if r["algoritmo"] == algo and r["nodos_expandidos"])
        if pts:
            ax2.plot([p[0] for p in pts], [p[1] for p in pts], ls="--", lw=1.2,
                     marker="s", ms=3, color=COLORES[clave],
                     label=f"nodos expandidos · {algo}")
    ax2.set_ylabel("nodos expandidos (media)")

    lineas = ax.get_lines() + ax2.get_lines()
    ax.legend(lineas, [l.get_label() for l in lineas], frameon=False, fontsize=8)
    ax.grid(alpha=.25, lw=.6)
    fig.savefig(RES_FIGURAS / f"heuristica_{area}.png", dpi=300)
    fig.savefig(RES_FIGURAS / f"heuristica_{area}.pdf")
    plt.close(fig)
    print(f"   figura -> heuristica_{area}.png")


def figura_compromiso(resumen: list[dict], area: str) -> None:
    """Longitud frente a exposición: el precio de esquivar el deterioro."""
    base = [r for r in resumen
            if r["algoritmo"] == "Dijkstra"
            and r["configuracion"] == resumen[0]["configuracion"]
            and r["longitud_m"] and r["exposicion"] is not None]
    if len(base) < 2:
        return
    base.sort(key=lambda r: r["alfa"])
    fig, ax = plt.subplots(figsize=(13 * CM, 7.5 * CM))
    ax.plot([r["longitud_m"] for r in base], [r["exposicion"] for r in base],
            marker="o", ms=5, lw=1.4, color=COLORES["dijkstra"])
    for r in base:
        ax.annotate(f"α = {r['alfa']:g}",
                    (r["longitud_m"], r["exposicion"]),
                    textcoords="offset points", xytext=(6, 5), fontsize=8)
    ax.set_xlabel("longitud media de la ruta [m]")
    ax.set_ylabel("exposición acumulada media")
    ax.grid(alpha=.25, lw=.6)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    fig.savefig(RES_FIGURAS / f"compromiso_{area}.png", dpi=300)
    fig.savefig(RES_FIGURAS / f"compromiso_{area}.pdf")
    plt.close(fig)
    print(f"   figura -> compromiso_{area}.png")


def tabla_dispersion(filas: list[dict], area: str,
                     algoritmos: tuple = ("dijkstra", "a_estrella")) -> list[dict]:
    """Dispersión de las métricas entre réplicas de asignación de clases.

    Solo tiene sentido en la red de contraste, cuyas clases se sortean: cada
    réplica es un sorteo distinto con la misma distribución. La desviación
    típica entre réplicas mide cuánto de lo observado depende del sorteo y
    cuánto de la estructura de la red. En la red principal las clases son
    observadas y hay una sola réplica, de modo que no hay nada que dispersar.
    """
    if len({f["replica"] for f in filas}) < 2:
        return []

    # la dispersión se calcula sobre la muestra completa del protocolo y no
    # sobre los treinta pares de Bellman-Ford: las métricas de ruta coinciden
    # en los tres algoritmos, de modo que restringirlas a la muestra menor solo
    # ensancharía el intervalo sin cambiar el valor central
    comunes = pares_comunes(filas, algoritmos)
    filas = [f for f in filas if clave_condicion(f) in comunes
             and f["algoritmo"] in algoritmos]

    # primero se promedia dentro de cada réplica; después se dispersa entre ellas
    por_replica = collections.defaultdict(lambda: collections.defaultdict(list))
    for f in filas:
        clave = (f["configuracion"], f["alfa"], f["algoritmo"])
        por_replica[clave][f["replica"]].append(f)

    salida = []
    for (config, alfa, algo), reps in sorted(por_replica.items()):
        medias = {m: [] for m in ("exposicion", "longitud_m", "expandidos",
                                  "tiempo_ms")}
        for _, g in sorted(reps.items()):
            for m in medias:
                v = [f[m] for f in g if f[m] is not None]
                if v:
                    medias[m].append(st.mean(v))
        fila = {"configuracion": config, "alfa": alfa,
                "algoritmo": ETIQUETAS.get(algo, algo), "replicas": len(reps)}
        for m, etiqueta in (("exposicion", "exposicion"),
                            ("longitud_m", "longitud_m"),
                            ("expandidos", "nodos_expandidos"),
                            ("tiempo_ms", "tiempo_ms")):
            v = medias[m]
            fila[f"{etiqueta}_media"] = round(st.mean(v), 4) if v else None
            fila[f"{etiqueta}_desv"] = (round(st.stdev(v), 4)
                                        if len(v) > 1 else 0.0)
            fila[f"{etiqueta}_cv_pct"] = (
                round(100 * st.stdev(v) / st.mean(v), 2)
                if len(v) > 1 and st.mean(v) else None)
        salida.append(fila)

    ruta = RES_TABLAS / f"dispersion_{area}.csv"
    with open(ruta, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(salida[0]))
        w.writeheader()
        w.writerows(salida)
    print(f"   dispersión entre réplicas -> {ruta.name}")
    return salida


def figura_dispersion(disp: list[dict], area: str) -> None:
    """Exposición media por configuración, con la dispersión entre réplicas."""
    base = [r for r in disp if r["algoritmo"] == "Dijkstra"]
    if not base:
        return
    fig, ax = plt.subplots(figsize=(13 * CM, 7.5 * CM))
    estilos = {"C2": ("-", "o"), "C3": ("--", "s")}
    for config in sorted({r["configuracion"] for r in base}):
        pts = sorted((r["alfa"], r["exposicion_media"], r["exposicion_desv"])
                     for r in base if r["configuracion"] == config)
        ls, marca = estilos.get(config, ("-", "o"))
        ax.errorbar([p[0] for p in pts], [p[1] for p in pts],
                    yerr=[p[2] for p in pts], ls=ls, marker=marca, ms=4,
                    lw=1.4, capsize=3, color=COLORES["dijkstra"]
                    if config == "C2" else COLORES["bellman_ford"],
                    label=f"configuración {config}")
    ax.set_xlabel("parámetro de penalización α")
    ax.set_ylabel("exposición acumulada media")
    ax.grid(alpha=.25, lw=.6)
    ax.legend(frameon=False)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    fig.savefig(RES_FIGURAS / f"dispersion_{area}.png", dpi=300)
    fig.savefig(RES_FIGURAS / f"dispersion_{area}.pdf")
    plt.close(fig)
    print(f"   figura -> dispersion_{area}.png")


def main() -> None:
    p = argparse.ArgumentParser(description="Análisis de las mediciones")
    p.add_argument("--area", default="encarnacion")
    args = p.parse_args()

    filas = leer(args.area)
    print(f"== {args.area}: {len(filas)} mediciones")
    resumen = tabla_por_algoritmo(filas, args.area)
    # la comparacion entre Dijkstra y A* dispone de todos los pares del
    # protocolo; solo Bellman-Ford obliga a recortar la muestra
    tabla_por_algoritmo(filas, args.area, ("dijkstra", "a_estrella"), "_par")
    figura_tiempos(resumen, args.area)
    figura_heuristica(resumen, args.area)
    figura_compromiso(resumen, args.area)
    disp = tabla_dispersion(filas, args.area)
    if disp:
        figura_dispersion(disp, args.area)


if __name__ == "__main__":
    main()
