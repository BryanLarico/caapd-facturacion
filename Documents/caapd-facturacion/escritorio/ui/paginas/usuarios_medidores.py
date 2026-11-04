import copy
import datetime
import weakref

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

import calculos
import codigos


class FilaMedidor(QFrame):
    def __init__(self, dialogo, datos=None, nuevo=False):
        super().__init__(dialogo)
        self.dialogo = weakref.proxy(dialogo)
        self.original = copy.deepcopy(datos or {})
        self.nuevo = nuevo or not datos or not dialogo.es_edicion
        self.motivo = None
        self.ultimo_numero = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        self.campo_medidor = QLineEdit(str((datos or {}).get('nro_medidor', '')))
        self.campo_medidor.setValidator(QRegularExpressionValidator(
            QRegularExpression(r'\d{0,12}'), self.campo_medidor))
        anterior = int((datos or {}).get('lectura_anterior') or 0)
        actual = (datos or {}).get('lectura_actual')
        self.campo_lectura_anterior = QLineEdit(str(anterior))
        self.campo_lectura_anterior.setReadOnly(True)
        self.campo_lectura_actual = QLineEdit(
            '0' if self.nuevo else (str(int(actual)) if actual is not None else ''))
        self.campo_lectura_actual.setValidator(QRegularExpressionValidator(
            QRegularExpression(r'\d{0,9}'), self.campo_lectura_actual))
        for titulo, campo in (
            ('N° de medidor', self.campo_medidor),
            ('Lectura Anterior', self.campo_lectura_anterior),
            ('Lectura Actual', self.campo_lectura_actual),
        ):
            col = QVBoxLayout()
            col.addWidget(QLabel(titulo))
            col.addWidget(campo)
            layout.addLayout(col, stretch=1)
        self.btn_quitar = QPushButton('−')
        self.btn_quitar.setAutoDefault(False)
        self.btn_quitar.setAccessibleName('Quitar medidor')
        self.btn_quitar.clicked.connect(lambda: self.dialogo._quitar_medidor(self))
        layout.addWidget(self.btn_quitar)
        self.campo_medidor.textChanged.connect(lambda: self.dialogo._validar_formulario(True))
        self.campo_lectura_actual.textChanged.connect(lambda: self.dialogo._validar_lectura_en_vivo())
        self.campo_medidor.editingFinished.connect(self.confirmar_cambio)

    def confirmar_cambio(self):
        DialogoMotivoCambioMedidor = self.dialogo.clase_motivo
        numero = codigos.normalizar_medidor(self.campo_medidor.text())
        anterior = self.original.get('nro_medidor')
        if self.nuevo or not anterior or numero == anterior:
            if numero == anterior and self.motivo:
                self._restaurar_lecturas()
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
            self._restaurar_lecturas()
            self.motivo = None
            self.ultimo_numero = None
            return False
        self.motivo = dlg.motivo_elegido
        self.ultimo_numero = numero
        if self.motivo == DialogoMotivoCambioMedidor.MOTIVO_REINSTALACION:
            self.campo_lectura_anterior.setText('0')
            self.campo_lectura_actual.setText('0')
        else:
            self._restaurar_lecturas()
        self.dialogo._validar_formulario(True)
        return True

    def _restaurar_lecturas(self):
        self.campo_lectura_anterior.setText(str(int(self.original.get('lectura_anterior') or 0)))
        actual = self.original.get('lectura_actual')
        self.campo_lectura_actual.setText(str(int(actual)) if actual is not None else '')

    def datos(self):
        datos = copy.deepcopy(self.original)
        datos['nro_medidor'] = codigos.normalizar_medidor(self.campo_medidor.text())
        datos['lectura_anterior'] = int(self.campo_lectura_anterior.text() or 0)
        texto = self.campo_lectura_actual.text().strip()
        actual = int(texto) if texto else None
        reinstalacion = self.motivo == 'REINSTALACION'
        if reinstalacion:
            datos.update(fecha_anterior=None, consumo_anterior=None, nota='', novedad='CAMBIO_MEDIDOR')
        if self.nuevo or reinstalacion or actual != self.original.get('lectura_actual'):
            datos.update(fecha_lectura=datetime.date.today().isoformat() if actual is not None else None,
                         estado_lectura='LEIDO' if actual is not None else 'PENDIENTE',
                         registrado_por='ADMIN')
        datos['lectura_actual'] = actual
        datos.setdefault('novedad', 'NORMAL')
        if actual is not None:
            datos['consumo'] = calculos.consumo_medidor(
                datos['lectura_anterior'], actual, datos['novedad'])
        return datos
