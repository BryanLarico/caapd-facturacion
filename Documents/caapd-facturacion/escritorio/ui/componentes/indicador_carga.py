"""
ui/componentes/indicador_carga.py — Indicador visual de operación en segundo plano.
"""
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QWidget,
)


class IndicadorCarga(QFrame):
    """Muestra un indicador discreto de carga mientras un hilo trabaja."""

    def __init__(self, mensaje: str = "Cargando...", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            "background-color: #e0f2fe; border-radius: 8px; padding: 4px 12px;"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(10)

        self.barra = QProgressBar()
        self.barra.setRange(0, 0)  # Modo indeterminado
        self.barra.setFixedSize(120, 8)
        self.barra.setTextVisible(False)
        layout.addWidget(self.barra)

        self.lbl_texto = QLabel(mensaje)
        self.lbl_texto.setStyleSheet("color: #0369a1; font-weight: 500; font-size: 13px;")
        layout.addWidget(self.lbl_texto)

        self.hide()

    def iniciar(self, mensaje: str = "Cargando...") -> None:
        self.lbl_texto.setText(mensaje)
        self.show()

    def detener(self) -> None:
        self.hide()
