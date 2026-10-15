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


# ======================= NUEVO (1 de 2) =======================
def ruta_escritorio_usuario() -> Path:
    """
    Devuelve la carpeta Escritorio del usuario actual.

    En Windows consulta la carpeta real del Escritorio (funciona aunque esté
    redirigida a OneDrive). En otros sistemas usa ~/Desktop o ~/Escritorio.
    """
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class _GUID(ctypes.Structure):
                _fields_ = [
                    ("Data1", wintypes.DWORD),
                    ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD),
                    ("Data4", wintypes.BYTE * 8),
                ]

            # FOLDERID_Desktop = {B4BFCC3A-DB2C-424C-B029-7FE99A87C641}
            folder_id = _GUID(
                0xB4BFCC3A, 0xDB2C, 0x424C,
                (wintypes.BYTE * 8)(0xB0, 0x29, 0x7F, 0xE9, 0x9A, 0x87, 0xC6, 0x41),
            )
            puntero = ctypes.c_wchar_p()
            res = ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(folder_id), 0, None, ctypes.byref(puntero)
            )
            if res == 0 and puntero.value:
                ruta = Path(puntero.value)
                ctypes.windll.ole32.CoTaskMemFree(puntero)
                return ruta
        except Exception:
            pass

    for nombre in ("Desktop", "Escritorio"):
        candidata = Path.home() / nombre
        if candidata.exists():
            return candidata
    return Path.home() / "Desktop"


# ======================= NUEVO (2 de 2) =======================
def ruta_recibos(*partes: str) -> Path:
    """
    Carpeta de salida de los recibos PDF: <Escritorio del usuario>/recibos/...

    Ejemplo: ruta_recibos("2026-09", "BARRIO DE CHAUPI") -> Escritorio/recibos/2026-09/BARRIO DE CHAUPI
    La carpeta se crea si no existe.
    """
    p = ruta_escritorio_usuario().joinpath("recibos", *partes)
    p.mkdir(parents=True, exist_ok=True)
    return p


# ============ DESDE AQUÍ TODO ES IGUAL A TU VERSIÓN ============
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
        dir_resp = DIR_BASE.parent.joinpath("respaldos") if DIR_BASE.parent.joinpath(
            "respaldos").exists() else DIR_BASE.joinpath("respaldos")
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
