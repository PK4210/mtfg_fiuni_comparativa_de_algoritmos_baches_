"""Videos de la expansión de cada algoritmo, sobre las calles, paso a paso.

Produce un MP4 por ciudad y valor de α, con los tres algoritmos en panel
triple sobre el mismo par origen-destino, y guarda el cuadro final como figura
estática. La expansión no se dibuja como puntos en las intersecciones sino
sobre la geometría real de cada calle: se ve la búsqueda avanzar por la red.

Cuatro capas por panel, sobre el mapa en gris:

  1. árbol de exploración   la unión de las aristas (pred[v], v) de los nodos
                            ya cerrados. Las recién exploradas van brillantes
                            y las viejas se atenúan: se ve el frente de onda
  2. camino al nodo actual  desde el origen hasta el nodo que se acaba de
                            cerrar, en trazo oscuro
  3. camino al destino      el mejor camino tentativo, cuando ya existe
  4. frontera y ruta final

Sobre la sincronización de los paneles. Dijkstra y A* comparten unidad —nodos
expandidos—, de modo que avanzan sobre la misma línea de tiempo: A* termina
antes y su panel queda congelado mientras Dijkstra sigue explorando. Esa
asimetría es justamente el resultado que interesa mostrar. Bellman-Ford no
expande nodos sino que relaja todas las aristas en cada pasada, así que su
unidad no es comparable: avanza por pasadas, repartidas a lo largo del video,
y el rótulo lo aclara. Su árbol además se recablea entre pasadas, así que se
dibuja el vigente en cada una y no la unión histórica.

Uso:
    python src/animaciones.py --area encarnacion
    python src/animaciones.py --area encarnacion --alfa 1.0
"""
from __future__ import annotations

import argparse
import random
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.animation as animation
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
import networkx as nx
import numpy as np
import osmnx as ox

from config import CFG, RES_MAPAS, area as cfg_area
import algoritmos as alg
import grafo as gr
import trazas as tz

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 9,
})
CM = 1 / 2.54
GRIS = "#c8ced3"
ACC = "#2f5d7c"
WARM = "#9c4a21"
VERDE = "#4f8a5b"
OSCURO = "#111111"
TENTATIVO = "#6b4c9a"
COLOR = {"dijkstra": ACC, "a_estrella": WARM, "bellman_ford": VERDE}
TITULO = {"dijkstra": "Dijkstra", "a_estrella": "A*",
          "bellman_ford": "Bellman-Ford"}
PISO = 0.28          # opacidad de las calles ya exploradas hace rato


def elegir_par(G, semilla: int) -> tuple:
    """Par origen-destino largo y determinista, del cuartil superior."""
    nodos = sorted(max(nx.strongly_connected_components(G), key=len))
    rng = random.Random(semilla)
    candidatos = []
    for _ in range(400):
        o, d = rng.sample(nodos, 2)
        a, b = G.nodes[o], G.nodes[d]
        candidatos.append(
            (alg._haversine(a["lat"], a["lon"], b["lat"], b["lon"]), o, d))
    candidatos.sort()
    corte = int(len(candidatos) * CFG["visualizacion"]["cuantil_distancia_par"])
    return candidatos[corte][1], candidatos[corte][2]


def _coords(G, nodos) -> np.ndarray:
    if len(nodos) == 0:
        return np.empty((0, 2))
    return np.array([[G.nodes[n]["x"], G.nodes[n]["y"]] for n in nodos])


def cache_geometria(G) -> dict:
    """(u, v) -> polilínea de la calle, orientada de u hacia v.

    Con aristas paralelas se toma la de menor peso, que es la que
    `algoritmos._aristas_salientes` elige y por lo tanto la que el algoritmo
    realmente recorre. OSMnx conserva la geometría de los tramos que simplificó;
    los que son un segmento recto no la traen y se arma con las coordenadas de
    los extremos.
    """
    cache: dict = {}
    for u, v in {(a, b) for a, b, _ in G.edges(keys=True)}:
        k = min(G[u][v], key=lambda kk: G[u][v][kk]["peso"])
        geo = G[u][v][k].get("geometry")
        if geo is not None:
            xy = np.asarray(geo.coords, dtype=float)
        else:
            xy = np.array([[G.nodes[u]["x"], G.nodes[u]["y"]],
                           [G.nodes[v]["x"], G.nodes[v]["y"]]], dtype=float)
        # el sentido de la polilínea que publica OSM es arbitrario: se orienta
        # de u hacia v para que los caminos empalmen sin saltos
        ux, uy = G.nodes[u]["x"], G.nodes[u]["y"]
        if ((xy[-1, 0] - ux) ** 2 + (xy[-1, 1] - uy) ** 2
                < (xy[0, 0] - ux) ** 2 + (xy[0, 1] - uy) ** 2):
            xy = xy[::-1]
        cache[(u, v)] = xy
    return cache


