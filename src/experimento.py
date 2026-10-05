"""Protocolo experimental: generación de pares, ejecución y registro.

La medición del tiempo emplea el reloj monótono del sistema. Cada condición se
ejecuta un número fijo de repeticiones y se descartan las primeras, para
excluir el efecto de la inicialización y de la memoria caché del procesador.
"""
from __future__ import annotations

import csv
import math
import random
import time

import networkx as nx

from config import CFG
import algoritmos as alg
import metricas as met

CAMPOS = [
    "area", "configuracion", "replica", "alfa", "algoritmo",
    "origen", "destino", "repeticion", "tiempo_ms", "expandidos",
    "pasadas", "relajaciones", "longitud_m", "tiempo_s", "exposicion",
    "costo", "aristas", "informatividad",
]


def generar_pares(G, cantidad: int, semilla: int) -> list[tuple]:
    """Pares origen-destino aleatorios sobre la componente fuertemente conexa."""
    comps = list(nx.strongly_connected_components(G))
    if not comps:
        return []
    nodos = sorted(max(comps, key=len))
    if len(nodos) < 2:
        return []

    rng = random.Random(semilla)
    minimo = CFG["experimento"]["distancia_minima_m"]
    pares, intentos = [], 0
    while len(pares) < cantidad and intentos < cantidad * 200:
        intentos += 1
        o, d = rng.sample(nodos, 2)
        a, b = G.nodes[o], G.nodes[d]
        if alg._haversine(a["lat"], a["lon"], b["lat"], b["lon"]) < minimo:
            continue
        pares.append((o, d))
    return pares


def ejecutar(G, pares, area: str, configuracion: str, replica: int,
             alfa: float, filas: list) -> None:
    """Corre los tres algoritmos sobre cada par y agrega las mediciones."""
    reps = CFG["experimento"]["repeticiones"]
    calent = CFG["experimento"]["descartar_calentamiento"]
    tope_bf = CFG["experimento"]["limite_pares_bellman_ford"]

    for nombre, funcion in alg.ALGORITMOS.items():
        usados = pares[:tope_bf] if nombre == "bellman_ford" else pares
        for origen, destino in usados:
            for rep in range(reps):
                t0 = time.perf_counter()          # reloj monótono
                res = funcion(G, origen, destino)
                ms = (time.perf_counter() - t0) * 1000
                if rep < calent:                  # repetición de calentamiento
                    continue
                m = met.de_ruta(G, res.ruta)
                filas.append({
                    "area": area,
                    "configuracion": configuracion,
                    "replica": replica,
                    "alfa": alfa,
                    "algoritmo": nombre,
                    "origen": origen,
                    "destino": destino,
                    "repeticion": rep,
                    "tiempo_ms": round(ms, 4),
                    "expandidos": res.expandidos,
                    "pasadas": res.pasadas,
                    "relajaciones": res.relajaciones,
                    "informatividad": met.informatividad(res.h_origen, res.costo)
                                      if nombre == "a_estrella" else None,
                    **m,
                })


def volcar(filas: list, ruta) -> None:
    """Escribe la tabla de mediciones, entrada única del análisis."""
    with open(ruta, "w", encoding="utf-8", newline="") as fh:
        escritor = csv.DictWriter(fh, fieldnames=CAMPOS)
        escritor.writeheader()
        escritor.writerows(filas)
