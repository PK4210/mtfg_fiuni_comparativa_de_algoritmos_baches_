"""Comprobaciones de verificación complementarias.

La verificación principal (los tres algoritmos y NetworkX deben dar el mismo
costo óptimo en cada par y cada α, con tolerancia relativa de 10⁻⁹) se hace
dentro de `experimento.ejecutar`, sobre toda la muestra. Este módulo agrega:
  - comprobación cruzada y contraste con NetworkX sobre una muestra (uso suelto);
  - admisibilidad de la heurística de A*;
  - integridad del grafo, respeto del sentido de circulación y coherencia de
    las trazas que se usan para las animaciones.
"""
from __future__ import annotations

import math

import networkx as nx

import algoritmos as alg

from config import CFG

TOL = CFG["experimento"]["tolerancia_relativa"]


def _distintos(a: float, b: float) -> bool:
    return abs(a - b) > TOL * max(abs(a), abs(b), 1e-12)


def optimalidad_cruzada(G, pares) -> dict:
    """Los tres algoritmos deben producir rutas de costo idéntico."""
    fallas, comparados = [], 0
    for origen, destino in pares:
        costos = {}
        for nombre, funcion in alg.ALGORITMOS.items():
            costos[nombre] = funcion(G, origen, destino).costo
        validos = [c for c in costos.values() if c is not None]
        if len(validos) < 2:
            continue
        comparados += 1
        if _distintos(max(validos), min(validos)):
            fallas.append({"par": (origen, destino), "costos": costos})
    return {"comparados": comparados, "discrepancias": len(fallas),
            "detalle": fallas[:5]}


def contra_networkx(G, pares) -> dict:
    """Contrasta el costo propio con el de la implementación de referencia."""
    fallas, comparados = [], 0
    for origen, destino in pares:
        propio = alg.dijkstra(G, origen, destino).costo
        try:
            referencia = nx.shortest_path_length(G, origen, destino, weight="peso")
        except nx.NetworkXNoPath:
            continue
        if propio is None:
            continue
        comparados += 1
        if _distintos(propio, referencia):
            fallas.append({"par": (origen, destino),
                           "propio": propio, "networkx": referencia})
    return {"comparados": comparados, "discrepancias": len(fallas),
            "detalle": fallas[:5]}


def admisibilidad(G, pares) -> dict:
    """h(n) nunca debe superar el costo real mínimo hasta el destino."""
    violaciones, comprobados = 0, 0
    peor = 0.0
    for _, destino in pares:
        reales = nx.shortest_path_length(G, target=destino, weight="peso")
        for nodo, real in reales.items():
            h = alg.heuristica(G, nodo, destino)
            comprobados += 1
            exceso = h - real
            if exceso > TOL * max(real, 1.0):
                violaciones += 1
                peor = max(peor, exceso)
    return {"comprobados": comprobados, "violaciones": violaciones,
            "peor_exceso_m": round(peor, 4)}


def sentidos_respetados(G, pares) -> dict:
    """Ninguna ruta puede circular en contramano.

    Comprueba que cada tramo consecutivo de la ruta corresponda a una arista
    dirigida que sale del nodo anterior. Si un algoritmo devolviera un tramo
    en contra del sentido de circulación, aparecería aquí.
    """
    infracciones, tramos, rutas = [], 0, 0
    for origen, destino in pares:
        for nombre, funcion in alg.ALGORITMOS.items():
            ruta = funcion(G, origen, destino).ruta
            if not ruta or len(ruta) < 2:
                continue
            rutas += 1
            for u, v in zip(ruta, ruta[1:]):
                tramos += 1
                if not G.has_edge(u, v):
                    infracciones.append({"algoritmo": nombre, "tramo": (u, v)})
    return {"rutas": rutas, "tramos": tramos,
            "en_contramano": len(infracciones), "detalle": infracciones[:5]}


def trazas_coherentes(G, pares) -> dict:
    """La instrumentación para animar no debe alterar el comportamiento.

    El número de nodos que registra `trazas.py` tiene que coincidir con el que
    cuenta `algoritmos.py` para el mismo par.
    """
    import trazas as tz

    discrepancias, comparados = [], 0
    for origen, destino in pares:
        for nombre in ("dijkstra", "a_estrella"):
            r = alg.ALGORITMOS[nombre](G, origen, destino)
            t = tz.TRAZAS[nombre](G, origen, destino)
            comparados += 1
            if r.expandidos != len(t.orden) or (
                    r.costo is not None and t.costo is not None
                    and _distintos(r.costo, t.costo)):
                discrepancias.append({
                    "algoritmo": nombre, "par": (origen, destino),
                    "expandidos": (r.expandidos, len(t.orden)),
                    "costo": (r.costo, t.costo)})
    return {"comparados": comparados, "discrepancias": len(discrepancias),
            "detalle": discrepancias[:5]}


def expansion_dibujable(G, pares) -> dict:
    """Todo lo que el video dibuja tiene que existir en el grafo dirigido.

    `sentidos_respetados` cubre la ruta final; esto extiende la comprobación al
    árbol de exploración completo y a los caminos que se resaltan cuadro a
    cuadro, que es mucho más de lo que se muestra en pantalla. Además exige que
    cada camino resaltado arranque en el origen y sea una cadena continua: una
    discontinuidad delataría un error al encadenar las geometrías.
    """
    import trazas as tz

    aristas, caminos = 0, 0
    inexistentes, discontinuos = [], []

    def revisar_camino(nombre, camino, origen, destino=None):
        nonlocal caminos
        if not camino:
            return
        caminos += 1
        if camino[0] != origen or (destino is not None and camino[-1] != destino):
            discontinuos.append({"algoritmo": nombre, "motivo": "extremos",
                                 "camino": camino[:3]})
            return
        for u, v in zip(camino, camino[1:]):
            if not G.has_edge(u, v):
                discontinuos.append({"algoritmo": nombre, "motivo": "tramo",
                                     "tramo": (u, v)})
                return

    for origen, destino in pares:
        for nombre, funcion in tz.TRAZAS.items():
            t = funcion(G, origen, destino)

            pares_arbol = []
            for entrada in t.arbol:
                if entrada is None:
                    continue
                pares_arbol += entrada if isinstance(entrada, list) else [entrada]
            for u, v in pares_arbol:
                aristas += 1
                if not G.has_edge(u, v):
                    inexistentes.append({"algoritmo": nombre, "arista": (u, v)})

            for camino in t.camino_expandido:
                revisar_camino(nombre, camino, origen)
            for camino in t.camino_destino:
                revisar_camino(nombre, camino, origen, destino)

    return {"aristas_de_arbol": aristas, "caminos_resaltados": caminos,
            "aristas_inexistentes": len(inexistentes),
            "caminos_rotos": len(discontinuos),
            "detalle": (inexistentes + discontinuos)[:5]}


def integridad_grafo(G) -> dict:
    """Comprobaciones estructurales sobre el grafo construido."""
    largos = [d["length"] for _, _, d in G.edges(data=True)]
    sev = [d.get("severidad", 0.0) for _, _, d in G.edges(data=True)]
    return {
        "aristas_long_cero": sum(1 for x in largos if x <= 0),
        "severidad_fuera_de_rango": sum(1 for s in sev if s < 0 or s > 1),
        "nodos_sin_coordenadas": sum(
            1 for _, d in G.nodes(data=True) if "lat" not in d or "lon" not in d),
        "pesos_negativos": sum(
            1 for _, _, d in G.edges(data=True) if d.get("peso", 0) < 0),
        "componentes_fuertes": nx.number_strongly_connected_components(G),
    }
