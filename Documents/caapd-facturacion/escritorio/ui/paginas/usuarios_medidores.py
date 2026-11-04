import copy
import weakref

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLineEdit, QPushButton

import codigos


def medidor_pendiente(numero: str, novedad: str = "NORMAL") -> dict:
    """Medidor sin lecturas: el lector lo leerá desde la pantalla de Lecturas."""
    return {
        "nro_medidor": numero, "lectura_anterior": 0, "lectura_actual": None,
        "fecha_anterior": None, "fecha_lectura": None, "consumo_anterior": None,
        "consumo": None, "estado_lectura": "PENDIENTE", "novedad": novedad, "nota": "",
    }


class FilaMedidor(QFrame):
    """Una fila con el número de medidor y el botón para quitarlo."""

    def __init__(self, dialogo, datos=None, nuevo=False):
        super().__init__(dialogo)
        self.dialogo = weakref.proxy(dialogo)
        self.original = copy.deepcopy(datos or {})
        self.nuevo = nuevo or not datos or not dialogo.es_edicion
        self.motivo = None
        self.ultimo_numero = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        self.campo_medidor = QLineEdit(str((datos or {}).get('nro_medidor', '')))
        self.campo_medidor.setPlaceholderText('N° de medidor')
        self.campo_medidor.setValidator(QRegularExpressionValidator(
            QRegularExpression(r'\d{0,12}'), self.campo_medidor))
        layout.addWidget(self.campo_medidor, stretch=1)
        self.btn_quitar = QPushButton('−')
        self.btn_quitar.setAutoDefault(False)
        self.btn_quitar.setAccessibleName('Quitar medidor')
        self.btn_quitar.setToolTip('Quitar este medidor')
        self.btn_quitar.clicked.connect(lambda: self.dialogo._quitar_medidor(self))
        layout.addWidget(self.btn_quitar)
        self.campo_medidor.textChanged.connect(lambda: self.dialogo._validar_formulario(True))
        self.campo_medidor.editingFinished.connect(self.confirmar_cambio)

    def confirmar_cambio(self):
        DialogoMotivoCambioMedidor = self.dialogo.clase_motivo
        numero = codigos.normalizar_medidor(self.campo_medidor.text())
        anterior = self.original.get('nro_medidor')
        if self.nuevo or not anterior or numero == anterior:
            self.motivo = None
            self.ultimo_numero = None
            return True
        if not self.campo_medidor.text().isdigit():
            return False
        if numero == self.ultimo_numero:
            return True
        valido, _ = self.dialogo.servicio.validar_medidores_unicos(
            [numero], id_usuario_actual=self.dialogo.id_original or None)
        otros = [codigos.normalizar_medidor(f.campo_medidor.text())
                 for f in self.dialogo.filas_medidores if f is not self]
        if not valido or numero in otros:
            return False
        dlg = DialogoMotivoCambioMedidor(anterior, numero, self.parentWidget())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            self.campo_medidor.setText(anterior)
            self.motivo = None
            self.ultimo_numero = None
            return False
        self.motivo = dlg.motivo_elegido
        self.ultimo_numero = numero
        self.dialogo._validar_formulario(True)
        return True

    def datos(self):
        numero = codigos.normalizar_medidor(self.campo_medidor.text())
        if self.nuevo:
            return medidor_pendiente(numero)
        if self.motivo == 'REINSTALACION':
            return medidor_pendiente(numero, novedad='CAMBIO_MEDIDOR')
        datos = copy.deepcopy(self.original)
        datos['nro_medidor'] = numero
        return datos