def polilinea(camino, cache) -> np.ndarray:
    """Encadena las geometrías de un camino en una sola polilínea continua."""
    if not camino or len(camino) < 2:
        return np.empty((0, 2))
    tramos = [cache[(u, v)] for u, v in zip(camino, camino[1:])]
    # el primer punto de cada tramo repite el último del anterior
    return np.vstack([tramos[0]] + [t[1:] for t in tramos[1:]])


def _trazo(linea, camino, cache) -> None:
    """Vuelca un camino sobre una línea, o la vacía si el camino no existe."""
    xy = polilinea(camino, cache)
    if len(xy):
        linea.set_data(xy[:, 0], xy[:, 1])
    else:
        linea.set_data([], [])


def _segmentos_incrementales(traza, cache) -> tuple:
    """Para Dijkstra y A*: las aristas del árbol y el paso en que entró cada una."""
    segs, pasos = [], []
    for i, par in enumerate(traza.arbol):
        if par is None:                  # el origen no tiene arista de entrada
            continue
        segs.append(cache[par])
        pasos.append(i)
    return segs, np.array(pasos, dtype=float)


def _segmentos_por_pasada(traza, cache) -> list:
    """Para Bellman-Ford: el árbol vigente al final de cada pasada.

    A diferencia de Dijkstra y A*, aquí el árbol se recablea: una arista
    incorporada en una pasada puede ser reemplazada en la siguiente. Se guarda
    la foto de cada pasada, no la unión histórica.
    """
    padre: dict = {}                     # hijo -> (padre, pasada en que entró)
    fotos = []
    for p, pares in enumerate(traza.arbol):
        for pa, hi in pares:
            padre[hi] = (pa, p)
        segs = [cache[(pa, hi)] for hi, (pa, _) in padre.items()]
        edades = np.array([p - p0 for _, (_, p0) in padre.items()], dtype=float)
        fotos.append((segs, edades))
    return fotos


def _pintar(coleccion, segs, edades, rgb, ventana, grosor) -> None:
    """Dibuja el árbol con el frente brillante y la cola atenuada."""
    if not segs:
        coleccion.set_segments([])
        return
    coleccion.set_segments(segs)
    intensidad = PISO + (1 - PISO) * np.exp(-edades / ventana)
    rgba = np.empty((len(segs), 4))
    rgba[:, 0], rgba[:, 1], rgba[:, 2] = rgb
    rgba[:, 3] = intensidad
    coleccion.set_color(rgba)
    coleccion.set_linewidth(grosor * (0.65 + 0.65 * intensidad))


def _miles(x: float) -> str:
    """Separador de miles con punto, como en el resto de la memoria."""
    return f"{x:,.0f}".replace(",", ".")


def _avances(traza, cuadros: int) -> list:
    """Cuántos pasos del algoritmo lleva mostrados cada cuadro."""
    total = len(traza.orden)
    if traza.unidad.startswith("pasadas"):
        return [max(1, int(round((i + 1) / cuadros * total)))
                for i in range(cuadros)]
    paso = max(1, int(np.ceil(total / cuadros)))
    return [min((i + 1) * paso, total) for i in range(cuadros)]


