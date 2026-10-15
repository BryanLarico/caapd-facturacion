"""
ui/paginas/lectores_dialogos.py — Diálogos para crear y editar lectores de Firebase Auth.
"""
from __future__ import annotations
import re
from typing import Any, Dict, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
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
        self.setMinimumWidth(560)
        self.setModal(True)

        self._construir_ui()

    def _construir_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # Encabezado
        lbl_titulo = QLabel("Editar Lector Móvil" if self.es_edicion else "Registrar Nuevo Lector")
        lbl_titulo.setStyleSheet("font-size: 18px; font-weight: bold; color: #0f172a;")
        layout.addWidget(lbl_titulo)

        subtexto = (
            f"Modifique el nombre o asigne una nueva contraseña a {self.lector.get('email')}."
            if self.es_edicion
            else "Cree una cuenta autorizada para que el lector inicie sesión en la app Android."
        )
        lbl_sub = QLabel(subtexto)
        lbl_sub.setWordWrap(True)
        lbl_sub.setStyleSheet("font-size: 13px; color: #64748b; margin-bottom: 4px;")
        layout.addWidget(lbl_sub)

        # Formulario
        form_frame = QFrame()
        form_frame.setProperty("class", "tarjeta")
        l_form = QVBoxLayout(form_frame)
        l_form.setContentsMargins(20, 20, 20, 20)
        l_form.setSpacing(14)

        # Estilo para etiquetas de campos
        estilo_label = "font-size: 13px; font-weight: 600; color: #1e293b; margin-bottom: 2px;"
        estilo_input = """
            QLineEdit {
                min-height: 40px;
                font-size: 13px;
                color: #0f172a;
                background-color: #ffffff;
                border: 1.5px solid #cbd5e1;
                border-radius: 6px;
                padding: 6px 12px;
            }
            QLineEdit:focus {
                border-color: #0284c7;
            }
            QLineEdit:disabled {
                background-color: #f1f5f9;
                color: #475569;
                border-color: #e2e8f0;
            }
        """

        # Campo: Correo Electrónico
        col_email = QVBoxLayout()
        col_email.setSpacing(4)
        lbl_email = QLabel("Correo electrónico *:")
        lbl_email.setStyleSheet(estilo_label)
        col_email.addWidget(lbl_email)

        self.txt_email = QLineEdit()
        self.txt_email.setStyleSheet(estilo_input)
        self.txt_email.setPlaceholderText("ej. lector1@caapd.org")
        if self.es_edicion:
            self.txt_email.setText(self.lector.get("email", ""))
            self.txt_email.setEnabled(False)
        col_email.addWidget(self.txt_email)
        l_form.addLayout(col_email)

        # Campo: Nombre completo
        col_nom = QVBoxLayout()
        col_nom.setSpacing(4)
        lbl_nom = QLabel("Nombre completo del lector:")
        lbl_nom.setStyleSheet(estilo_label)
        col_nom.addWidget(lbl_nom)

        self.txt_nombre = QLineEdit()
        self.txt_nombre.setStyleSheet(estilo_input)
        self.txt_nombre.setPlaceholderText("ej. Carlos Quispe Mamani")
        if self.es_edicion:
            self.txt_nombre.setText(self.lector.get("display_name", ""))
        col_nom.addWidget(self.txt_nombre)
        l_form.addLayout(col_nom)

        # Campo: Contraseña
        col_pass = QVBoxLayout()
        col_pass.setSpacing(4)
        lbl_pass = QLabel("Contraseña *:" if not self.es_edicion else "Nueva contraseña (opcional):")
        lbl_pass.setStyleSheet(estilo_label)
        col_pass.addWidget(lbl_pass)

        fila_pass = QHBoxLayout()
        fila_pass.setSpacing(6)
        self.txt_password = QLineEdit()
        self.txt_password.setStyleSheet(estilo_input)
        self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)
        if self.es_edicion:
            self.txt_password.setPlaceholderText("Dejar en blanco para mantener la contraseña actual")
        else:
            self.txt_password.setPlaceholderText("Mínimo 6 caracteres")
        fila_pass.addWidget(self.txt_password, stretch=1)

        self.btn_ver_pass = QPushButton("👁️")
        self.btn_ver_pass.setFixedSize(44, 40)
        self.btn_ver_pass.setProperty("class", "boton boton_secundario")
        self.btn_ver_pass.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ver_pass.setToolTip("Ver/ocultar contraseña")
        self.btn_ver_pass.clicked.connect(self._toggle_ver_pass)
        fila_pass.addWidget(self.btn_ver_pass)
        col_pass.addLayout(fila_pass)

        if self.es_edicion:
            lbl_pass_hint = QLabel("Deje este campo vacío si no desea cambiar la contraseña actual.")
            lbl_pass_hint.setStyleSheet("font-size: 12px; color: #64748b;")
            col_pass.addWidget(lbl_pass_hint)

        l_form.addLayout(col_pass)

        # Campo: Confirmar Contraseña
        col_conf = QVBoxLayout()
        col_conf.setSpacing(4)
        lbl_conf = QLabel("Confirmar contraseña:")
        lbl_conf.setStyleSheet(estilo_label)
        col_conf.addWidget(lbl_conf)

        self.txt_confirm_pass = QLineEdit()
        self.txt_confirm_pass.setStyleSheet(estilo_input)
        self.txt_confirm_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_confirm_pass.setPlaceholderText("Repita la contraseña para confirmar")
        col_conf.addWidget(self.txt_confirm_pass)
        l_form.addLayout(col_conf)

        layout.addWidget(form_frame)

        # Mensaje de error inline
        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet("color: #dc2626; font-size: 13px; font-weight: bold; padding: 4px 8px;")
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

        self.btn_guardar = QPushButton("Guardar Cambios" if self.es_edicion else "Crear Lector")
        self.btn_guardar.setProperty("class", "boton boton_primario")
        self.btn_guardar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_guardar.setMinimumHeight(38)
        self.btn_guardar.setMinimumWidth(140)
        self.btn_guardar.clicked.connect(self._guardar)
        fila_botones.addWidget(self.btn_guardar)

        layout.addLayout(fila_botones)

    def _toggle_ver_pass(self) -> None:
        if self.txt_password.echoMode() == QLineEdit.EchoMode.Password:
            self.txt_password.setEchoMode(QLineEdit.EchoMode.Normal)
            self.txt_confirm_pass.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)
            self.txt_confirm_pass.setEchoMode(QLineEdit.EchoMode.Password)

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
