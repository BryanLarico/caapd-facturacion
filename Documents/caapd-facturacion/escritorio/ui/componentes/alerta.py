"""
ui/componentes/alerta.py — Componente reutilizable de avisos y alertas (tipo flash).

Soporta los 4 tipos estándar: exito, aviso, peligro, info.
El texto se ajusta en varias líneas y el contenedor crece en alto
(responsive): nunca se recorta el mensaje.
"""
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from ui import iconos


class AlertaWidget(QFrame):
    """
    Componente de alerta visual con ícono y texto descriptivo.
    """

    # Color del ícono según el tipo (coincide con alerta_texto_* en tema.qss)
    COLOR_ICONO = {
        "exito": "exito",
        "aviso": "aviso",
        "peligro": "peligro",
        "info": "info",
    }

    def __init__(
        self,
        mensaje: str = "",
        tipo: str = "info",
        cerrable: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.tipo = tipo
        self._cerrable = cerrable

        self.setProperty("class", f"alerta alerta_{tipo}")
        self.setObjectName(f"alerta_{tipo}")

        # El contenedor ocupa todo el ancho disponible y crece en alto según el texto
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Minimum)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        # Ícono
        self.lbl_icono = iconos.etiqueta(
            iconos.POR_TIPO.get(tipo, "info-circle"),
            self.COLOR_ICONO.get(tipo, "info"), 20)
        layout.addWidget(self.lbl_icono, alignment=Qt.AlignmentFlag.AlignTop)

        # Texto del mensaje (se parte en varias líneas y crece en alto según el ancho)
        self.lbl_mensaje = QLabel(mensaje)
        self.lbl_mensaje.setWordWrap(True)
        self.lbl_mensaje.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        politica = QSizePolicy(QSizePolicy.Policy.Expanding,
                               QSizePolicy.Policy.Preferred)
        politica.setHeightForWidth(True)
        self.lbl_mensaje.setSizePolicy(politica)
        self.lbl_mensaje.setMinimumWidth(0)
        self.lbl_mensaje.setProperty("class", f"alerta_texto_{tipo}")
        self.lbl_mensaje.setStyleSheet("background: transparent;")
        layout.addWidget(self.lbl_mensaje, stretch=1)

        # Botón de cerrar opcional
        if cerrable:
            self.btn_cerrar = QPushButton("")
            iconos.aplicar(self.btn_cerrar, "x", "gris", 14)
            self.btn_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_cerrar.setFixedSize(24, 24)
            self.btn_cerrar.setStyleSheet(
                "border: none; background: transparent; font-weight: bold; font-size: 14px;"
            )
            self.btn_cerrar.clicked.connect(self.hide)
            layout.addWidget(
                self.btn_cerrar, alignment=Qt.AlignmentFlag.AlignTop)

    def set_mensaje(self, mensaje: str, tipo: Optional[str] = None) -> None:
        """Actualiza el mensaje y opcionalmente el tipo de alerta."""
        if tipo and tipo != self.tipo:
            self.tipo = tipo
            self.setProperty("class", f"alerta alerta_{tipo}")
            self.lbl_mensaje.setProperty("class", f"alerta_texto_{tipo}")
            iconos.poner_en_etiqueta(
                self.lbl_icono, iconos.POR_TIPO.get(tipo, "info-circle"),
                self.COLOR_ICONO.get(tipo, "info"), 20)
            # Refrescar estilo en Qt
            self.style().unpolish(self)
            self.style().polish(self)
            self.lbl_mensaje.style().unpolish(self.lbl_mensaje)
            self.lbl_mensaje.style().polish(self.lbl_mensaje)

        self.lbl_mensaje.setText(mensaje)
        # Forzar recálculo de alto para que el texto largo no se recorte
        self.lbl_mensaje.updateGeometry()
        self.updateGeometry()
        self.show()

    def mostrar(self, mensaje: str, tipo: Optional[str] = None) -> None:
        """Alias de conveniencia para set_mensaje."""
        self.set_mensaje(mensaje, tipo)
