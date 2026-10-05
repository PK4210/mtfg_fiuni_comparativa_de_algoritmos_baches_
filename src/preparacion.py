"""Lectura y depuración de los conjuntos de baches.

Encarnación llega como KML de Google My Maps: la clase de cada marca no es un
campo de texto sino el color del icono, de modo que hay que resolver la
referencia de estilo. Jersey City llega como CSV y no trae clase alguna: se le
transfiere la distribución observada en Encarnación (ecuaciones 13 y 14).
"""
from __future__ import annotations

import collections
import csv
import io
import random
import re
import xml.etree.ElementTree as ET

from config import CFG

NS = {"kml": "http://www.opengis.net/kml/2.2"}


# --- Encarnación: KML -------------------------------------------------------
def _mapa_estilo_color(raiz) -> dict[str, str]:
    """Asocia cada identificador de estilo con su color RGB en mayúsculas."""
    colores: dict[str, str] = {}
    for est in raiz.iter("{%s}Style" % NS["kml"]):
        sid = est.get("id", "")
        nodo = est.find(".//kml:IconStyle/kml:color", NS)
        if nodo is None or not nodo.text:
            continue
        aabbggrr = nodo.text.strip()          # KML invierte el orden de canales
        rgb = (aabbggrr[6:8] + aabbggrr[4:6] + aabbggrr[2:4]).upper()
        colores[sid] = rgb
        colores[sid.replace("-normal", "").replace("-highlight", "")] = rgb
    return colores


def leer_kml(ruta: str) -> list[dict]:
    """Devuelve una lista de registros con longitud, latitud y clase."""
    raiz = ET.parse(ruta).getroot()
    colores = _mapa_estilo_color(raiz)
    corresp = {k.upper(): v for k, v in CFG["clases"]["correspondencia_color"].items()}

    registros = []
    for pm in raiz.iter("{%s}Placemark" % NS["kml"]):
        coord = pm.find(".//kml:Point/kml:coordinates", NS)
        if coord is None or not coord.text:
            continue
        lon, lat = (float(v) for v in coord.text.strip().split(",")[:2])

        estilo = pm.find("kml:styleUrl", NS)
        clave = estilo.text.lstrip("#") if estilo is not None and estilo.text else ""
        rgb = colores.get(clave)
        clase = corresp.get(rgb) if rgb else None
        if clase is None:                      # color no previsto: no se inventa
            continue

        nombre = pm.find("kml:name", NS)
        registros.append({
            "id": nombre.text if nombre is not None else "",
            "lon": lon,
            "lat": lat,
            "clase": clase,
        })
    return registros


# --- Jersey City: CSV -------------------------------------------------------
def leer_csv(ruta: str) -> list[dict]:
    """Lee el CSV del portal de datos abiertos y valida las coordenadas."""
    registros = []
    with io.open(ruta, encoding="utf-8") as fh:
        for fila in csv.DictReader(fh):
            try:
                lon = float(fila["longitude"])
                lat = float(fila["latitude"])
            except (TypeError, ValueError, KeyError):
                continue                       # coordenada ausente o ilegible
            registros.append({
                "id": fila.get("address", ""),
                "lon": lon,
                "lat": lat,
                "clase": None,                 # la fuente no publica clase
                "fecha": fila.get("date", ""),
                "distrito": fila.get("ward", ""),
            })
    return registros


# --- Depuración común -------------------------------------------------------
def depurar(registros: list[dict], bbox: list[float]) -> tuple[list[dict], dict]:
    """Descarta coordenadas fuera del recuadro y duplicados exactos."""
    oeste, sur, este, norte = bbox
    dentro, fuera, duplicados = [], 0, 0
    vistos: set[tuple] = set()
    for r in registros:
        if not (oeste <= r["lon"] <= este and sur <= r["lat"] <= norte):
            fuera += 1
            continue
        clave = (round(r["lon"], 7), round(r["lat"], 7), r.get("clase"))
        if clave in vistos:
            duplicados += 1
            continue
        vistos.add(clave)
        dentro.append(r)
    return dentro, {
        "leidos": len(registros),
        "fuera_del_area": fuera,
        "duplicados": duplicados,
        "retenidos": len(dentro),
    }


# --- Transferencia de distribución (ecuaciones 13 y 14) ---------------------
def proporciones(registros: list[dict]) -> dict[str, float]:
    """p_k = n_k / N, ecuación (13)."""
    conteos = collections.Counter(r["clase"] for r in registros)
    total = sum(conteos.values())
    return {k: c / total for k, c in conteos.items()}


def _reparte_en_configuracion(props: dict[str, float], config: str) -> dict[str, float]:
    """C2 usa las clases observadas; C3 subdivide la mayoritaria en dos mitades."""
    clases = CFG["configuraciones"][config]
    if config == "C2":
        return {k: props[k] for k in clases if k in props}
    mayor = max(props, key=props.get)
    salida = dict(props)
    mitad = salida.pop(mayor) / 2
    salida["individual"] = mitad
    salida["intermedia"] = mitad
    return {k: salida[k] for k in clases if k in salida}


def transferir_distribucion(clases_origen: list[str], n_destino: int,
                            semilla: int, config: str = "C2") -> list[str]:
    """Aplica al conjunto destino las proporciones observadas en origen.

    Devuelve un vector de longitud n_destino con las cantidades exactas por
    clase, permutado al azar. Ecuaciones (13) y (14).
    """
    conteos = collections.Counter(clases_origen)
    n_origen = sum(conteos.values())
    props = _reparte_en_configuracion(
        {k: c / n_origen for k, c in conteos.items()}, config)

    orden = [k for k in CFG["clases"]["orden"] if k in props]
    asignados: list[str] = []
    for k in orden[:-1]:
        asignados += [k] * round(props[k] * n_destino)
    # la última clase absorbe el redondeo: la suma es exactamente n_destino
    asignados += [orden[-1]] * (n_destino - len(asignados))

    rng = random.Random(semilla)
    rng.shuffle(asignados)                     # reparto espacialmente aleatorio
    return asignados


def contribucion(clase: str) -> float:
    """σ(r) = b(r) / b_máx, ecuación (12)."""
    baches = CFG["clases"]["baches_representados"]
    return baches[clase] / max(baches.values())
