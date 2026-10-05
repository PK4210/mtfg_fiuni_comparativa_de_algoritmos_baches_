"""Construcción del grafo vial, asignación espacial y ponderación.

Descarga y simplificación de la red, proyección métrica, asignación de los
registros de baches a las aristas mediante índice espacial (árbol R), cálculo
de la severidad por tramo y aplicación de la función de costo del PTFG rev6.
"""
from __future__ import annotations

import collections
import pickle

import geopandas as gpd
import numpy as np
import networkx as nx
import osmnx as ox
from shapely.geometry import Point

from config import CFG, DATOS_DERIVADOS, RAIZ
import preparacion as prep

ox.settings.log_console = False
ox.settings.requests_timeout = 300
# la caché de OSMnx vive junto a los demás derivados, no dentro de src/
ox.settings.cache_folder = str(DATOS_DERIVADOS / "cache_osm")


# --- F2: construcción -------------------------------------------------------
def construir(area_cfg: dict, cache: bool = True) -> nx.MultiDiGraph:
    """Descarga la red vial, la simplifica y la proyecta al sistema métrico."""
    nombre = area_cfg["nombre"].split(",")[0].strip().lower().replace(" ", "_")
    ruta = DATOS_DERIVADOS / f"grafo_{nombre}.gpickle"
    if cache and ruta.exists():
        with open(ruta, "rb") as fh:
            return longitudes_proyectadas(pickle.load(fh))

    G = ox.graph.graph_from_bbox(
        bbox=tuple(area_cfg["bbox"]),
        network_type=CFG["grafo"]["tipo_red"],
        simplify=CFG["grafo"]["simplificar"],
    )
    # las coordenadas geográficas se conservan antes de proyectar, para los
    # mapas; la heurística de A* usa las proyectadas (x, y), en metros
    for _, datos in G.nodes(data=True):
        datos["lon"], datos["lat"] = datos["x"], datos["y"]

    G = ox.projection.project_graph(G, to_crs=f"EPSG:{area_cfg['epsg_metrico']}")

    # velocidades y tiempos de recorrido: dato descriptivo, no entra al costo.
    # OSMnx toma la señalización cuando existe y la imputa por jerarquía vial
    # cuando no.
    G = ox.routing.add_edge_speeds(G, fallback=CFG["grafo"]["velocidad_por_defecto"])
    G = ox.routing.add_edge_travel_times(G)

    with open(ruta, "wb") as fh:
        pickle.dump(G, fh)
    return longitudes_proyectadas(G)


