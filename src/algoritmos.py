"""Implementación instrumentada de Dijkstra, A* y Bellman-Ford.

Los tres se implementan directamente y no se toman de la biblioteca de análisis
de redes, por dos razones: el objetivo específico 3 pide implementarlos, y
registrar el número de nodos expandidos exige instrumentar el bucle principal,
algo que las versiones de biblioteca no exponen. NetworkX se conserva como
oráculo de corrección en `verificacion.py`.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field


class CicloNegativo(Exception):
    """El grafo contiene un ciclo de peso negativo."""


@dataclass
class Resultado:
    ruta: list | None
    costo: float | None
    expandidos: int = 0
    pasadas: int = 0
    relajaciones: int = 0
    h_origen: float = 0.0
    extra: dict = field(default_factory=dict)


def _reconstruir(pred: dict, origen, destino) -> list | None:
    if destino not in pred and destino != origen:
        return None
    ruta, actual = [destino], destino
    while actual != origen:
        actual = pred[actual]
        ruta.append(actual)
    return ruta[::-1]


def _aristas_salientes(G, u):
    """Peso mínimo por vecino: en un multigrafo puede haber aristas paralelas."""
    mejor: dict = {}
    for _, v, datos in G.out_edges(u, data=True):
        p = datos["peso"]
        if v not in mejor or p < mejor[v]:
            mejor[v] = p
    return mejor.items()


# --- Dijkstra ---------------------------------------------------------------
def dijkstra(G, origen, destino) -> Resultado:
    dist = {origen: 0.0}
    pred: dict = {}
    cerrados: set = set()
    cola = [(0.0, origen)]
    expandidos = 0

    while cola:
        d_u, u = heapq.heappop(cola)
        if u in cerrados:                 # entrada obsoleta (borrado diferido)
            continue
        cerrados.add(u)
        expandidos += 1
        if u == destino:
            break
        for v, peso in _aristas_salientes(G, u):
            alt = d_u + peso
            if alt < dist.get(v, math.inf):
                dist[v] = alt
                pred[v] = u
                heapq.heappush(cola, (alt, v))

    return Resultado(_reconstruir(pred, origen, destino),
                     dist.get(destino), expandidos=expandidos)


# --- A* ---------------------------------------------------------------------
def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6_371_008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def heuristica(G, n, destino, c_min: float) -> float:
    """Distancia geodésica escalada: admisible bajo la ec. (9). Ecuación (8)."""
    a, b = G.nodes[n], G.nodes[destino]
    return _haversine(a["lat"], a["lon"], b["lat"], b["lon"]) * c_min


def a_estrella(G, origen, destino) -> Resultado:
    c_min = G.graph["c_min"]
    g = {origen: 0.0}
    pred: dict = {}
    cerrados: set = set()
    h_origen = heuristica(G, origen, destino, c_min)
    cola = [(h_origen, origen)]
    expandidos = 0

    while cola:
        _, u = heapq.heappop(cola)
        if u in cerrados:
            continue
        cerrados.add(u)
        expandidos += 1
        if u == destino:
            break
        for v, peso in _aristas_salientes(G, u):
            alt = g[u] + peso
            if alt < g.get(v, math.inf):
                g[v] = alt
                pred[v] = u
                heapq.heappush(cola, (alt + heuristica(G, v, destino, c_min), v))

    return Resultado(_reconstruir(pred, origen, destino), g.get(destino),
                     expandidos=expandidos, h_origen=h_origen)


# --- Bellman-Ford -----------------------------------------------------------
def bellman_ford(G, origen, destino) -> Resultado:
    dist = {n: math.inf for n in G.nodes}
    dist[origen] = 0.0
    pred: dict = {}
    aristas = [(u, v, d["peso"]) for u, v, d in G.edges(data=True)]
    pasadas = relajaciones = 0

    for _ in range(len(G.nodes) - 1):
        cambio = False
        pasadas += 1
        for u, v, peso in aristas:
            if dist[u] + peso < dist[v]:
                dist[v] = dist[u] + peso
                pred[v] = u
                relajaciones += 1
                cambio = True
        if not cambio:                    # salida temprana: ya convergió
            break

    for u, v, peso in aristas:            # detección de ciclo negativo
        if dist[u] + peso < dist[v]:
            raise CicloNegativo("el grafo contiene un ciclo de peso negativo")

    costo = dist[destino]
    return Resultado(_reconstruir(pred, origen, destino),
                     None if costo == math.inf else costo,
                     pasadas=pasadas, relajaciones=relajaciones)


ALGORITMOS = {
    "dijkstra": dijkstra,
    "a_estrella": a_estrella,
    "bellman_ford": bellman_ford,
}
