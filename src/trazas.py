"""Variantes de los algoritmos que registran el orden de expansión.

Van en un módulo aparte a propósito. `algoritmos.py` no se toca: la
instrumentación adicional que hace falta para animar añade trabajo dentro del
bucle principal, y contaminaría las mediciones de tiempo del Capítulo 5.

Estas versiones se usan solo para producir los videos. Además del orden de
expansión registran, paso a paso:

  arbol            la arista (padre, hijo) que entra al árbol de exploración
  camino_expandido el camino origen -> nodo que se acaba de cerrar
  camino_destino   el mejor camino tentativo hasta el destino, si ya existe

Con eso la animación puede dibujar la expansión sobre las calles y no como
puntos sueltos en las intersecciones.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

from algoritmos import _aristas_salientes, _reconstruir, heuristica


@dataclass
class Traza:
    """Historia completa de una búsqueda, cuadro por cuadro."""
    ruta: list | None
    costo: float | None
    orden: list = field(default_factory=list)     # nodos cerrados, en orden
    frontera: list = field(default_factory=list)  # frontera en cada paso
    arbol: list = field(default_factory=list)     # arista que entra por paso
    camino_expandido: list = field(default_factory=list)
    camino_destino: list = field(default_factory=list)
    unidad: str = "nodos expandidos"
    pasos: int = 0


def _camino(pred: dict, origen, destino, tope: int) -> list | None:
    """Camino origen -> destino según el `pred` vigente, o None si no hay.

    Los pesos son estrictamente positivos, de modo que `pred` es en todo
    momento un bosque enraizado en el origen y el recorrido termina siempre.
    El tope está por si alguna vez dejara de cumplirse: vale más un camino
    incompleto que un cuelgue durante el renderizado.
    """
    if destino == origen:
        return [origen]
    if destino not in pred:
        return None
    camino, actual = [destino], destino
    for _ in range(tope):
        actual = pred.get(actual)
        if actual is None:
            return None
        camino.append(actual)
        if actual == origen:
            return camino[::-1]
    return None


def dijkstra(G, origen, destino) -> Traza:
    dist = {origen: 0.0}
    pred: dict = {}
    cerrados: set = set()
    cola = [(0.0, origen)]
    tope = G.number_of_nodes()
    orden, frontera, arbol, cam_exp, cam_dest = [], [], [], [], []

    while cola:
        d_u, u = heapq.heappop(cola)
        if u in cerrados:
            continue
        cerrados.add(u)
        orden.append(u)
        frontera.append({n for _, n in cola if n not in cerrados})
        arbol.append((pred[u], u) if u in pred else None)
        cam_exp.append(_camino(pred, origen, u, tope))
        cam_dest.append(_camino(pred, origen, destino, tope))
        if u == destino:
            break
        for v, peso in _aristas_salientes(G, u):
            alt = d_u + peso
            if alt < dist.get(v, math.inf):
                dist[v] = alt
                pred[v] = u
                heapq.heappush(cola, (alt, v))

    return Traza(_reconstruir(pred, origen, destino), dist.get(destino),
                 orden=orden, frontera=frontera, arbol=arbol,
                 camino_expandido=cam_exp, camino_destino=cam_dest,
                 pasos=len(orden))


def a_estrella(G, origen, destino) -> Traza:
    g = {origen: 0.0}
    pred: dict = {}
    cerrados: set = set()
    cola = [(heuristica(G, origen, destino), origen)]
    tope = G.number_of_nodes()
    orden, frontera, arbol, cam_exp, cam_dest = [], [], [], [], []

    while cola:
        _, u = heapq.heappop(cola)
        if u in cerrados:
            continue
        cerrados.add(u)
        orden.append(u)
        frontera.append({n for _, n in cola if n not in cerrados})
        arbol.append((pred[u], u) if u in pred else None)
        cam_exp.append(_camino(pred, origen, u, tope))
        cam_dest.append(_camino(pred, origen, destino, tope))
        if u == destino:
            break
        for v, peso in _aristas_salientes(G, u):
            alt = g[u] + peso
            if alt < g.get(v, math.inf):
                g[v] = alt
                pred[v] = u
                heapq.heappush(cola, (alt + heuristica(G, v, destino), v))

    return Traza(_reconstruir(pred, origen, destino), g.get(destino),
                 orden=orden, frontera=frontera, arbol=arbol,
                 camino_expandido=cam_exp, camino_destino=cam_dest,
                 pasos=len(orden))


def bellman_ford(G, origen, destino) -> Traza:
    """La unidad no son nodos expandidos sino pasadas de relajación.

    En cada pasada se relajan todas las aristas del grafo; se registra el
    conjunto de nodos cuya distancia mejoró en esa pasada y las aristas de
    árbol que quedaron vigentes tras ella. A diferencia de Dijkstra y A*, el
    árbol se recablea: una arista incorporada en una pasada puede ser
    reemplazada en la siguiente.
    """
    dist = {n: math.inf for n in G.nodes}
    dist[origen] = 0.0
    pred: dict = {}
    aristas = [(u, v, d["peso"]) for u, v, d in G.edges(data=True)]
    tope = G.number_of_nodes()
    orden, frontera, arbol, cam_dest = [], [], [], []

    for _ in range(len(G.nodes) - 1):
        mejorados: set = set()
        for u, v, peso in aristas:
            if dist[u] + peso < dist[v]:
                dist[v] = dist[u] + peso
                pred[v] = u
                mejorados.add(v)
        if not mejorados:
            break
        orden.append(mejorados)
        frontera.append(set())
        arbol.append([(pred[v], v) for v in mejorados])
        cam_dest.append(_camino(pred, origen, destino, tope))

    costo = dist[destino]
    return Traza(_reconstruir(pred, origen, destino),
                 None if costo == math.inf else costo,
                 orden=orden, frontera=frontera, arbol=arbol,
                 camino_expandido=[None] * len(orden), camino_destino=cam_dest,
                 unidad="pasadas de relajación", pasos=len(orden))


TRAZAS = {
    "dijkstra": dijkstra,
    "a_estrella": a_estrella,
    "bellman_ford": bellman_ford,
}