def longitudes_proyectadas(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Mide la longitud ℓ(e) de cada arista en el plano proyectado (UTM).

    OSMnx calcula `length` sobre una esfera, mientras que la heurística de A* es
    la distancia en línea recta entre coordenadas proyectadas, que se basan en el
    elipsoide. Las dos métricas difieren hasta en un 0,2 %, y en tramos
    este-oeste la longitud esférica puede quedar por debajo de la recta
    proyectada, lo que haría inadmisible la heurística. Medidas ambas en el mismo
    plano, la recta entre dos nodos nunca supera la longitud de un camino entre
    ellos. La longitud de OSMnx se conserva en `length_osmnx`.
    """
    if G.graph.get("longitudes_proyectadas"):
        return G
    for u, v, datos in G.edges(data=True):
        datos["length_osmnx"] = datos["length"]
        geom = datos.get("geometry")
        if geom is not None:
            datos["length"] = float(geom.length)
        else:
            a, b = G.nodes[u], G.nodes[v]
            datos["length"] = float(((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2) ** 0.5)
    G.graph["longitudes_proyectadas"] = True
    return G


def _nombre_calle(datos: dict) -> str:
    """El atributo `name` de OSM puede venir como cadena o como lista."""
    n = datos.get("name")
    if isinstance(n, list):
        return n[0] if n else ""
    return n or ""


def aplicar_correcciones_sentido(G: nx.MultiDiGraph) -> dict:
    """Sobrescribe el sentido que publica OSM con el declarado por los autores.

    Lee `datos/crudos/sentidos_corregidos.csv`. Convertir una calle a doble
    sentido agrega la arista recíproca; convertirla a sentido único elimina la
    recíproca si existiera. Mientras el archivo no tenga filas, no hace nada.
    """
    ruta = RAIZ / CFG.get("sentidos", {}).get(
        "archivo_correcciones", "datos/crudos/sentidos_corregidos.csv")
    informe = {"archivo": str(ruta.name), "reglas": 0,
               "aristas_agregadas": 0, "aristas_eliminadas": 0}
    if not ruta.exists():
        return informe

    reglas: dict[str, str] = {}
    with open(ruta, encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea or linea.startswith("#") or linea.startswith("nombre_calle"):
                continue
            partes = [p.strip() for p in linea.split(",")]
            if len(partes) >= 2 and partes[1] in ("unico", "doble"):
                reglas[partes[0].casefold()] = partes[1]
    informe["reglas"] = len(reglas)
    if not reglas:
        return informe

    for u, v, k, datos in list(G.edges(keys=True, data=True)):
        regla = reglas.get(_nombre_calle(datos).casefold())
        if regla is None:
            continue
        recip = G.has_edge(v, u)
        if regla == "doble" and not recip:
            inverso = {kk: vv for kk, vv in datos.items() if kk != "geometry"}
            inverso["reversed"] = not datos.get("reversed", False)
            inverso["oneway"] = False
            G.add_edge(v, u, **inverso)
            datos["oneway"] = False
            informe["aristas_agregadas"] += 1
        elif regla == "unico" and recip:
            G.remove_edges_from([(v, u, kk) for kk in list(G[v][u])])
            datos["oneway"] = True
            informe["aristas_eliminadas"] += 1

    return informe


def resumen(G: nx.MultiDiGraph) -> dict:
    """Medidas estructurales del grafo, para el Capítulo 5."""
    largo = [d["length"] for _, _, d in G.edges(data=True)]
    comps = list(nx.strongly_connected_components(G))
    mayor = max(comps, key=len) if comps else set()
    return {
        "nodos": G.number_of_nodes(),
        "aristas": G.number_of_edges(),
        "grado_medio": round(2 * G.number_of_edges() / G.number_of_nodes(), 3),
        "long_total_km": round(sum(largo) / 1000, 2),
        "long_media_m": round(sum(largo) / len(largo), 2),
        "aristas_long_cero": sum(1 for x in largo if x <= 0),
        "componentes_fuertes": len(comps),
        "nodos_componente_mayor": len(mayor),
    }


# --- F4: asignación espacial y severidad -------------------------------------
def asignar_severidad(G: nx.MultiDiGraph, registros: list[dict],
                      epsg: int) -> tuple[nx.MultiDiGraph, dict]:
    """Asigna cada registro al tramo más próximo y calcula la severidad.

    PTFG rev6, protocolo, párrafo 3. Cada registro va a la arista más cercana si
    está a ≤ 20 m (índice espacial, árbol R); los demás se descartan y se
    informan. Por arista:

        baches(e) = suma de los aportes asignados (1 o b por registro)
        d(e)      = baches(e) / ℓ(e)
        s(e)      = mín(1, d(e) / d95)

    donde d95 es el percentil 95 de d(e) entre las aristas con baches.
    """
    radio = CFG["asignacion"]["radio_tolerancia_m"]
    aristas = ox.convert.graph_to_gdfs(G, nodes=False)
    indice = aristas.sindex

    puntos = gpd.GeoSeries(
        [Point(r["lon"], r["lat"]) for r in registros], crs="EPSG:4326"
    ).to_crs(epsg=epsg)

    baches: dict = collections.defaultdict(float)
    registros_por_arista: dict = collections.defaultdict(int)
    descartados = 0
    for reg, pt in zip(registros, puntos):
        pos = indice.nearest(pt, return_all=False)[1][0]
        arista = aristas.iloc[pos]
        if arista.geometry.distance(pt) <= radio:
            baches[arista.name] += prep.aporte(reg["clase"])
            registros_por_arista[arista.name] += 1
        else:
            descartados += 1

    densidades = sorted(b / G.edges[k]["length"] for k, b in baches.items())
    d95 = float(np.percentile(densidades, CFG["costo"]["percentil_tope"])) if densidades else 0.0

    for _, _, datos in G.edges(data=True):
        datos["baches"] = 0.0
        datos["densidad"] = 0.0
        datos["severidad"] = 0.0
    for clave, b in baches.items():
        datos = G.edges[clave]
        datos["baches"] = b
        datos["densidad"] = b / datos["length"]
        datos["severidad"] = min(1.0, datos["densidad"] / d95) if d95 > 0 else 0.0
    G.graph["d95"] = d95

    con_dato = len(baches)
    return G, {
        "registros_asignados": len(registros) - descartados,
        "registros_descartados": descartados,
        "baches_asignados": round(sum(baches.values()), 1),
        "aristas_con_deterioro": con_dato,
        "aristas_totales": G.number_of_edges(),
        "cobertura_aristas_pct": round(100 * con_dato / G.number_of_edges(), 2),
        "d95_baches_por_m": round(d95, 6),
        "aristas_en_tope": sum(1 for d in densidades if d >= d95),
    }


# --- F5: ponderación --------------------------------------------------------
def ponderar(G: nx.MultiDiGraph, alfa: float) -> nx.MultiDiGraph:
    """Aplica w(e) = ℓ(e) · [1 + α · s(e)] sobre cada arista.

    La exposición de una arista es la cantidad de baches que contiene; la de una
    ruta, la suma sobre sus tramos (protocolo, párrafo 5). Como s(e) ≥ 0, el
    costo de una arista nunca es inferior a su longitud, condición que hace
    admisible la heurística euclidiana de A*.
    """
    for _, _, datos in G.edges(data=True):
        datos["peso"] = datos["length"] * (1.0 + alfa * datos.get("severidad", 0.0))
        datos["exposicion"] = datos.get("baches", 0.0)
    G.graph["alfa"] = alfa
    return G
