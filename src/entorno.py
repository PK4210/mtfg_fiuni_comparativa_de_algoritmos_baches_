"""Captura de la especificación del equipo y del entorno de ejecución.

El tiempo de cómputo es una de las métricas comparadas, de modo que toda
medición debe quedar acompañada del equipo donde se obtuvo. Este módulo lo
registra automáticamente en cada corrida: así ninguna tabla de resultados
queda huérfana de su contexto, y no hace falta recordar dónde se ejecutó.
"""
from __future__ import annotations

import platform
import subprocess
import sys

from config import RAIZ


def _ps(consulta: str) -> str:
    """Ejecuta una consulta de PowerShell y devuelve la primera línea útil."""
    try:
        salida = subprocess.run(
            ["powershell", "-NoProfile", "-Command", consulta],
            capture_output=True, text=True, timeout=25,
        ).stdout
        return " ".join(salida.split())
    except Exception:
        return ""


def describir() -> dict:
    """Devuelve la especificación del equipo y las versiones del entorno."""
    datos = {
        "equipo": platform.node(),
        "sistema_operativo": f"{platform.system()} {platform.release()}",
        "version_so": platform.version(),
        "arquitectura": platform.machine(),
        "python": sys.version.split()[0],
        "procesador": platform.processor(),
    }

    if platform.system() == "Windows":
        datos["procesador"] = _ps(
            "(Get-CimInstance Win32_Processor).Name") or datos["procesador"]
        datos["nucleos"] = _ps(
            "$c=Get-CimInstance Win32_Processor; "
            "\"$($c.NumberOfCores) fisicos / $($c.NumberOfLogicalProcessors) logicos\"")
        datos["memoria_gb"] = _ps(
            "[math]::Round((Get-CimInstance Win32_ComputerSystem)"
            ".TotalPhysicalMemory/1GB,1)")
        datos["memoria_mt_s"] = _ps(
            "(Get-CimInstance Win32_PhysicalMemory | "
            "Select-Object -First 1).Speed")
        # El disco que interesa es el que aloja el proyecto, no el del
        # sistema: es el que interviene en la lectura de los datos.
        letra = str(RAIZ)[:1].upper()
        datos["almacenamiento"] = _ps(
            f"$p = Get-Partition -DriveLetter {letra}; "
            "$d = Get-Disk -Number $p.DiskNumber; "
            "\"$($d.FriendlyName) ($($d.BusType), "
            "$([math]::Round($d.Size/1e9,1)) GB)\"")
        datos["unidad_del_proyecto"] = f"{letra}:"

    for paquete in ("osmnx", "networkx", "geopandas", "shapely", "matplotlib"):
        try:
            datos[f"version_{paquete}"] = __import__(paquete).__version__
        except Exception:
            datos[f"version_{paquete}"] = "no disponible"

    return datos


if __name__ == "__main__":
    import json
    print(json.dumps(describir(), ensure_ascii=False, indent=2))
