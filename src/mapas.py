"""Mapas estáticos de cada ciudad.

Produce, a `resultados/mapas/` (sufijo _<modelo> en Jersey City):

  red_<ciudad>        la red vial con sus nodos y los baches superpuestos
  severidad_<ciudad>  las aristas coloreadas por su índice de severidad s(e)
  rutas_<ciudad>      rutas de un mismo par para varios valores de α, con los
                      tres algoritmos superpuestos
  sentidos_<ciudad>   auditoría del sentido de circulación que publica OSM

El tercero es el que hay que contrastar con la realidad: si algún sentido está
mal cartografiado, se corrige en `datos/crudos/sentidos_corregidos.csv`.

Uso:
    python src/mapas.py --area encarnacion
    python src/mapas.py --area jersey_city --modelo M2
"""
from __future__ import annotations

import argparse

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter
import numpy as np
from shapely.geometry import Point

from config import CFG, RAIZ, RES_MAPAS, area as cfg_area
import grafo as gr

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Liberation Serif", "Times New Roman", "DejaVu Serif"],
    "font.size": 9,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.08,
})
CM = 1 / 2.54
GRIS = "#b9bfc4"
ACC = "#2f5d7c"
WARM = "#9c4a21"
VERDE = "#4f8a5b"


def _miles(n: int) -> str:
    """Separador de miles con punto, como en la memoria."""
    return f"{n:,}".replace(",", ".")


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
             nota: str = "") -> None:
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
               label=f"intersección ({_miles(G.number_of_nodes())})"),
        Line2D([], [], marker="o", ls="", color=WARM, ms=4,
               label=f"bache individual ({_miles(sum(1 for g in grandes if not g))})"),
        Line2D([], [], marker="o", ls="", color=WARM, ms=8,
               label=f"agrupación ({_miles(sum(grandes))})"),
    ], loc="upper left", bbox_to_anchor=(-.02, -.01), frameon=False, fontsize=8)
    if nota:
        fig.text(.5, .012, nota, ha="center", fontsize=7.5, color="#8a4a20", style="italic")
    _guardar(fig, f"red_{ciudad}")


def mapa_severidad(G, aristas, ciudad: str, titulo: str) -> None:
    """Aristas coloreadas por el índice de severidad s(e) que penaliza el costo."""
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
        barra.set_label("índice de severidad  s(e)", fontsize=9)
        barra.outline.set_visible(False)
        barra.ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:.1f}".replace(".", ",")))

    pct = f"{100 * len(con) / len(aristas):.1f}".replace(".", ",")
    ax.set_title(f"Severidad por tramo — {titulo}\n"
                 f"{_miles(len(con))} de {_miles(len(aristas))} tramos con baches ({pct} %)",
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
                 f"{_miles(n_unico)} tramos de sentido único, {_miles(n_doble)} de doble",
                 fontsize=11, pad=8)
    ax.legend(handles=[
        Line2D([], [], color=ACC, lw=1.8, label="sentido único"),
        Line2D([], [], color=VERDE, lw=1.8, label="doble sentido"),
    ], loc="lower left", frameon=False, fontsize=8)
    fig.text(.5, .015, "Contrastar con la realidad. Las diferencias se corrigen "
             "en datos/crudos/sentidos_corregidos.csv",
             ha="center", fontsize=7.5, color="#6b7276", style="italic")
    _guardar(fig, f"sentidos_{ciudad}")


