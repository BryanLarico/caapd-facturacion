"""
rutas.py — Gestión centralizada de rutas del programa de escritorio CAAPD Ispacas.

Garantiza que todas las rutas se calculen desde la ubicación del programa
y configura sys.path para la importación limpia de módulos.
"""
from pathlib import Path
import sys

# Directorio raíz del programa de escritorio
DIR_BASE = Path(__file__).resolve().parent

# Asegurar que el directorio base esté en sys.path
if str(DIR_BASE) not in sys.path:
    sys.path.insert(0, str(DIR_BASE))


def ruta_recurso(*partes: str) -> Path:
    """Devuelve la ruta absoluta a un recurso dentro de escritorio."""
    return DIR_BASE.joinpath(*partes)


def ruta_fuentes(*partes: str) -> Path:
    """Devuelve la ruta dentro de ui/estilos/fuentes/."""
    return DIR_BASE.joinpath("ui", "estilos", "fuentes", *partes)


def ruta_datos(*partes: str) -> Path:
    """Devuelve la ruta dentro de datos/."""
    p = DIR_BASE.joinpath("datos", *partes)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def ruta_salida(*partes: str) -> Path:
    """Devuelve la ruta dentro de salida/."""
    p = DIR_BASE.joinpath("salida", *partes)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def es_entorno_prueba() -> bool:
    """Indica si el sistema se está ejecutando en modo de prueba (CAAPD_ENTORNO=prueba)."""
    import os
    return os.environ.get("CAAPD_ENTORNO", "").strip().lower() == "prueba"


def ruta_respaldos(*partes: str) -> Path:
    """Devuelve la ruta dentro de respaldos/ (creándola si no existe)."""
    if es_entorno_prueba():
        dir_resp = DIR_BASE.joinpath("Base de datos PRUEBA", "respaldos")
    else:
        # Priorizar respaldos en la raíz si existe, sino en escritorio
        dir_resp = DIR_BASE.parent.joinpath("respaldos") if DIR_BASE.parent.joinpath("respaldos").exists() else DIR_BASE.joinpath("respaldos")
    p = dir_resp.joinpath(*partes)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def ruta_base_de_datos(*partes: str) -> Path:
    """Devuelve la ruta dentro de 'Base de datos/' (o 'Base de datos PRUEBA/' si CAAPD_ENTORNO=prueba)."""
    nombre_carpeta = "Base de datos PRUEBA" if es_entorno_prueba() else "Base de datos"
    dir_bd = DIR_BASE.joinpath(nombre_carpeta)
    dir_bd.mkdir(parents=True, exist_ok=True)
    p = dir_bd.joinpath(*partes)
    if partes:
        p.parent.mkdir(parents=True, exist_ok=True)
    return p


def ruta_plantillas(*partes: str) -> Path:
    """Devuelve la ruta dentro de plantillas/ dentro de escritorio/."""
    dir_pl = DIR_BASE.joinpath("plantillas")
    dir_pl.mkdir(parents=True, exist_ok=True)
    p = dir_pl.joinpath(*partes)
    if partes:
        p.parent.mkdir(parents=True, exist_ok=True)
    return p

