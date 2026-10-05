"""Métricas sobre una ruta obtenida (PTFG rev6, protocolo, párrafo 5).

Recorre las aristas efectivamente utilizadas y acumula la longitud, el costo y
la exposición al deterioro, entendida como la cantidad de baches comprendidos
en los tramos recorridos. El desvío relativo respecto de la ruta con α = 0 se
calcula en `analisis.py`, porque requiere comparar dos corridas.
"""
from __future__ import annotations


def _arista_minima(G, u, v):
    """En un multigrafo, la arista de menor peso entre dos nodos."""
    mejor = None
    for k in G[u][v]:
        d = G[u][v][k]
        if mejor is None or d["peso"] < mejor["peso"]:
            mejor = d
    return mejor


def de_ruta(G, ruta: list | None) -> dict:
    """Métricas acumuladas a lo largo de la ruta."""
    if not ruta or len(ruta) < 2:
        return {"longitud_m": None, "exposicion": None, "costo": None, "aristas": 0}

    longitud = exposicion = costo = 0.0
    for u, v in zip(ruta, ruta[1:]):
        d = _arista_minima(G, u, v)
        longitud += d["length"]
        exposicion += d.get("exposicion", 0.0)
        costo += d["peso"]

    return {
        "longitud_m": round(longitud, 3),
        "exposicion": round(exposicion, 3),
        "costo": round(costo, 4),
        "aristas": len(ruta) - 1,
    }


def informatividad(h_origen: float, costo_real: float | None) -> float | None:
    """Razón entre la estimación heurística en el origen y el costo real.

    Vale 1 cuando la heurística acierta exactamente y tiende a 0 cuando pierde
    poder informativo. Solo aplica a A*.
    """
    if not costo_real or costo_real <= 0 or h_origen is None:
        return None
    return round(min(1.0, h_origen / costo_real), 4)