def mapa_rutas(G, aristas, ciudad: str, titulo: str) -> dict:
    """Rutas de un mismo par para varios α; los tres algoritmos se superponen.

    El par se elige del cuartil superior de distancia en línea recta entre los
    pares del protocolo, para que el recorrido sea largo. Como los tres
    algoritmos obtienen el mismo costo óptimo, se comprueba además si devuelven
    la misma secuencia de nodos y se informa.
    """
    import algoritmos as alg
    import experimento as exp

    pares = exp.generar_pares(G, CFG["experimento"]["pares_od"], CFG["semilla_maestra"])
    dist = sorted(((exp.distancia_recta(G, o, d), o, d) for o, d in pares))
    _, origen, destino = dist[int(CFG["visualizacion"]["cuantil_distancia_par"] * (len(dist) - 1))]

    from metricas import de_ruta

    sev = np.array([G.edges[i].get("severidad", 0.0) for i in aristas.index])
    fig, ax = _lienzo()
    aristas[sev == 0].plot(ax=ax, color=GRIS, linewidth=0.6, zorder=1)
    if (sev > 0).any():
        aristas[sev > 0].plot(ax=ax, column=sev[sev > 0], cmap="OrRd", vmin=0, vmax=1,
                              linewidth=1.3, alpha=.55, zorder=1)
    # de abajo hacia arriba, cada α más fino que el anterior: los tramos
    # compartidos quedan a la vista como líneas concéntricas
    trazos = [(0.0, ACC, 7.0), (1.0, VERDE, 4.2), (5.0, "#111111", 1.6)]
    leyenda, iguales = [], {}
    for alfa, color, ancho in trazos:
        gr.ponderar(G, alfa)
        rutas = {n: f(G, origen, destino).ruta for n, f in alg.ALGORITMOS.items()}
        iguales[alfa] = len({tuple(r) for r in rutas.values()}) == 1
        for nombre, ruta in rutas.items():
            ax.plot([G.nodes[n]["x"] for n in ruta], [G.nodes[n]["y"] for n in ruta], color=color,
                    lw=ancho, solid_capstyle="round", alpha=.95, zorder=3)
        m = de_ruta(G, rutas["dijkstra"])
        leyenda.append(Line2D([], [], color=color, lw=min(ancho, 4),
                              label=f"α = {alfa:g}: {_miles(round(m['longitud_m']))} m, {_miles(round(m['exposicion']))} baches"))
    for n, txt in ((origen, "O"), (destino, "D")):
        ax.plot(G.nodes[n]["x"], G.nodes[n]["y"], "o", color="black", ms=6, zorder=5)
        ax.annotate(txt, (G.nodes[n]["x"], G.nodes[n]["y"]), xytext=(5, 5),
                    textcoords="offset points", fontsize=9, weight="bold", zorder=6)
    ax.legend(handles=leyenda, loc="upper left", bbox_to_anchor=(-.02, -.01), frameon=False, fontsize=8)
    if all(iguales.values()):
        nota = "Para cada α, Dijkstra, A* y Bellman-Ford obtuvieron la misma ruta."
    else:
        nota = "Para algún α los algoritmos obtuvieron rutas distintas de igual costo: " + str(iguales)
    ax.set_title(f"Rutas calculadas sobre un mismo par — {titulo}\n{nota}", fontsize=10, pad=8)
    _guardar(fig, f"rutas_{ciudad}")
    return {"origen": origen, "destino": destino, "rutas_identicas_por_alfa": iguales}


def main() -> None:
    import ejecutar
    import osmnx as ox

    p = argparse.ArgumentParser(description="Mapas estáticos por ciudad")
    p.add_argument("--area", default="encarnacion", choices=list(CFG["areas"]))
    p.add_argument("--modelo", default=None, help="por omisión, todos los del área")
    args = p.parse_args()

    a = cfg_area(args.area)
    titulo_base = a["nombre"].split(",")[0].strip()
    base = titulo_base.lower().replace(" ", "_")
    G = gr.construir(a)
    gr.aplicar_correcciones_sentido(G)
    nodos, _ = ox.convert.graph_to_gdfs(G)

    for modelo in ([args.modelo] if args.modelo else a["modelos"]):
        ciudad = base if modelo == "observado" else f"{base}_{modelo.lower()}"
        titulo = titulo_base if modelo == "observado" else f"{titulo_base}, {modelo}"
        print(f"== {a['nombre']} · {modelo}")
        regs, info = ejecutar.registros_de(a, modelo, 0)
        G, _ = gr.asignar_severidad(G, regs, a["epsg_metrico"])
        _, aristas = ox.convert.graph_to_gdfs(G)
        puntos = gpd.GeoSeries([Point(r["lon"], r["lat"]) for r in regs],
                               crs="EPSG:4326").to_crs(epsg=a["epsg_metrico"])
        nota = {"M1": "Clase asignada por sorteo (modelo 1, réplica 1): no describe el estado real de cada bache.",
                "M2": "Agrupaciones formadas por registros a ≤ 10 m entre sí (modelo 2), reducidas a su centroide."
                }.get(modelo, "")
        mapa_red(G, aristas, nodos, puntos, [r["clase"] for r in regs], ciudad, titulo, nota)
        mapa_severidad(G, aristas, ciudad, titulo)
        info_rutas = mapa_rutas(G, aristas, ciudad, titulo)
        print(f"   rutas idénticas entre algoritmos por α: {info_rutas['rutas_identicas_por_alfa']}")
    mapa_sentidos(G, aristas, base, titulo_base)


if __name__ == "__main__":
    main()
