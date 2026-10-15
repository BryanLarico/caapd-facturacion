"""
ui/paginas/lectores_dialogos.py — Diálogos para crear y editar lectores de Firebase Auth.
"""
from __future__ import annotations
import re
from typing import Any, Dict, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from servicios.datos import ServicioDatos
from ui.hilos import Worker, mostrar_dialogo_error


class DialogoLector(QDialog):
    """Diálogo modal para crear un nuevo lector o editar uno existente."""

    def __init__(
        self,
        servicio_datos: ServicioDatos,
        lector: Optional[Dict[str, Any]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.servicio = servicio_datos
        self.lector = lector  # Si es None -> Crear; si tiene datos -> Editar
        self.es_edicion = lector is not None

        titulo = "Editar Lector" if self.es_edicion else "Nuevo Lector Móvil"
        self.setWindowTitle(titulo)
        self.resize(540, 570)
        self.setModal(True)

        self._construir_ui()

    def _construir_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Encabezado
        texto_titulo = (
            f"✏️ Editar Lector: {self.lector.get('display_name') or self.lector.get('email', '')}"
            if self.es_edicion
            else "➕ Registrar Nuevo Lector"
        )
        lbl_titulo = QLabel(texto_titulo)
        lbl_titulo.setObjectName("dialogo_titulo")
        layout.addWidget(lbl_titulo)

        subtexto = (
            f"Modifique el nombre o asigne una nueva contraseña a {self.lector.get('email')}."
            if self.es_edicion
            else "Cree una cuenta autorizada para que el lector inicie sesión en la app Android."
        )
        lbl_sub = QLabel(subtexto)
        lbl_sub.setObjectName("dialogo_subtitulo")
        lbl_sub.setWordWrap(True)
        layout.addWidget(lbl_sub)

        # Campo: Correo Electrónico
        self.txt_email = self._crear_campo(
            layout,
            "Correo electrónico *:",
            "Ej. lector1@caapd.org",
        )
        if self.es_edicion:
            self.txt_email.setText(self.lector.get("email", ""))
            self.txt_email.setEnabled(False)

        # Campo: Nombre completo
        self.txt_nombre = self._crear_campo(
            layout,
            "Nombre completo del lector:",
            "Ej. Carlos Quispe Mamani",
        )
        if self.es_edicion:
            self.txt_nombre.setText(self.lector.get("display_name", ""))

        # Campo: Contraseña
        texto_contrasena = (
            "Nueva contraseña (opcional):"
            if self.es_edicion
            else "Contraseña *:"
        )
        placeholder_contrasena = (
            "Dejar en blanco para mantener la contraseña actual"
            if self.es_edicion
            else "Mínimo 6 caracteres"
        )
        self.txt_password = self._crear_campo(
            layout, texto_contrasena, placeholder_contrasena
        )
        self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)

        # Campo: Confirmar Contraseña
        self.txt_confirm_pass = self._crear_campo(
            layout,
            "Confirmar contraseña:",
            "Repita la contraseña para confirmar",
        )
        self.txt_confirm_pass.setEchoMode(QLineEdit.EchoMode.Password)

        self.chk_mostrar_contrasenas = QCheckBox("Mostrar contraseñas")
        self.chk_mostrar_contrasenas.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_mostrar_contrasenas.toggled.connect(
            self._alternar_visibilidad_contrasenas
        )
        layout.addWidget(self.chk_mostrar_contrasenas)

        if self.es_edicion:
            lbl_pass_hint = QLabel(
                "Deje la contraseña en blanco si no desea cambiarla."
            )
            lbl_pass_hint.setObjectName("dialogo_ayuda")
            layout.addWidget(lbl_pass_hint)

        # Mensaje de error inline
        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("dialogo_error")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()
        layout.addWidget(self.lbl_error)

        # Botones de acción
        fila_botones = QHBoxLayout()
        fila_botones.addStretch(1)

        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setProperty("class", "boton boton_secundario")
        self.btn_cancelar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancelar.setMinimumHeight(38)
        self.btn_cancelar.setMinimumWidth(100)
        self.btn_cancelar.clicked.connect(self.reject)
        fila_botones.addWidget(self.btn_cancelar)

        self.btn_guardar = QPushButton(
            "Guardar Cambios" if self.es_edicion else "Guardar Lector"
        )
        self.btn_guardar.setProperty("class", "boton boton_primario")
        self.btn_guardar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_guardar.setMinimumHeight(38)
        self.btn_guardar.setMinimumWidth(160)
        self.btn_guardar.clicked.connect(self._guardar)
        fila_botones.addWidget(self.btn_guardar)

        layout.addLayout(fila_botones)

    @staticmethod
    def _crear_campo(
        layout: QVBoxLayout, etiqueta: str, placeholder: str
    ) -> QLineEdit:
        lbl = QLabel(etiqueta)
        layout.addWidget(lbl)
        campo = QLineEdit()
        campo.setPlaceholderText(placeholder)
        layout.addWidget(campo)
        return campo

    def _alternar_visibilidad_contrasenas(self, visible: bool) -> None:
        modo = (
            QLineEdit.EchoMode.Normal
            if visible
            else QLineEdit.EchoMode.Password
        )
        self.txt_password.setEchoMode(modo)
        self.txt_confirm_pass.setEchoMode(modo)

    def _mostrar_error(self, mensaje: str) -> None:
        self.lbl_error.setText(f"⚠️ {mensaje}")
        self.lbl_error.show()

    def _guardar(self) -> None:
        self.lbl_error.hide()
        email = self.txt_email.text().strip().lower()
        nombre = self.txt_nombre.text().strip()
        pwd = self.txt_password.text().strip()
        confirm_pwd = self.txt_confirm_pass.text().strip()

        # Validaciones
        if not self.es_edicion:
            if not email or "@" not in email or "." not in email:
                self._mostrar_error("Ingrese un correo electrónico válido.")
                self.txt_email.setFocus()
                return

            if not pwd or len(pwd) < 6:
                self._mostrar_error("La contraseña debe tener al menos 6 caracteres.")
                self.txt_password.setFocus()
                return

            if pwd != confirm_pwd:
                self._mostrar_error("Las contraseñas no coinciden.")
                self.txt_confirm_pass.setFocus()
                return
        else:
            if pwd:
                if len(pwd) < 6:
                    self._mostrar_error("La nueva contraseña debe tener al menos 6 caracteres.")
                    self.txt_password.setFocus()
                    return
                if pwd != confirm_pwd:
                    self._mostrar_error("Las contraseñas no coinciden.")
                    self.txt_confirm_pass.setFocus()
                    return

        # Deshabilitar botones durante el guardado
        self.btn_guardar.setEnabled(False)
        self.btn_cancelar.setEnabled(False)
        self.btn_guardar.setText("Guardando...")

        uid = self.lector.get("uid") if self.es_edicion else None

        def tarea() -> Any:
            if self.es_edicion:
                return self.servicio.actualizar_lector(
                    uid=uid,
                    display_name=nombre,
                    password=pwd if pwd else None,
                )
            else:
                return self.servicio.crear_lector(
                    email=email,
                    password=pwd,
                    display_name=nombre if nombre else None,
                )

        worker = Worker(tarea)
        worker.signals.resultado.connect(self._al_guardar_exitoso)
        worker.signals.error.connect(self._al_guardar_error)
        from PySide6.QtCore import QThreadPool
        QThreadPool.globalInstance().start(worker)

    def _al_guardar_exitoso(self, resultado: Any) -> None:
        self.accept()

    def _al_guardar_error(self, err: str) -> None:
        self.btn_guardar.setEnabled(True)
        self.btn_cancelar.setEnabled(True)
        self.btn_guardar.setText("Guardar Cambios" if self.es_edicion else "Crear Lector")
        msg = str(err)
        if "EMAIL_EXISTS" in msg or "already exists" in msg:
            self._mostrar_error("Ya existe un lector registrado con ese correo electrónico.")
        else:
            self._mostrar_error(f"Error al guardar: {msg}")