def animar(G, aristas, origen, destino, alfa: float, ciudad: str,
           titulo: str) -> str:
    resultados = {n: f(G, origen, destino) for n, f in tz.TRAZAS.items()}
    cache = cache_geometria(G)

    vis = CFG["visualizacion"]
    fps = vis["fps"]
    pasos_max = max(len(r.orden) for r in resultados.values()
                    if not r.unidad.startswith("pasadas"))
    cuadros = min(vis["cuadros_objetivo"], max(pasos_max, 60))
    cola = int(fps * vis["segundos_ruta_final"])

    avances = {n: _avances(r, cuadros) for n, r in resultados.items()}

    n_nodos = G.number_of_nodes()
    denso = n_nodos >= 800
    grosor_arbol = 1.1 if denso else 2.0
    grosor_camino = 1.6 if denso else 2.6
    tam_frontera = 3.0 if denso else 11.0

    fig, ejes = plt.subplots(1, 3, figsize=(30 * CM, 13.5 * CM))
    fig.subplots_adjust(bottom=.15, top=.88)
    fig.suptitle(
        f"Expansión de la búsqueda — {titulo}   ·   α = {alfa:g}"
        f"   ·   {n_nodos} nodos, {G.number_of_edges()} aristas "
        f"dirigidas (respeta los sentidos de circulación)",
        fontsize=10.5, y=.97)

    dibujos = {}
    for ax, nombre in zip(ejes, tz.TRAZAS):
        r = resultados[nombre]
        rgb = mcolors.to_rgb(COLOR[nombre])
        aristas.plot(ax=ax, color=GRIS if not denso else "#dde2e6",
                     linewidth=.5 if not denso else .35, zorder=1)
        ax.set_aspect("equal")
        ax.axis("off")

        arbol = LineCollection([], zorder=3, capstyle="round")
        ax.add_collection(arbol)
        frontera = ax.scatter([], [], s=tam_frontera * 2.2, facecolor="none",
                              edgecolor=COLOR[nombre], linewidth=.55, zorder=4)
        tentativo, = ax.plot([], [], color=TENTATIVO, lw=grosor_camino * .85,
                             zorder=5, solid_capstyle="round", alpha=.9)
        actual, = ax.plot([], [], color=OSCURO, lw=grosor_camino, zorder=6,
                          solid_capstyle="round")
        final, = ax.plot([], [], color=OSCURO, lw=grosor_camino * 1.15,
                         zorder=7, solid_capstyle="round")

        for nodo, marca, tam_marca in ((origen, "o", 62), (destino, "s", 62)):
            ax.scatter(G.nodes[nodo]["x"], G.nodes[nodo]["y"], s=tam_marca,
                       marker=marca, facecolor="white", edgecolor=OSCURO,
                       linewidth=1.3, zorder=8)

        contador = ax.text(.5, -.04, "", transform=ax.transAxes, ha="center",
                           va="top", fontsize=9, color=COLOR[nombre])
        ax.set_title(TITULO[nombre], fontsize=11, color=COLOR[nombre], pad=6)

        if r.unidad.startswith("pasadas"):
            fotos, segs, pasos = _segmentos_por_pasada(r, cache), None, None
        else:
            fotos = None
            segs, pasos = _segmentos_incrementales(r, cache)
        # la atenuacion se mide en la unidad de cada algoritmo, no en
        # cuadros: asi el frente ocupa la misma fraccion del video en los
        # tres paneles, aunque Bellman-Ford cuente pasadas y no nodos
        ventana = max(1.5, 0.15 * max(len(r.orden), 1))

        dibujos[nombre] = dict(
            r=r, rgb=rgb, ventana=ventana, arbol=arbol, frontera=frontera,
            tentativo=tentativo, actual=actual, final=final, contador=contador,
            fotos=fotos, segs=segs, pasos=pasos)

    fig.legend(handles=[
        Line2D([], [], color="#7d878e", lw=2.2, label="árbol de exploración"),
        Line2D([], [], color=OSCURO, lw=2.2, label="camino al nodo que se expande"),
        Line2D([], [], color=TENTATIVO, lw=2.2, label="mejor camino tentativo al destino"),
        Line2D([], [], marker="o", ls="", mfc="none", mec="#7d878e",
               label="frontera"),
        Line2D([], [], marker="o", ls="", mfc="white", mec=OSCURO, label="origen"),
        Line2D([], [], marker="s", ls="", mfc="white", mec=OSCURO, label="destino"),
    ], loc="lower center", ncol=6, frameon=False, fontsize=8.5,
        bbox_to_anchor=(.5, .01))

    def cuadro(i):
        artistas = []
        for nombre, d in dibujos.items():
            r, idx = d["r"], min(i, cuadros - 1)
            avance = avances[nombre][idx]
            terminado = i >= cuadros

            if d["fotos"] is not None:                       # Bellman-Ford
                segs, edades = d["fotos"][avance - 1]
                _pintar(d["arbol"], segs, edades, d["rgb"], d["ventana"],
                        grosor_arbol)
                d["actual"].set_data([], [])
            else:                                            # Dijkstra y A*
                k = int(np.searchsorted(d["pasos"], avance, side="left"))
                _pintar(d["arbol"], d["segs"][:k],
                        (avance - 1) - d["pasos"][:k], d["rgb"], d["ventana"],
                        grosor_arbol)
                _trazo(d["actual"], r.camino_expandido[avance - 1], cache)

                if not terminado and r.frontera:
                    j = min(avance - 1, len(r.frontera) - 1)
                    d["frontera"].set_offsets(
                        _coords(G, sorted(r.frontera[j])))
                else:
                    d["frontera"].set_offsets(np.empty((0, 2)))

            _trazo(d["tentativo"], r.camino_destino[avance - 1], cache)

            if terminado and r.ruta:
                _trazo(d["final"], r.ruta, cache)
                d["tentativo"].set_data([], [])
                d["actual"].set_data([], [])

            d["contador"].set_text(
                f"{avance} de {len(r.orden)} {r.unidad}"
                + (f"   ·   costo {_miles(r.costo)}"
                   if terminado and r.costo else ""))
            artistas += [d["arbol"], d["frontera"], d["tentativo"],
                         d["actual"], d["final"], d["contador"]]
        return artistas

    sufijo = f"{ciudad}_alfa{str(alfa).replace('.', 'p')}"
    salida = RES_MAPAS / f"busqueda_{sufijo}.mp4"
    anim = animation.FuncAnimation(fig, cuadro, frames=cuadros + cola,
                                   interval=1000 / fps, blit=False)
    anim.save(str(salida), writer=animation.FFMpegWriter(
        fps=fps, bitrate=2400, codec="libx264"), dpi=110)

    # el último cuadro, con el árbol completo y la ruta, sirve de figura
    cuadro(cuadros + cola - 1)
    fig.savefig(RES_MAPAS / f"expansion_{sufijo}.png",
                dpi=CFG["visualizacion"]["dpi_mapas"])
    plt.close(fig)

    dur = (cuadros + cola) / fps
    print(f"   -> busqueda_{sufijo}.mp4  ({cuadros + cola} cuadros, {dur:.0f} s)"
          f"  +  expansion_{sufijo}.png")
    return str(salida)


