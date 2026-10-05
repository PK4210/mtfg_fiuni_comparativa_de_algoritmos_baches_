"""Carga de la configuración y rutas del proyecto.

Ningún otro módulo define constantes: todo sale de `config.yaml`.
"""
from __future__ import annotations

import pathlib

import yaml

RAIZ = pathlib.Path(__file__).resolve().parent.parent

DATOS_CRUDOS = RAIZ / "datos" / "crudos"
DATOS_DERIVADOS = RAIZ / "datos" / "derivados"
RES_FIGURAS = RAIZ / "resultados" / "figuras"
RES_TABLAS = RAIZ / "resultados" / "tablas"
RES_MAPAS = RAIZ / "resultados" / "mapas"

for _d in (DATOS_DERIVADOS, RES_FIGURAS, RES_TABLAS, RES_MAPAS):
    _d.mkdir(parents=True, exist_ok=True)


def cargar(ruta: pathlib.Path | str | None = None) -> dict:
    """Devuelve el contenido de config.yaml como diccionario."""
    ruta = pathlib.Path(ruta) if ruta else RAIZ / "config.yaml"
    with open(ruta, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


CFG = cargar()


def area(nombre: str) -> dict:
    """Devuelve la configuración de un área de estudio."""
    if nombre not in CFG["areas"]:
        disponibles = ", ".join(CFG["areas"])
        raise KeyError(f"área desconocida: {nombre!r}. Disponibles: {disponibles}")
    return CFG["areas"][nombre]
