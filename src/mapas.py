"""Mapas estáticos de cada ciudad.

Produce tres, a `resultados/mapas/`:

  red_<ciudad>        la red vial con sus nodos y los baches superpuestos
  severidad_<ciudad>  las aristas coloreadas por su índice de deterioro
  sentidos_<ciudad>   auditoría del sentido de circulación que publica OSM

El tercero es el que hay que contrastar con la realidad: si algún sentido está
mal cartografiado, se corrige en `datos/crudos/sentidos_corregidos.csv`.

Uso:
    python src/mapas.py --area encarnacion
"""
from __future__ import annotations

import argparse

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
from shapely.geometry import Point

from config import CFG, RAIZ, RES_MAPAS, area as cfg_area
import grafo as gr

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 9,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.08,
})
CM = 1 / 2.54
GRIS = "#b9bfc4"
ACC = "#2f5d7c"
WARM = "#9c4a21"
VERDE = "#4f8a5b"


def _guardar(fig, nombre: str) -> None:
    dpi = CFG["visualizacion"]["dpi_mapas"]
    for ext in ("png", "pdf"):
        fig.savefig(RES_MAPAS / f"{nombre}.{ext}", dpi=dpi)
    plt.close(fig)
    print(f"   -> {nombre}.png")


def _lienzo(alto=15.5):
    fig, ax = plt.subplots(figsize=(15.5 * CM, alto * CM))
    ax.set_aspect("equal")
    ax.axis("off")
    return fig, ax


def _dibujar_red(ax, aristas, color=GRIS, lw=0.6, alpha=1.0):
    aristas.plot(ax=ax, color=color, linewidth=lw, alpha=alpha, zorder=1)


def mapa_red(G, aristas, nodos, puntos, clases, ciudad: str, titulo: str,
             sinteticas: bool = False) -> None:
    """Red vial, nodos e incidencias de deterioro."""
    # en redes densas los marcadores taparían la trama: se escalan
    n_reg = max(len(clases), 1)
    esc = min(1.0, (359 / n_reg) ** 0.5)
    esc_nodo = min(1.0, (202 / max(G.number_of_nodes(), 1)) ** 0.5)

    fig, ax = _lienzo()
    _dibujar_red(ax, aristas)
    nodos.plot(ax=ax, color="#7d878e", markersize=max(.6, 2.5 * esc_nodo),
               zorder=2)

    grandes = [c != "individual" for c in clases]
    peq = puntos[[not g for g in grandes]]
    gra = puntos[grandes]
    if len(peq):
        peq.plot(ax=ax, color=WARM, markersize=max(1.6, 9 * esc), alpha=.6,
                 edgecolor="white", linewidth=.15 * esc, zorder=3)
    if len(gra):
        gra.plot(ax=ax, color=WARM, markersize=max(8, 52 * esc), alpha=.75,
                 edgecolor="white", linewidth=.4 * esc, zorder=4)

    ax.set_title(f"Red vial y baches relevados — {titulo}", fontsize=11, pad=8)
    ax.legend(handles=[
        Line2D([], [], color=GRIS, lw=1.4, label="tramo vial"),
        Line2D([], [], marker="o", ls="", color="#7d878e", ms=3,
               label=f"intersección ({G.number_of_nodes()})"),
        Line2D([], [], marker="o", ls="", color=WARM, ms=4,
               label=f"bache individual ({sum(1 for g in grandes if not g)})"),
        Line2D([], [], marker="o", ls="", color=WARM, ms=8,
               label=f"agrupación ({sum(grandes)})"),
    ], loc="upper left", bbox_to_anchor=(-.02, -.01), frameon=False, fontsize=8)
    if sinteticas:
        fig.text(.5, .012, "La fuente no publica clase por registro: la "
                 "distribución individual/agrupación se transfirió desde el "
                 "relevamiento de Encarnación.\n"
                 "Es un atributo sintético y no describe el estado real de "
                 "cada bache.",
                 ha="center", fontsize=7.5, color="#8a4a20", style="italic")
    _guardar(fig, f"red_{ciudad}")


def mapa_severidad(G, aristas, ciudad: str, titulo: str) -> None:
    """Aristas coloreadas por el índice de deterioro que penaliza el costo."""
    sev = np.array([G.edges[i].get("severidad", 0.0) for i in aristas.index])
    fig, ax = _lienzo()
    aristas[sev == 0].plot(ax=ax, color=GRIS, linewidth=0.6, zorder=1)

    con = aristas[sev > 0]
    if len(con):
        con.plot(ax=ax, column=sev[sev > 0], cmap="OrRd", linewidth=2.0,
                 zorder=2, vmin=0, vmax=1)
        sm = plt.cm.ScalarMappable(cmap="OrRd",
                                   norm=plt.Normalize(vmin=0, vmax=1))
        barra = fig.colorbar(sm, ax=ax, fraction=.03, pad=.02)
        barra.set_label("índice de deterioro  s(e)", fontsize=9)
        barra.outline.set_visible(False)

    pct = round(100 * len(con) / len(aristas), 1)
    ax.set_title(f"Deterioro por tramo — {titulo}\n"
                 f"{len(con)} de {len(aristas)} tramos con registros ({pct} %)",
                 fontsize=11, pad=8)
    _guardar(fig, f"severidad_{ciudad}")


