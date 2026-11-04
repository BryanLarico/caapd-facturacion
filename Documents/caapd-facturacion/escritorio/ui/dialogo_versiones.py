"""Opciones de reparación y retorno de versión."""
from PySide6.QtCore import QThread, Signal
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
        self.resize(620, 380)
        layout = QVBoxLayout(self)
        self.estado = QLabel("Consultando versiones publicadas…")
        self.estado.setWordWrap(True)
        layout.addWidget(self.estado)
        aviso = QLabel(
            "Se reinstalará el programa sin modificar sus datos." if reparar else
            "Advertencia: una versión anterior puede no ser compatible con sus datos actuales. "
            "Haga un respaldo antes de continuar. Escriba VOLVER para confirmar.")
        aviso.setWordWrap(True)
        layout.addWidget(aviso)
        self.lista = QListWidget()
        layout.addWidget(self.lista)
        self.confirmacion = QLineEdit()
        self.confirmacion.setPlaceholderText("VOLVER")
        self.confirmacion.setVisible(not reparar)
        layout.addWidget(self.confirmacion)
        self.instalar = QPushButton("Reparar ahora" if reparar else "Instalar versión anterior")
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
        self.estado.setText(f"No se pudieron consultar las versiones. Intente más tarde.\n{mensaje}")

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
