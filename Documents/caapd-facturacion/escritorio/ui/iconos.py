"""
ui/iconos.py — Íconos vectoriales de la aplicación (Tabler Icons, licencia MIT).

Los SVG viven en `recursos/iconos/<nombre>.svg` y se tiñen en tiempo de
ejecución con los colores de la paleta, de modo que un mismo archivo sirve
para un botón oscuro, uno claro o un chip activo/inactivo.

Uso típico:
    from ui import iconos

    btn = QPushButton("Actualizar")
    iconos.aplicar(btn, "refresh")                    # gris pizarra, 16 px
    iconos.aplicar(btn_nav, "home", "blanco", 18)     # barra azul
    lbl = iconos.etiqueta("alert-triangle", "aviso", 20)   # QLabel con pixmap

Si falta un SVG no se rompe la app: se devuelve un ícono vacío y se avisa
una sola vez por consola.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QAbstractButton, QLabel

import rutas

log = logging.getLogger(__name__)

DIR_ICONOS: Path = rutas.ruta_recurso("recursos", "iconos")

# Paleta (misma que tema.qss). Se puede pasar un "#rrggbb" directo también.
COLORES = {
    "texto": "#334155",      # gris pizarra: botones secundarios, títulos
    "gris": "#64748b",       # chips inactivos, textos de apoyo
    "blanco": "#ffffff",     # barra de navegación, botones de color
    "primario": "#0284c7",   # azul institucional
    "turquesa": "#0d9488",
    "exito": "#166534",
    "aviso": "#9a3412",
    "peligro": "#991b1b",
    "info": "#075985",
}

# Íconos por tipo de mensaje (toast, alertas, banners)
POR_TIPO = {
    "exito": "circle-check",
    "aviso": "alert-triangle",
    "peligro": "circle-x",
    "info": "info-circle",
}

_TAMANOS_ICONO = (16, 20, 24, 32, 48)
_avisados: set[str] = set()


def _color_hex(color: str) -> str:
    return COLORES.get(color, color)


@lru_cache(maxsize=None)
def _svg_bytes(nombre: str, color_hex: str) -> Optional[bytes]:
    ruta = DIR_ICONOS / f"{nombre}.svg"
    if not ruta.exists():
        if nombre not in _avisados:
            _avisados.add(nombre)
            log.warning("Ícono no encontrado: %s (ejecuta scripts/descargar_iconos.py)", ruta)
        return None
    svg = ruta.read_text(encoding="utf-8")
    # Tabler usa stroke="currentColor"; lo reemplazamos por el color pedido.
    svg = svg.replace("currentColor", color_hex)
    return svg.encode("utf-8")


def pixmap(nombre: str, color: str = "texto", tamano: int = 18, escala: float = 2.0) -> QPixmap:
    """Devuelve un QPixmap nítido (renderizado a `escala`x para pantallas HiDPI)."""
    datos = _svg_bytes(nombre, _color_hex(color))
    px = QPixmap(int(tamano * escala), int(tamano * escala))
    px.fill(Qt.GlobalColor.transparent)
    if datos is not None:
        render = QSvgRenderer(QByteArray(datos))
        pintor = QPainter(px)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        render.render(pintor, QRectF(0, 0, px.width(), px.height()))
        pintor.end()
    px.setDevicePixelRatio(escala)
    return px


@lru_cache(maxsize=None)
def _icono_cacheado(nombre: str, color: str) -> QIcon:
    ico = QIcon()
    for t in _TAMANOS_ICONO:
        ico.addPixmap(pixmap(nombre, color, t, escala=1.0))
    return ico


def icono(nombre: str, color: str = "texto") -> QIcon:
    """QIcon con varias resoluciones; Qt elige la adecuada según iconSize.

    Si aún no existe una QGuiApplication (p. ej. pruebas de modelos sin UI)
    devuelve un QIcon vacío en lugar de abortar el proceso.
    """
    if QGuiApplication.instance() is None:
        return QIcon()
    return _icono_cacheado(nombre, color)


def aplicar(boton: QAbstractButton, nombre: str, color: str = "texto", tamano: int = 16) -> None:
    """Pone el ícono a un botón y recuerda su nombre (ver `recolorear`)."""
    boton.setIcon(icono(nombre, color))
    boton.setIconSize(QSize(tamano, tamano))
    boton.setProperty("icono_nombre", nombre)
    boton.setProperty("icono_tamano", tamano)


def recolorear(boton: QAbstractButton, color: str) -> None:
    """Cambia solo el color del ícono ya aplicado (chips activo/inactivo)."""
    nombre = boton.property("icono_nombre")
    if nombre:
        boton.setIcon(icono(str(nombre), color))


def etiqueta(nombre: str, color: str = "texto", tamano: int = 18) -> QLabel:
    """QLabel que muestra solo el ícono (para tarjetas KPI, alertas, etc.)."""
    lbl = QLabel()
    lbl.setPixmap(pixmap(nombre, color, tamano))
    lbl.setFixedSize(tamano, tamano)
    lbl.setStyleSheet("background: transparent; border: none;")
    return lbl


def poner_en_etiqueta(lbl: QLabel, nombre: str, color: str = "texto", tamano: int = 18) -> None:
    """Reemplaza el contenido de un QLabel existente por el ícono."""
    lbl.setText("")
    lbl.setPixmap(pixmap(nombre, color, tamano))
    lbl.setFixedSize(tamano, tamano)
