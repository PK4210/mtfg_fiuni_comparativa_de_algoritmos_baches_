"""Construcción del grafo vial, asignación espacial y ponderación.

Cubre las fases F2 a F5 del Capítulo 3: descarga y simplificación de la red,
proyección métrica, cálculo de velocidades y tiempos, asignación de los
registros de deterioro a las aristas mediante índice espacial (árbol R) y
aplicación de la función de costo.
"""
from __future__ import annotations

import collections
import pickle

import geopandas as gpd
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
            return pickle.load(fh)

    G = ox.graph.graph_from_bbox(
        bbox=tuple(area_cfg["bbox"]),
        network_type=CFG["grafo"]["tipo_red"],
        simplify=CFG["grafo"]["simplificar"],
    )
    # las coordenadas geográficas se conservan antes de proyectar: la heurística
    # de A* las necesita para calcular la distancia geodésica, ecuación (8)
    for _, datos in G.nodes(data=True):
        datos["lon"], datos["lat"] = datos["x"], datos["y"]

    G = ox.projection.project_graph(G, to_crs=f"EPSG:{area_cfg['epsg_metrico']}")

    # velocidades y tiempos: ecuación (16). OSMnx toma la señalización cuando
    # existe y la imputa por jerarquía vial cuando no.
    G = ox.routing.add_edge_speeds(G, fallback=CFG["grafo"]["velocidad_por_defecto"])
    G = ox.routing.add_edge_travel_times(G)

    with open(ruta, "wb") as fh:
        pickle.dump(G, fh)
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


# --- F4: asignación espacial ------------------------------------------------
def asignar_severidad(G: nx.MultiDiGraph, registros: list[dict],
                      epsg: int) -> tuple[nx.MultiDiGraph, dict]:
    """Asigna cada registro a la arista más próxima dentro del radio.

    Emplea el índice espacial de GeoPandas (árbol R) para no comparar cada
    punto con todas las aristas. Ecuaciones (15) y (17).
    """
    radio = CFG["asignacion"]["radio_tolerancia_m"]
    aristas = ox.convert.graph_to_gdfs(G, nodes=False)
    indice = aristas.sindex

    puntos = gpd.GeoSeries(
        [Point(r["lon"], r["lat"]) for r in registros], crs="EPSG:4326"
    ).to_crs(epsg=epsg)

    acumulado: dict = collections.defaultdict(float)
    descartados = 0
    for reg, pt in zip(registros, puntos):
        pos = indice.nearest(pt, return_all=False)[1][0]
        arista = aristas.iloc[pos]
        if arista.geometry.distance(pt) <= radio:
            acumulado[arista.name] += prep.contribucion(reg["clase"])
        else:
            descartados += 1

    for _, _, datos in G.edges(data=True):
        datos["severidad"] = 0.0
    for clave, suma in acumulado.items():
        u, v, k = clave
        G.edges[u, v, k]["severidad"] = min(1.0, suma)   # ecuación (17)

    con_dato = sum(1 for _, _, d in G.edges(data=True) if d["severidad"] > 0)
    return G, {
        "registros_asignados": len(registros) - descartados,
        "registros_descartados": descartados,
        "aristas_con_deterioro": con_dato,
        "aristas_totales": G.number_of_edges(),
        "cobertura_aristas_pct": round(100 * con_dato / G.number_of_edges(), 2),
    }


# --- F5: ponderación --------------------------------------------------------
def ponderar(G: nx.MultiDiGraph, alfa: float) -> nx.MultiDiGraph:
    """Aplica w(e) = long(e) · [1 + alfa · s(e)] sobre cada arista, ec. (9)."""
    for _, _, datos in G.edges(data=True):
        long_e = datos["length"]
        sev_e = datos.get("severidad", 0.0)
        datos["peso"] = long_e * (1.0 + alfa * sev_e)
        datos["exposicion"] = sev_e * long_e          # ecuación (10)

    c_min = min(d["peso"] / d["length"]
                for _, _, d in G.edges(data=True) if d["length"] > 0)
    G.graph["c_min"] = c_min                          # requerido por la ec. (8)
    G.graph["alfa"] = alfa
    return G
