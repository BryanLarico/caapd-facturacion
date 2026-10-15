"""
ui/componentes/tarjeta_stat.py — Tarjeta estadística para el panel de Inicio.

Muestra cifras destacadas con fondo degradado y sombra suave mediante QGraphicsDropShadowEffect.
"""
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class TarjetaStat(QFrame):
    """
    Tarjeta visual de métricas estadísticas (ej. Recibos generados, pagados, pendientes).
    """

    def __init__(
        self,
        numero: int = 0,
        label: str = "",
        variante: str = "azul",  # azul, verde, naranja
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.variante = variante
        self.setObjectName(f"stat_card_{variante}")
        self.setProperty("class", "tarjeta_stat")

        # Configuración de sombra suave (exclusivo para tarjetas de inicio)
        sombra = QGraphicsDropShadowEffect(self)
        sombra.setBlurRadius(10)
        sombra.setOffset(0, 2)
        sombra.setColor(QColor(0, 0, 0, 24))
        self.setGraphicsEffect(sombra)

        # Altura fija equilibrada y compacta para encajar perfectamente en pantalla
        self.setFixedHeight(72)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(1)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Número grande
        self.lbl_numero = QLabel(str(numero))
        self.lbl_numero.setProperty("class", "stat_numero")
        self.lbl_numero.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_numero.setStyleSheet("background: transparent;")
        layout.addWidget(self.lbl_numero)

        # Etiqueta descriptiva
        self.lbl_label = QLabel(label.upper())
        self.lbl_label.setProperty("class", "stat_label")
        self.lbl_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_label.setStyleSheet("background: transparent;")
        layout.addWidget(self.lbl_label)

    def set_valor(self, numero: int) -> None:
        """Actualiza la cifra mostrada."""
        self.lbl_numero.setText(str(numero))