def main() -> None:
    import ejecutar

    p = argparse.ArgumentParser(description="Videos de la búsqueda")
    p.add_argument("--area", default="encarnacion", choices=list(CFG["areas"]))
    p.add_argument("--config", default="C2", choices=list(CFG["configuraciones"]))
    p.add_argument("--alfa", type=float, default=None,
                   help="un solo valor; por omisión, todos los de config.yaml")
    args = p.parse_args()

    a = cfg_area(args.area)
    ciudad = a["nombre"].split(",")[0].strip().lower().replace(" ", "_")
    titulo = a["nombre"].split(",")[0].strip()
    print(f"== {a['nombre']}")

    G = gr.construir(a)
    gr.aplicar_correcciones_sentido(G)
    regs, _ = ejecutar.registros_de(a, args.area, args.config,
                                    CFG["semilla_maestra"])
    G, _ = gr.asignar_severidad(G, regs, a["epsg_metrico"])
    _, aristas = ox.convert.graph_to_gdfs(G)

    G = gr.ponderar(G, 0.0)
    origen, destino = elegir_par(G, CFG["semilla_maestra"])
    d = alg._haversine(G.nodes[origen]["lat"], G.nodes[origen]["lon"],
                       G.nodes[destino]["lat"], G.nodes[destino]["lon"])
    print(f"   par origen-destino: {origen} -> {destino}  ({d:.0f} m en línea recta)")

    alfas = [args.alfa] if args.alfa is not None else CFG["costo"]["alfas"]
    for alfa in alfas:
        t0 = time.time()
        G = gr.ponderar(G, alfa)
        animar(G, aristas, origen, destino, alfa, ciudad, titulo)
        print(f"      ({time.time() - t0:.0f} s)")


if __name__ == "__main__":
    main()