def mapa_sentidos(G, aristas, ciudad: str, titulo: str) -> None:
    """Auditoría: qué tramos declara OSM de sentido único y cuáles de doble."""
    pares = {(u, v) for u, v, _ in G.edges(keys=True)}
    doble = np.array([(v, u) in pares for u, v, _ in aristas.index])

    fig, ax = _lienzo()
    aristas[doble].plot(ax=ax, color=VERDE, linewidth=1.6, zorder=2)
    aristas[~doble].plot(ax=ax, color=ACC, linewidth=1.2, zorder=2)

    # flecha de dirección sobre cada tramo de sentido único
    for geom in aristas[~doble].geometry:
        try:
            a, b = geom.interpolate(.45, normalized=True), geom.interpolate(.55, normalized=True)
        except Exception:
            continue
        ax.annotate("", xy=(b.x, b.y), xytext=(a.x, a.y),
                    arrowprops=dict(arrowstyle="-|>", color=ACC, lw=.8,
                                    mutation_scale=7), zorder=3)

    # nombres de calle, uno por calle, sobre el tramo más largo
    vistos: dict = {}
    for idx, geom in zip(aristas.index, aristas.geometry):
        nombre = gr._nombre_calle(G.edges[idx])
        if not nombre:
            continue
        largo = G.edges[idx]["length"]
        if nombre not in vistos or largo > vistos[nombre][0]:
            vistos[nombre] = (largo, geom)
    for nombre, (_, geom) in sorted(vistos.items(),
                                    key=lambda x: -x[1][0])[:45]:
        p = geom.interpolate(.5, normalized=True)
        ax.text(p.x, p.y, nombre[:26], fontsize=4.6, color="#33393d",
                ha="center", va="center", zorder=5,
                bbox=dict(boxstyle="round,pad=.12", fc="white", ec="none",
                          alpha=.72))

    n_doble, n_unico = int(doble.sum()), int((~doble).sum())
    ax.set_title(f"Sentido de circulación según OpenStreetMap — {titulo}\n"
                 f"{n_unico} tramos de sentido único, {n_doble} de doble",
                 fontsize=11, pad=8)
    ax.legend(handles=[
        Line2D([], [], color=ACC, lw=1.8, label="sentido único"),
        Line2D([], [], color=VERDE, lw=1.8, label="doble sentido"),
    ], loc="lower left", frameon=False, fontsize=8)
    fig.text(.5, .015, "Contrastar con la realidad. Las diferencias se corrigen "
             "en datos/crudos/sentidos_corregidos.csv",
             ha="center", fontsize=7.5, color="#6b7276", style="italic")
    _guardar(fig, f"sentidos_{ciudad}")


def main() -> None:
    import ejecutar

    p = argparse.ArgumentParser(description="Mapas estáticos por ciudad")
    p.add_argument("--area", default="encarnacion", choices=list(CFG["areas"]))
    p.add_argument("--config", default="C2", choices=list(CFG["configuraciones"]))
    args = p.parse_args()

    a = cfg_area(args.area)
    ciudad = a["nombre"].split(",")[0].strip().lower().replace(" ", "_")
    titulo = a["nombre"].split(",")[0].strip()
    print(f"== {a['nombre']}")

    G = gr.construir(a)
    gr.aplicar_correcciones_sentido(G)
    regs, info = ejecutar.registros_de(a, args.area, args.config,
                                       CFG["semilla_maestra"])
    G, asig = gr.asignar_severidad(G, regs, a["epsg_metrico"])

    import osmnx as ox
    nodos, aristas = ox.convert.graph_to_gdfs(G)
    puntos = gpd.GeoSeries([Point(r["lon"], r["lat"]) for r in regs],
                           crs="EPSG:4326").to_crs(epsg=a["epsg_metrico"])
    clases = [r["clase"] for r in regs]

    mapa_red(G, aristas, nodos, puntos, clases, ciudad, titulo,
             sinteticas=info.get("clases_transferidas", False))
    mapa_severidad(G, aristas, ciudad, titulo)
    mapa_sentidos(G, aristas, ciudad, titulo)


if __name__ == "__main__":
    main()
