"""
ui/componentes/toast.py — Notificación emergente (toast) flotante y temporal.

Se muestra en la esquina superior derecha de la página, por encima del contenido,
y desaparece automáticamente después de unos segundos (5 s por defecto).
"""
from typing import Optional
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from ui import iconos


class Toast(QFrame):
    """Aviso flotante que se oculta solo. Tipos: exito, aviso, peligro, info."""

    DURACION_MS = 5000
    MARGEN = 16

    # (fondo, texto, borde)
    COLORES = {
        "exito": ("#dcfce7", "#166534", "#86efac"),
        "aviso": ("#ffedd5", "#9a3412", "#fdba74"),
        "peligro": ("#fee2e2", "#991b1b", "#fca5a5"),
        "info": ("#e0f2fe", "#075985", "#7dd3fc"),
    }

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMaximumWidth(480)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 10, 10)
        lay.setSpacing(10)

        self.lbl_icono = iconos.etiqueta("info-circle", "info", 20)
        lay.addWidget(self.lbl_icono, alignment=Qt.AlignmentFlag.AlignTop)

        self.lbl_mensaje = QLabel("")
        self.lbl_mensaje.setWordWrap(True)
        self.lbl_mensaje.setStyleSheet(
            "background: transparent; border: none; font-size: 13px; font-weight: 600;")
        lay.addWidget(self.lbl_mensaje, stretch=1)

        self.btn_cerrar = QPushButton("")
        iconos.aplicar(self.btn_cerrar, "x", "gris", 14)
        self.btn_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cerrar.setFixedSize(22, 22)
        self.btn_cerrar.setStyleSheet(
            "QPushButton { border: none; background: transparent; font-weight: bold; font-size: 13px; }"
            "QPushButton:hover { color: #000000; }"
        )
        self.btn_cerrar.clicked.connect(self.ocultar)
        lay.addWidget(self.btn_cerrar, alignment=Qt.AlignmentFlag.AlignTop)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.ocultar)

        self.hide()

    # ------------------------------------------------------------------
    def mostrar(self, mensaje: str, tipo: str = "info", duracion_ms: Optional[int] = None) -> None:
        """Muestra el aviso en la esquina superior derecha y lo oculta tras `duracion_ms`."""
        fondo, texto, borde = self.COLORES.get(tipo, self.COLORES["info"])
        self.setStyleSheet(
            f"QFrame#toast {{ background-color: {fondo}; border: 1px solid {borde}; "
            f"border-left: 5px solid {texto}; border-radius: 8px; }}"
        )
        iconos.poner_en_etiqueta(
            self.lbl_icono, iconos.POR_TIPO.get(tipo, "info-circle"), texto, 20)
        iconos.recolorear(self.btn_cerrar, texto)
        self.lbl_mensaje.setText(mensaje)
        self.lbl_mensaje.setStyleSheet(
            f"background: transparent; border: none; font-size: 13px; font-weight: 600; color: {texto};"
        )
        self.btn_cerrar.setStyleSheet(
            f"QPushButton {{ border: none; background: transparent; font-weight: bold; font-size: 13px; color: {texto}; }}"
        )

        self.adjustSize()
        self.reposicionar()
        self.show()
        self.raise_()

        self._timer.start(
            duracion_ms if duracion_ms is not None else self.DURACION_MS)

    def ocultar(self) -> None:
        self._timer.stop()
        self.hide()

    def reposicionar(self) -> None:
        """Coloca el toast en la esquina superior derecha del widget padre."""
        padre = self.parentWidget()
        if padre is None:
            return
        ancho = min(self.sizeHint().width(), self.maximumWidth(),
                    max(200, padre.width() - 2 * self.MARGEN))
        self.resize(ancho, self.sizeHint().height())
        x = max(self.MARGEN, padre.width() - self.width() - self.MARGEN)
        y = self.MARGEN
        self.move(x, y)
