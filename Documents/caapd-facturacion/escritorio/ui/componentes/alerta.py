"""
ui/componentes/alerta.py — Componente reutilizable de avisos y alertas (tipo flash).

Soporta los 4 tipos estándar: exito, aviso, peligro, info.
"""
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class AlertaWidget(QFrame):
    """
    Componente de alerta visual con ícono y texto descriptivo.
    """

    ICONOS = {
        "exito": "✅",
        "aviso": "⚠️",
        "peligro": "❌",
        "info": "ℹ️",
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

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        # Ícono
        self.lbl_icono = QLabel(self.ICONOS.get(tipo, "ℹ️"))
        self.lbl_icono.setStyleSheet("font-size: 18px; background: transparent;")
        self.lbl_icono.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.lbl_icono)

        # Texto del mensaje
        self.lbl_mensaje = QLabel(mensaje)
        self.lbl_mensaje.setWordWrap(True)
        self.lbl_mensaje.setProperty("class", f"alerta_texto_{tipo}")
        self.lbl_mensaje.setStyleSheet("background: transparent;")
        layout.addWidget(self.lbl_mensaje, stretch=1)

        # Botón de cerrar opcional
        if cerrable:
            self.btn_cerrar = QPushButton("✕")
            self.btn_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_cerrar.setStyleSheet(
                "border: none; background: transparent; font-weight: bold; font-size: 14px;"
            )
            self.btn_cerrar.clicked.connect(self.hide)
            layout.addWidget(self.btn_cerrar)

    def set_mensaje(self, mensaje: str, tipo: Optional[str] = None) -> None:
        """Actualiza el mensaje y opcionalmente el tipo de alerta."""
        if tipo and tipo != self.tipo:
            self.tipo = tipo
            self.setProperty("class", f"alerta alerta_{tipo}")
            self.lbl_mensaje.setProperty("class", f"alerta_texto_{tipo}")
            self.lbl_icono.setText(self.ICONOS.get(tipo, "ℹ️"))
            # Refrescar estilo en Qt
            self.style().unpolish(self)
            self.style().polish(self)
            self.lbl_mensaje.style().unpolish(self.lbl_mensaje)
            self.lbl_mensaje.style().polish(self.lbl_mensaje)

        self.lbl_mensaje.setText(mensaje)
        self.show()

    def mostrar(self, mensaje: str, tipo: Optional[str] = None) -> None:
        """Alias de conveniencia para set_mensaje."""
        self.set_mensaje(mensaje, tipo)

