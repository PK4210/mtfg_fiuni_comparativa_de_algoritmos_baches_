"""Protocolo experimental: pares origen-destino, medición, verificación y registro.

PTFG rev6, protocolo, párrafos 4 a 6:
  - 200 pares por ciudad, sorteados entre los nodos de la mayor componente
    fuertemente conexa, a ≥ 300 m en línea recta; los mismos para los tres
    algoritmos, todos los valores de α y ambos modelos de Jersey City.
  - Cada consulta se repite 5 veces con el reloj de alta resolución
    (time.perf_counter_ns); la primera se descarta como calentamiento y se
    informa la mediana de las cuatro restantes. El recolector de basura se
    suspende durante la medición. Se cronometra solo la búsqueda: el grafo ya
    está cargado.
  - Para cada par y cada α, los tres algoritmos deben obtener el mismo costo
    óptimo, con tolerancia relativa de 10⁻⁹, y coincidir con NetworkX.
"""
from __future__ import annotations

import csv
import gc
import math
import random
import statistics
import time

import networkx as nx

from config import CFG
import algoritmos as alg
import metricas as met

CAMPOS = [
    "area", "modelo", "replica", "alfa", "par", "algoritmo", "origen", "destino",
    "tiempo_ms", "tiempos_ms", "expandidos", "relajaciones", "mejoras", "pasadas",
    "longitud_m", "exposicion", "costo", "aristas", "informatividad",
    "costo_networkx", "verificado",
]


def distancia_recta(G, a, b) -> float:
    """Distancia euclidiana entre dos nodos, en metros (coordenadas proyectadas)."""
    na, nb = G.nodes[a], G.nodes[b]
    return math.hypot(na["x"] - nb["x"], na["y"] - nb["y"])


def generar_pares(G, cantidad: int, semilla: int) -> list[tuple]:
    """Pares aleatorios en la mayor componente fuertemente conexa, a ≥ 300 m."""
    comps = list(nx.strongly_connected_components(G))
    if not comps:
        return []
    nodos = sorted(max(comps, key=len))
    if len(nodos) < 2:
        return []

    rng = random.Random(semilla)
    minimo = CFG["experimento"]["distancia_minima_m"]
    pares, vistos, intentos = [], set(), 0
    while len(pares) < cantidad and intentos < cantidad * 500:
        intentos += 1
        o, d = rng.sample(nodos, 2)
        if (o, d) in vistos or distancia_recta(G, o, d) < minimo:
            continue
        vistos.add((o, d))
        pares.append((o, d))
    if len(pares) < cantidad:
        raise RuntimeError(f"solo se obtuvieron {len(pares)} pares de {cantidad}")
    return pares


def _cronometrar(funcion, G, origen, destino) -> tuple[list[float], alg.Resultado]:
    """Repite la consulta; devuelve los tiempos válidos (ms) y el último resultado."""
    reps = CFG["experimento"]["repeticiones"]
    calent = CFG["experimento"]["descartar_calentamiento"]
    tiempos, res = [], None
    gc.collect()
    gc.disable()
    try:
        for rep in range(reps):
            t0 = time.perf_counter_ns()
            res = funcion(G, origen, destino)
            dt = time.perf_counter_ns() - t0
            if rep >= calent:
                tiempos.append(dt / 1e6)
    finally:
        gc.enable()
    return tiempos, res


def _coinciden(a: float | None, b: float | None, tol: float) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= tol * max(abs(a), abs(b), 1e-12)


def ejecutar(G, pares, area: str, modelo: str, replica: int, alfa: float,
             filas: list) -> dict:
    """Corre los tres algoritmos sobre cada par, verifica y agrega las mediciones."""
    tol = CFG["experimento"]["tolerancia_relativa"]
    fallas = []
    for k, (origen, destino) in enumerate(pares):
        try:
            ref = nx.shortest_path_length(G, origen, destino, weight="peso")
        except nx.NetworkXNoPath:
            ref = None
        resultados = {}
        for nombre, funcion in alg.ALGORITMOS.items():
            tiempos, res = _cronometrar(funcion, G, origen, destino)
            resultados[nombre] = (tiempos, res)

        costos = [r.costo for _, r in resultados.values()]
        ok = all(_coinciden(c, ref, tol) for c in costos)
        if not ok:
            fallas.append({"par": k, "origen": origen, "destino": destino,
                           "costos": costos, "networkx": ref})

        for nombre, (tiempos, res) in resultados.items():
            m = met.de_ruta(G, res.ruta)
            filas.append({
                "area": area, "modelo": modelo, "replica": replica, "alfa": alfa,
                "par": k, "algoritmo": nombre, "origen": origen, "destino": destino,
                "tiempo_ms": round(statistics.median(tiempos), 5),
                "tiempos_ms": " ".join(f"{t:.5f}" for t in tiempos),
                "expandidos": res.expandidos if nombre != "bellman_ford" else None,
                "relajaciones": res.relajaciones,
                "mejoras": res.mejoras,
                "pasadas": res.pasadas if nombre == "bellman_ford" else None,
                "informatividad": met.informatividad(res.h_origen, res.costo)
                                  if nombre == "a_estrella" else None,
                "costo_networkx": None if ref is None else round(ref, 6),
                "verificado": ok,
                **m,
            })
    return {"area": area, "modelo": modelo, "replica": replica, "alfa": alfa,
            "pares": len(pares), "discrepancias": len(fallas), "detalle": fallas[:5]}


def volcar(filas: list, ruta) -> None:
    """Escribe la tabla de mediciones, entrada única del análisis."""
    with open(ruta, "w", encoding="utf-8", newline="") as fh:
        escritor = csv.DictWriter(fh, fieldnames=CAMPOS)
        escritor.writeheader()
        escritor.writerows(filas)
