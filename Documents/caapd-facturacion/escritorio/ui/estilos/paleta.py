"""
paleta.py — Sistema de diseño centralizado CAAPD Ispacas (PySide6).

Todos los colores, fuentes, radios y medidas visuales se definen aquí.
Modificar estos valores cambia la apariencia en toda la aplicación.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Paleta:
    # Paleta principal — azul agua
    PRIMARIO: str = "#0369a1"
    PRIMARIO_HOVER: str = "#0284c7"
    PRIMARIO_CLARO: str = "#e0f2fe"
    SECUNDARIO: str = "#0ea5e9"
    ACENTO: str = "#06b6d4"

    # Fondos
    FONDO: str = "#f0f9ff"
    FONDO_ALT: str = "#ffffff"
    FONDO_SIDEBAR: str = "#0c4a6e"
    FONDO_PIE: str = "#0c4a6e"

    # Texto
    TEXTO: str = "#0f172a"
    TEXTO_SUAVE: str = "#475569"
    TEXTO_INVERSO: str = "#ffffff"
    TEXTO_LINK: str = "#0369a1"
    TEXTO_MUTED: str = "#64748b"

    # Bordes
    BORDE: str = "#bae6fd"
    BORDE_SUAVE: str = "#e0f2fe"

    # Alertas y estados
    EXITO: str = "#16a34a"
    EXITO_FONDO: str = "#dcfce7"
    EXITO_TEXTO: str = "#14532d"

    AVISO: str = "#d97706"
    AVISO_FONDO: str = "#fef3c7"
    AVISO_TEXTO: str = "#78350f"

    PELIGRO: str = "#dc2626"
    PELIGRO_FONDO: str = "#fee2e2"
    PELIGRO_TEXTO: str = "#7f1d1d"

    INFO: str = "#2563eb"
    INFO_FONDO: str = "#dbeafe"
    INFO_TEXTO: str = "#1e3a8a"

    # Mora
    MORA_AZUL: str = "#1E88E5"
    MORA_NARANJA: str = "#FB8C00"
    MORA_ROJO: str = "#E53935"
    MORA_PAGADO: str = "#16a34a"

    # Desplegables y Menús Popups (Regla centralizada)
    POPUP_FONDO: str = "#ffffff"
    POPUP_TEXTO: str = "#000000"
    POPUP_SELECCION_FONDO: str = "#e0f2fe"
    POPUP_SELECCION_TEXTO: str = "#000000"

    # Radios (en px)
    RADIO_SM: int = 6
    RADIO_MD: int = 10
    RADIO_LG: int = 16
    RADIO_FULL: int = 999

    # Tipografía
    FUENTE_FAMILIA: str = "Inter"
    FUENTE_FALLBACK: str = "Segoe UI"
    FUENTE_MONO: str = "Consolas"
    FUENTE_EMOJI: str = "Segoe UI Emoji"

    TAMANO_SM: int = 12
    TAMANO_BASE: int = 14
    TAMANO_LG: int = 16
    TAMANO_XL: int = 18
    TAMANO_2XL: int = 22
    TAMANO_3XL: int = 28


# Instancia única reutilizable
PALETA = Paleta()
