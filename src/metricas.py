"""Cálculo de las métricas sobre una ruta resultante.

Recorre las aristas efectivamente utilizadas y acumula longitud, tiempo de
recorrido (ec. 11), exposición al deterioro (ec. 10) y costo total (ec. 9).
"""
from __future__ import annotations

import math


def _arista_minima(G, u, v):
    """En un multigrafo, la arista de menor peso entre dos nodos."""
    mejor = None
    for _, _, datos in G.edges(nbunch=[u], data=True):
        pass
    for k in G[u][v]:
        d = G[u][v][k]
        if mejor is None or d["peso"] < mejor["peso"]:
            mejor = d
    return mejor


def de_ruta(G, ruta: list | None) -> dict:
    """Métricas acumuladas a lo largo de la ruta."""
    if not ruta or len(ruta) < 2:
        return {"longitud_m": None, "tiempo_s": None,
                "exposicion": None, "costo": None, "aristas": 0}

    longitud = tiempo = exposicion = costo = 0.0
    for u, v in zip(ruta, ruta[1:]):
        d = _arista_minima(G, u, v)
        longitud += d["length"]
        tiempo += d.get("travel_time", 0.0)
        exposicion += d.get("exposicion", 0.0)
        costo += d["peso"]

    return {
        "longitud_m": round(longitud, 3),
        "tiempo_s": round(tiempo, 3),
        "exposicion": round(exposicion, 4),
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


def resumen(valores: list[float]) -> dict:
    """Media, desviación típica y extremos, para agregar entre repeticiones."""
    limpios = [v for v in valores if v is not None and not math.isnan(v)]
    if not limpios:
        return {"n": 0, "media": None, "desv": None, "min": None, "max": None}
    n = len(limpios)
    media = sum(limpios) / n
    desv = (sum((v - media) ** 2 for v in limpios) / n) ** 0.5 if n > 1 else 0.0
    return {"n": n, "media": media, "desv": desv,
            "min": min(limpios), "max": max(limpios)}
