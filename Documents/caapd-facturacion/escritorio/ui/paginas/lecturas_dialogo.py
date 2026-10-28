"""
ui/paginas/lecturas_dialogo.py — Diálogo modal para registrar y corregir lecturas de medidor.

Permite:
- Ingreso de lectura actual (número entero).
- Selección de novedad desde el catálogo de config.observaciones.
- Ingreso de nota libre.
- Detección inmediata de alertas: consumo negativo, consumo > 100 m³, consumo > 3x histórico.
- Guardado asíncrono en segundo plano (registrado_por = 'ADMIN').
"""
from __future__ import annotations
from typing import Any, Dict, Optional
from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui import iconos

import calculos
from servicios.datos import ServicioDatos
from ui.componentes.indicador_carga import IndicadorCarga
from ui.hilos import Worker, mostrar_dialogo_error


class DialogoLectura(QDialog):
    """Modal para registrar o editar una lectura de medidor."""

    def __init__(
        self,
        servicio: ServicioDatos,
        periodo: str,
        item: Dict[str, Any],
        config: Dict[str, Any],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.servicio = servicio
        self.periodo = periodo
        self.item = item
        self.config = config
        self.thread_pool = QThreadPool.globalInstance()

        self.setWindowTitle(f"Lectura de Medidor — Conexión {item.get('nro_conexion')}")
        self.setMinimumWidth(480)
        self.setModal(True)

        self._construir_ui()

    def _construir_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # 1. Cabecera con datos del usuario
        lbl_persona = QLabel(str(self.item.get("nombre") or "").upper())
        lbl_persona.setStyleSheet("font-size: 16px; font-weight: bold; color: #0f172a;")
        layout.addWidget(lbl_persona)

        sub_info = (
            f"Conexión: <b>{self.item.get('nro_conexion')}</b> &nbsp;|&nbsp; "
            f"ID: <b>{self.item.get('id_usuario')}</b> &nbsp;|&nbsp; "
            f"Sector: <b>{self.item.get('sector')}</b>"
        )
        lbl_sub = QLabel(sub_info)
        lbl_sub.setStyleSheet("font-size: 13px; color: #475569;")
        layout.addWidget(lbl_sub)

        # 2. Tarjeta resumen del medidor
        card_medidor = QFrame()
        card_medidor.setStyleSheet("background: #f1f5f9; border-radius: 8px; padding: 12px;")
        layout_card = QHBoxLayout(card_medidor)
        layout_card.setContentsMargins(12, 8, 12, 8)

        lbl_med = QLabel(f"Medidor: <b>{self.item.get('nro_medidor')}</b>")
        lbl_med.setStyleSheet("font-size: 13px; color: #0369a1;")
        layout_card.addWidget(lbl_med)

        cat_txt = f"Categoría: <b>{self.item.get('codigo_categoria', 'A')}</b>"
        lbl_cat = QLabel(cat_txt)
        lbl_cat.setStyleSheet("font-size: 13px; color: #475569;")
        layout_card.addWidget(lbl_cat)

        layout.addWidget(card_medidor)

        # 3. Formulario de edición
        panel_inputs = QFrame()
        layout_inputs = QVBoxLayout(panel_inputs)
        layout_inputs.setSpacing(12)

        # Lectura anterior (editable)
        fila_ant = QHBoxLayout()
        lbl_ant = QLabel("Lectura anterior:")
        lbl_ant.setFixedWidth(130)
        lbl_ant.setStyleSheet("font-weight: bold; color: #1e293b;")

        self.input_anterior = QLineEdit()
        self.input_anterior.setPlaceholderText("Ej. 10")
        ant_val = self.item.get("lectura_anterior")
        self.input_anterior.setText(str(ant_val if ant_val is not None else 0))
        self.input_anterior.textChanged.connect(self._recalcular_y_validar)
        fila_ant.addWidget(lbl_ant)
        fila_ant.addWidget(self.input_anterior)
        layout_inputs.addLayout(fila_ant)

        # Lectura actual
        fila_lect = QHBoxLayout()
        lbl_l = QLabel("Lectura actual:")
        lbl_l.setFixedWidth(130)
        lbl_l.setStyleSheet("font-weight: bold; color: #1e293b;")

        self.input_actual = QLineEdit()
        self.input_actual.setPlaceholderText("Ej. 125")
        act_val = self.item.get("lectura_actual")
        if act_val is not None:
            self.input_actual.setText(str(act_val))
        self.input_actual.textChanged.connect(self._recalcular_y_validar)
        fila_lect.addWidget(lbl_l)
        fila_lect.addWidget(self.input_actual)
        layout_inputs.addLayout(fila_lect)

        # Novedad / Observación
        fila_nov = QHBoxLayout()
        lbl_n = QLabel("Novedad:")
        lbl_n.setFixedWidth(130)
        lbl_n.setStyleSheet("font-weight: bold; color: #1e293b;")

        self.combo_novedad = QComboBox()
        self.combo_novedad.setView(QListView())
        # Catálogo desde config.observaciones
        obs_catalogo = self.config.get("observaciones") or [
            {"codigo": "NORMAL", "texto": "Normal"},
            {"codigo": "MEDIDOR_DANADO", "texto": "Medidor dañado"},
            {"codigo": "FUGA", "texto": "Fuga de agua"},
            {"codigo": "CASA_CERRADA", "texto": "Casa cerrada"},
            {"codigo": "LECTURA_ESTIMADA", "texto": "Lectura estimada"},
            {"codigo": "CAMBIO_MEDIDOR", "texto": "Cambio de medidor"},
            {"codigo": "OTRO", "texto": "Otro"},
        ]
        self.combo_novedad.addItem("Normal", "NORMAL")
        for ob in obs_catalogo:
            cod = ob.get("codigo", "")
            txt = ob.get("texto", cod)
            if cod != "NORMAL":
                self.combo_novedad.addItem(txt, cod)

        # Seleccionar valor previo
        nov_prev = str(self.item.get("novedad") or "NORMAL").upper()
        idx_nov = self.combo_novedad.findData(nov_prev)
        if idx_nov >= 0:
            self.combo_novedad.setCurrentIndex(idx_nov)
        self.combo_novedad.currentIndexChanged.connect(self._recalcular_y_validar)
        fila_nov.addWidget(lbl_n)
        fila_nov.addWidget(self.combo_novedad)
        layout_inputs.addLayout(fila_nov)

        # Nota
        fila_nota = QHBoxLayout()
        lbl_nt = QLabel("Nota / Detalle:")
        lbl_nt.setFixedWidth(130)
        lbl_nt.setStyleSheet("font-weight: bold; color: #1e293b;")

        self.input_nota = QLineEdit()
        self.input_nota.setPlaceholderText("Comentario u observación opcional")
        self.input_nota.setText(str(self.item.get("nota") or ""))
        fila_nota.addWidget(lbl_nt)
        fila_nota.addWidget(self.input_nota)
        layout_inputs.addLayout(fila_nota)

        layout.addWidget(panel_inputs)

        # 4. Indicador dinámico de consumo y advertencias
        self.lbl_feedback_consumo = QLabel("")
        self.lbl_feedback_consumo.setStyleSheet("font-size: 13px; font-weight: bold; color: #0284c7;")
        layout.addWidget(self.lbl_feedback_consumo)

        self.lbl_alerta = QLabel("")
        self.lbl_alerta.setWordWrap(True)
        self.lbl_alerta.setStyleSheet("background: #fef3c7; color: #92400e; border: 1px solid #fde68a; border-radius: 6px; padding: 8px; font-size: 12px;")
        self.lbl_alerta.hide()
        layout.addWidget(self.lbl_alerta)

        # 5. Indicador de carga
        self.indicador = IndicadorCarga()
        layout.addWidget(self.indicador)

        # 6. Botones de acción
        fila_btns = QHBoxLayout()
        fila_btns.addStretch(1)

        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setProperty("class", "boton boton_secundario")
        self.btn_cancelar.clicked.connect(self.reject)
        fila_btns.addWidget(self.btn_cancelar)

        self.btn_guardar = QPushButton("Guardar lectura")
        iconos.aplicar(self.btn_guardar, "device-floppy", "blanco")
        self.btn_guardar.setProperty("class", "boton boton_primario")
        self.btn_guardar.clicked.connect(self._ejecutar_guardado)
        fila_btns.addWidget(self.btn_guardar)

        layout.addLayout(fila_btns)

        # Evaluación inicial
        self._recalcular_y_validar()

    def _recalcular_y_validar(self) -> None:
        texto_ant = self.input_anterior.text().strip()
        texto_act = self.input_actual.text().strip()
        nov = self.combo_novedad.currentData() or "NORMAL"

        if not texto_ant or not texto_ant.isdigit():
            self.lbl_feedback_consumo.setText("Lectura anterior no válida (ingrese un número entero).")
            self.lbl_feedback_consumo.setStyleSheet("color: #dc2626;")
            self.lbl_alerta.hide()
            return

        ant = int(texto_ant)

        if not texto_act:
            self.lbl_feedback_consumo.setText("Consumo: —")
            self.lbl_alerta.hide()
            return

        if not texto_act.isdigit():
            self.lbl_feedback_consumo.setText("Lectura actual no válida (ingrese un número entero).")
            self.lbl_feedback_consumo.setStyleSheet("color: #dc2626;")
            self.lbl_alerta.hide()
            return

        act = int(texto_act)
        try:
            c = calculos.consumo_medidor(ant, act, nov)
            self.lbl_feedback_consumo.setText(f"Consumo calculado: {c:.0f} m³")
            self.lbl_feedback_consumo.setStyleSheet("color: #16a34a; font-weight: bold;")
        except ValueError:
            self.lbl_feedback_consumo.setText(f"Consumo negativo: {act - ant} m³")
            self.lbl_feedback_consumo.setStyleSheet("color: #dc2626; font-weight: bold;")
            self.lbl_alerta.setText(
                "La lectura actual es menor que la anterior. "
                "Si el medidor fue reemplazado, seleccione 'Cambio de medidor' en Novedad."
            )
            self.lbl_alerta.show()
            return

        # Validaciones de consumo inusual
        avisos = []
        if c > 100:
            avisos.append("• Consumo inusualmente alto (> 100 m³). Verifique que no sea un error de digitación.")

        hist = self.item.get("historial_m3") or []
        if hist and len(hist) > 0:
            promedio = sum(hist) / len(hist)
            if promedio > 0 and c >= (3 * promedio):
                avisos.append(f"• El consumo triplica el promedio histórico ({promedio:.1f} m³).")

        if avisos:
            self.lbl_alerta.setText("Avisos preventivos:\n" + "\n".join(avisos))
            self.lbl_alerta.show()
        else:
            self.lbl_alerta.hide()

    def _ejecutar_guardado(self) -> None:
        texto_ant = self.input_anterior.text().strip()
        texto_act = self.input_actual.text().strip()
        if not texto_ant or not texto_ant.isdigit():
            QMessageBox.warning(self, "Atención", "Debe ingresar una lectura anterior válida (número entero positivo).")
            return
        if not texto_act or not texto_act.isdigit():
            QMessageBox.warning(self, "Atención", "Debe ingresar una lectura actual válida (número entero positivo).")
            return

        ant = int(texto_ant)
        act = int(texto_act)
        nov = self.combo_novedad.currentData() or "NORMAL"
        nota = self.input_nota.text().strip()

        if act < ant and nov != "CAMBIO_MEDIDOR":
            QMessageBox.critical(
                self,
                "Lectura no válida",
                "La lectura actual no puede ser menor a la lectura anterior "
                "a menos que la novedad sea 'Cambio de medidor'.",
            )
            return

        self.indicador.iniciar("Guardando y recalculando...")
        self.btn_guardar.setEnabled(False)
        self.btn_cancelar.setEnabled(False)

        def tarea() -> Dict[str, Any]:
            return self.servicio.guardar_lectura_medidor(
                periodo=self.periodo,
                id_usuario=str(self.item.get("id_usuario")),
                nro_medidor=str(self.item.get("nro_medidor")),
                lectura_actual=act,
                novedad=nov,
                nota=nota,
                registrado_por="ADMIN",
                lectura_anterior=ant,
            )

        worker = Worker(tarea)
        worker.signals.resultado.connect(self._al_exito)
        worker.signals.error.connect(self._al_error)
        worker.signals.finalizado.connect(self.indicador.detener)
        self.thread_pool.start(worker)

    def _al_exito(self, res: Dict[str, Any]) -> None:
        if hasattr(self, "item") and isinstance(self.item, dict):
            texto_ant = self.input_anterior.text().strip()
            texto_act = self.input_actual.text().strip()
            if texto_ant.isdigit():
                self.item["lectura_anterior"] = int(texto_ant)
            if texto_act.isdigit():
                self.item["lectura_actual"] = int(texto_act)
        self.accept()

    def _al_error(self, err_msg: str) -> None:
        mostrar_dialogo_error(self, "Error al guardar lectura", err_msg)
        self.btn_guardar.setEnabled(True)
        self.btn_cancelar.setEnabled(True)
