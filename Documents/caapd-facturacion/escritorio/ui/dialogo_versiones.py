"""Opciones de reparación y retorno de versión."""
from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QLabel, QLineEdit, QListWidget, QPushButton, QVBoxLayout,
)

from servicios import actualizador


class HiloVersiones(QThread):
    resultado = Signal(object)
    error = Signal(str)

    def __init__(self, reparar=False, parent=None):
        super().__init__(parent)
        self.reparar = reparar

    def run(self):
        try:
            versiones = ([actualizador.version_para_reparar()] if self.reparar
                         else actualizador.versiones_anteriores())
            self.resultado.emit(versiones)
        except Exception as e:
            self.error.emit(str(e))


class DialogoVersiones(QDialog):
    def __init__(self, parent=None, reparar=False):
        super().__init__(parent)
        self.reparar = reparar
        self.info = None
        self.versiones = []
        self.setWindowTitle("Reparar instalación" if reparar else "Volver a una versión anterior")
        self.resize(680, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        titulo = QLabel(self.windowTitle())
        titulo.setObjectName("dialogo_titulo")
        titulo.setWordWrap(True)
        layout.addWidget(titulo)
        self.estado = QLabel("Consultando versiones publicadas…")
        self.estado.setObjectName("dialogo_subtitulo")
        self.estado.setTextFormat(Qt.TextFormat.PlainText)
        self.estado.setWordWrap(True)
        layout.addWidget(self.estado)
        aviso = QLabel(
            "Se reinstalará el programa sin modificar sus datos." if reparar else
            "Advertencia: una versión anterior puede no ser compatible con sus datos actuales. "
            "Haga un respaldo antes de continuar. Escriba VOLVER para confirmar.")
        aviso.setWordWrap(True)
        aviso.setProperty("class", "alerta_texto_peligro" if not reparar else "")
        layout.addWidget(aviso)
        self.lista = QListWidget()
        self.lista.setAccessibleName("Versiones disponibles")
        self.lista.setWordWrap(True)
        self.lista.setStyleSheet("""
            QListWidget { background: #ffffff; color: #1e293b;
                border: 1px solid #cbd5e1; border-radius: 8px; font-size: 13px; }
            QListWidget::item { padding: 12px; border-bottom: 1px solid #e2e8f0; }
            QListWidget::item:selected { background: #e0f2fe; color: #075985; }
        """)
        layout.addWidget(self.lista)
        self.confirmacion = QLineEdit()
        self.confirmacion.setPlaceholderText("VOLVER")
        self.confirmacion.setAccessibleName("Confirmación: escriba VOLVER")
        self.confirmacion.setVisible(not reparar)
        layout.addWidget(self.confirmacion)
        self.instalar = QPushButton("Reparar ahora" if reparar else "Instalar versión anterior")
        self.instalar.setProperty("class", "boton boton_peligro" if not reparar else "boton")
        self.instalar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.instalar.setStyleSheet("""
            QPushButton:disabled { background-color: #e2e8f0; color: #94a3b8;
                border: 1px solid #cbd5e1; }
        """)
        self.instalar.setEnabled(False)
        layout.addWidget(self.instalar)
        self.instalar.clicked.connect(self._aceptar)
        self.lista.currentRowChanged.connect(self._habilitar)
        self.confirmacion.textChanged.connect(self._habilitar)
        self.hilo = HiloVersiones(reparar, self)
        self.hilo.resultado.connect(self._cargar)
        self.hilo.error.connect(self._error)
        self.hilo.start()

    def _error(self, mensaje):
        actualizador._log(f"ERROR al cargar opciones de versión: {mensaje}")
        self.estado.setText("No pudimos consultar las versiones disponibles. "
                            "Revise su conexión a Internet e inténtelo más tarde.")

    def _cargar(self, versiones):
        self.versiones = versiones
        for info in versiones:
            notas = " ".join(info.notas.split())[:220]
            self.lista.addItem(f"v{info.version} — {info.fecha[:10]}\n{notas}")
        self.estado.setText("Seleccione una versión." if versiones else
                            "No hay versiones anteriores publicadas disponibles.")
        if versiones:
            self.lista.setCurrentRow(0)

    def _habilitar(self, *_):
        self.instalar.setEnabled(self.lista.currentRow() >= 0 and
                                (self.reparar or self.confirmacion.text() == "VOLVER"))

    def _aceptar(self):
        self.info = self.versiones[self.lista.currentRow()]
        self.accept()

    def closeEvent(self, event):
        if self.hilo.isRunning():
            self.hide()
            self.hilo.finished.connect(self.close)
            event.ignore()
        else:
            super().closeEvent(event)

    def reject(self):
        if self.hilo.isRunning():
            self.estado.setText("Espere a que termine la consulta para cerrar…")
            return
        super().reject()
