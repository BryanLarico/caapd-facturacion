"""
respaldo.py — Hook de notificación de cambios de datos del sistema CAAPD Ispacas.

Cada operación que modifique usuarios, lecturas o configuración debe llamar a
on_datos_cambiados() para registrar la actividad y habilitar los respaldos automáticos
en la Fase 6.
"""

from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger("caapd.respaldo")


def on_datos_cambiados(tipo: str = "general", detalle: dict[str, Any] | None = None) -> None:
    """Registra que hubo una modificación en los datos.

    La Fase 6 implementará aquí el respaldo automático a Excel / archivo de contingencia.
    """
    logger.info("Cambio de datos registrado: tipo=%s, detalle=%s", tipo, detalle or {})
