"""Lectura, depuración y asignación de clase de los conjuntos de baches.

Encarnación llega como KML de Google My Maps: la clase de cada marca no es un
campo de texto sino el color del ícono, de modo que hay que resolver la
referencia de estilo. Esa clase la asignaron los autores del relevamiento y no
se modifica: sobre Encarnación no se aplica ningún agrupamiento adicional.

Jersey City llega como CSV de reparaciones y no trae clase: cada registro es un
punto suelto. La clase se le asigna con uno de dos modelos (PTFG rev6,
protocolo, párrafo 2), aplicados únicamente a ese conjunto:

  M1  proporción igualada: la misma proporción de agrupaciones que Encarnación,
      sorteada de forma uniforme y sin reposición.
  M2  agrupación por radio: los registros a ≤ r metros entre sí, encadenados,
      forman un grupo; cada grupo se reduce a su centroide con clase agrupación.
"""
from __future__ import annotations

import collections
import csv
import io
import random
import xml.etree.ElementTree as ET

from pyproj import Transformer

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
    """Descarta coordenadas fuera del recuadro y registros idénticos.

    Solo es duplicado un registro idéntico en todos sus campos. Dos reparaciones
    en la misma dirección con fechas distintas son registros distintos: en
    Jersey City 493 coordenadas aparecen en dos o más registros y ninguno de
    ellos es idéntico a otro, de modo que se conservan los 6.664.
    """
    oeste, sur, este, norte = bbox
    dentro, fuera, duplicados = [], 0, 0
    vistos: set = set()
    for r in registros:
        if not (oeste <= r["lon"] <= este and sur <= r["lat"] <= norte):
            fuera += 1
            continue
        clave = tuple(sorted(r.items()))
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


# --- Modelo 1: proporción igualada ------------------------------------------
def modelo_proporcion(registros: list[dict], semilla: int) -> tuple[list[dict], dict]:
    """Asigna la clase agrupación a exactamente round(p · N) registros al azar.

    El sorteo es uniforme y sin reposición; el resto queda como individual.
    """
    p = CFG["modelos"]["M1"]["proporcion_agrupacion"]
    n = len(registros)
    k = round(p * n)
    elegidos = set(random.Random(semilla).sample(range(n), k))
    salida = [dict(r, clase="agrupacion" if i in elegidos else "individual")
              for i, r in enumerate(registros)]
    return salida, {"modelo": "M1", "semilla": semilla, "registros": n,
                    "agrupaciones": k, "individuales": n - k,
                    "pct_agrupaciones": round(100 * k / n, 2) if n else 0.0}


# --- Modelo 2: agrupación por radio -----------------------------------------
def modelo_radio(registros: list[dict], epsg: int,
                 radio: float | None = None) -> tuple[list[dict], dict]:
    """Agrupa por cercanía: componentes conexas del grafo «a ≤ r metros».

    Equivale a DBSCAN con un mínimo de dos puntos por vecindad: dos registros a
    distancia ≤ r quedan en el mismo grupo, y la relación se encadena. Cada
    grupo se reemplaza por un único punto en el centroide de sus registros, con
    clase agrupación; los registros aislados conservan la clase individual.
    """
    radio = CFG["modelos"]["M2"]["radio_m"] if radio is None else radio
    a_metros = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    a_grados = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    xy = [a_metros.transform(r["lon"], r["lat"]) for r in registros]

    padre = list(range(len(xy)))

    def raiz(i: int) -> int:
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    # rejilla de celdas de lado r: solo se comparan registros de celdas vecinas
    celdas: dict = collections.defaultdict(list)
    for i, (x, y) in enumerate(xy):
        celdas[(int(x // radio), int(y // radio))].append(i)
    r2 = radio * radio
    for (cx, cy), propios in celdas.items():
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in celdas.get((cx + dx, cy + dy), ()):
                    for i in propios:
                        if i < j and (xy[i][0] - xy[j][0]) ** 2 + (xy[i][1] - xy[j][1]) ** 2 <= r2:
                            a, b = raiz(i), raiz(j)
                            if a != b:
                                padre[a] = b

    grupos: dict = collections.defaultdict(list)
    for i in range(len(xy)):
        grupos[raiz(i)].append(i)

    salida, tamanos = [], []
    for miembros in grupos.values():
        if len(miembros) == 1:
            salida.append(dict(registros[miembros[0]], clase="individual"))
            continue
        cx = sum(xy[i][0] for i in miembros) / len(miembros)
        cy = sum(xy[i][1] for i in miembros) / len(miembros)
        lon, lat = a_grados.transform(cx, cy)
        tamanos.append(len(miembros))
        salida.append({"id": "grupo de %d registros" % len(miembros), "lon": lon,
                       "lat": lat, "clase": "agrupacion", "miembros": len(miembros)})

    n_ind = sum(1 for r in salida if r["clase"] == "individual")
    n_grp = len(tamanos)
    return salida, {"modelo": "M2", "radio_m": radio, "registros": len(registros),
                    "individuales": n_ind, "agrupaciones": n_grp,
                    "registros_en_agrupaciones": sum(tamanos),
                    "puntos_resultantes": n_ind + n_grp,
                    "pct_agrupaciones": round(100 * n_grp / (n_ind + n_grp), 2) if salida else 0.0,
                    "tamano_maximo": max(tamanos, default=0)}


def aporte(clase: str) -> float:
    """Baches que representa un registro: 1 si es individual, b si es agrupación."""
    return float(CFG["clases"]["baches_representados"][clase])
