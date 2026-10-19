"""
ui/componentes/dialogo_confirmar.py — Diálogo modal de confirmación con diseño nativo y alto contraste.

Reemplaza los QMessageBox.question estándar para evitar problemas de contraste y textos
invisibles ocasionados por los temas oscuros del sistema operativo en Windows.
"""
from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui import iconos


class DialogoConfirmacion(QDialog):
    """Diálogo modal personalizado de confirmación con diseño estilizado y legible."""

    def __init__(
        self,
        parent: Optional[QWidget],
        titulo: str,
        mensaje_principal: str,
        detalle: str = "",
        texto_confirmar: str = "Confirmar",
        texto_cancelar: str = "Cancelar",
        es_peligro: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setModal(True)
        self.setMinimumWidth(460)

        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
                border-radius: 10px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(18)

        # Fila superior con icono y texto
        fila_cuerpo = QHBoxLayout()
        fila_cuerpo.setSpacing(16)
        fila_cuerpo.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Icono visual
        if es_peligro:
            nombre_icono, color_icono = "trash", "peligro"
        elif "desactivar" in titulo.lower():
            nombre_icono, color_icono = "player-pause", "aviso"
        else:
            nombre_icono, color_icono = "help-circle", "primario"
        lbl_icono = iconos.etiqueta(nombre_icono, color_icono, 32)
        fila_cuerpo.addWidget(lbl_icono)

        col_textos = QVBoxLayout()
        col_textos.setSpacing(6)

        lbl_tit = QLabel(mensaje_principal)
        lbl_tit.setWordWrap(True)
        lbl_tit.setStyleSheet("font-size: 15px; font-weight: bold; color: #0f172a;")
        col_textos.addWidget(lbl_tit)

        if detalle:
            lbl_det = QLabel(detalle)
            lbl_det.setWordWrap(True)
            lbl_det.setStyleSheet("font-size: 13px; color: #475569; line-height: 1.4;")
            col_textos.addWidget(lbl_det)

        fila_cuerpo.addLayout(col_textos, stretch=1)
        layout.addLayout(fila_cuerpo)

        # Botones inferiores
        fila_botones = QHBoxLayout()
        fila_botones.addStretch(1)
        fila_botones.setSpacing(10)

        self.btn_cancelar = QPushButton(texto_cancelar)
        self.btn_cancelar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancelar.setMinimumHeight(38)
        self.btn_cancelar.setMinimumWidth(100)
        self.btn_cancelar.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                color: #334155;
                font-size: 13px;
                font-weight: 600;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
            }
        """)
        self.btn_cancelar.clicked.connect(self.reject)
        fila_botones.addWidget(self.btn_cancelar)

        self.btn_confirmar = QPushButton(texto_confirmar)
        self.btn_confirmar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_confirmar.setMinimumHeight(38)
        self.btn_confirmar.setMinimumWidth(120)

        color_fondo = "#dc2626" if es_peligro else "#0284c7"
        color_hover = "#b91c1c" if es_peligro else "#0369a1"

        self.btn_confirmar.setStyleSheet(f"""
            QPushButton {{
                background-color: {color_fondo};
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                padding: 6px 18px;
            }}
            QPushButton:hover {{
                background-color: {color_hover};
            }}
        """)
        self.btn_confirmar.clicked.connect(self.accept)
        fila_botones.addWidget(self.btn_confirmar)

        layout.addLayout(fila_botones)


def pedir_confirmacion(
    parent: Optional[QWidget],
    titulo: str,
    mensaje_principal: str,
    detalle: str = "",
    texto_confirmar: str = "Confirmar",
    texto_cancelar: str = "Cancelar",
    es_peligro: bool = False,
) -> bool:
    """Función de ayuda para mostrar un diálogo modal de confirmación seguro y estilizado."""
    diag = DialogoConfirmacion(
        parent=parent,
        titulo=titulo,
        mensaje_principal=mensaje_principal,
        detalle=detalle,
        texto_confirmar=texto_confirmar,
        texto_cancelar=texto_cancelar,
        es_peligro=es_peligro,
    )
    return diag.exec() == QDialog.DialogCode.Accepted
