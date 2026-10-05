"""Implementación instrumentada de Dijkstra, A* y Bellman-Ford.

Los tres se implementan directamente y no se toman de la biblioteca de análisis
de redes: registrar el esfuerzo de búsqueda exige instrumentar el bucle
principal, algo que las versiones de biblioteca no exponen. NetworkX se usa
como implementación de referencia para verificar la corrección.

Contadores (PTFG rev6, protocolo, párrafo 5):
  expandidos    nodos extraídos de la cola y cerrados (Dijkstra y A*)
  relajaciones  aristas evaluadas: cada vez que se compara d(u) + w(u, v)
                contra d(v), haya o no mejora
  mejoras       relajaciones que efectivamente redujeron d(v)
  pasadas       recorridos completos de la lista de aristas (Bellman-Ford)

Los tres algoritmos se mantienen en su formulación clásica (limitación 6 del
PTFG). Dijkstra y A* se detienen al cerrar el destino, como en las
formulaciones de Dijkstra (1959) y de Hart, Nilsson y Raphael (1968) para el
camino entre dos nodos. Bellman-Ford itera aproximaciones sucesivas hasta que
ninguna distancia cambia, como en la formulación de Bellman (1958); la cota de
n − 1 pasadas es el peor caso. Después verifica la ausencia de ciclos negativos.
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
    relajaciones: int = 0
    mejoras: int = 0
    pasadas: int = 0
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
    expandidos = relajaciones = mejoras = 0

    while cola:
        d_u, u = heapq.heappop(cola)
        if u in cerrados:                 # entrada obsoleta (borrado diferido)
            continue
        cerrados.add(u)
        expandidos += 1
        if u == destino:
            break
        for v, peso in _aristas_salientes(G, u):
            relajaciones += 1
            alt = d_u + peso
            if alt < dist.get(v, math.inf):
                dist[v] = alt
                pred[v] = u
                mejoras += 1
                heapq.heappush(cola, (alt, v))

    return Resultado(_reconstruir(pred, origen, destino), dist.get(destino),
                     expandidos=expandidos, relajaciones=relajaciones, mejoras=mejoras)


# --- A* ---------------------------------------------------------------------
def heuristica(G, n, destino) -> float:
    """Distancia en línea recta entre n y el destino, en coordenadas proyectadas.

    Es admisible porque w(e) = ℓ(e) · [1 + α · s(e)] ≥ ℓ(e), y la longitud de
    cualquier camino es al menos la distancia en línea recta entre sus extremos.
    En las proyecciones UTM usadas, el factor de escala en las áreas de estudio
    es menor que 1, de modo que la distancia proyectada no excede la real.
    """
    a, b = G.nodes[n], G.nodes[destino]
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def a_estrella(G, origen, destino) -> Resultado:
    g = {origen: 0.0}
    pred: dict = {}
    cerrados: set = set()
    h_origen = heuristica(G, origen, destino)
    cola = [(h_origen, origen)]
    expandidos = relajaciones = mejoras = 0

    while cola:
        _, u = heapq.heappop(cola)
        if u in cerrados:
            continue
        cerrados.add(u)
        expandidos += 1
        if u == destino:
            break
        for v, peso in _aristas_salientes(G, u):
            relajaciones += 1
            alt = g[u] + peso
            if alt < g.get(v, math.inf):
                g[v] = alt
                pred[v] = u
                mejoras += 1
                heapq.heappush(cola, (alt + heuristica(G, v, destino), v))

    return Resultado(_reconstruir(pred, origen, destino), g.get(destino),
                     expandidos=expandidos, relajaciones=relajaciones, mejoras=mejoras,
                     h_origen=h_origen)


# --- Bellman-Ford -----------------------------------------------------------
def bellman_ford(G, origen, destino) -> Resultado:
    dist = {n: math.inf for n in G.nodes}
    dist[origen] = 0.0
    pred: dict = {}
    aristas = [(u, v, d["peso"]) for u, v, d in G.edges(data=True)]
    pasadas = relajaciones = mejoras = 0

    for _ in range(len(G.nodes) - 1):
        cambio = False
        pasadas += 1
        for u, v, peso in aristas:
            relajaciones += 1
            if dist[u] + peso < dist[v]:
                dist[v] = dist[u] + peso
                pred[v] = u
                mejoras += 1
                cambio = True
        if not cambio:                    # convergencia: ninguna distancia cambió
            break

    for u, v, peso in aristas:            # detección de ciclo negativo
        if dist[u] + peso < dist[v]:
            raise CicloNegativo("el grafo contiene un ciclo de peso negativo")

    costo = dist[destino]
    return Resultado(_reconstruir(pred, origen, destino),
                     None if costo == math.inf else costo,
                     relajaciones=relajaciones, mejoras=mejoras, pasadas=pasadas)


ALGORITMOS = {
    "dijkstra": dijkstra,
    "a_estrella": a_estrella,
    "bellman_ford": bellman_ford,
}
