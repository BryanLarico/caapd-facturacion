"""
ui/paginas/mes_dialogo.py — Diálogo modal para abrir un nuevo mes operativo.

Verifica:
1. Si ya existe un mes en curso activo (ABIERTO o CERRADO) -> bloquea la apertura.
2. Si ya existe una base (colección) en Firestore para el periodo ingresado -> bloquea la duplicación.
3. Permite configurar fechas de emisión y vencimiento.
4. Genera los documentos en segundo plano sin congelar la interfaz.
"""
from __future__ import annotations
import datetime
from typing import Any, Dict, Optional
from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
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
from ui.componentes.alerta import AlertaWidget
from ui.componentes.indicador_carga import IndicadorCarga
from ui.hilos import Worker, mostrar_dialogo_error


class DialogoAbrirMes(QDialog):
    """Diálogo modal para abrir un mes nuevo con validación rigurosa de base existente."""

    def __init__(self, servicio: ServicioDatos, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.servicio = servicio
        self.thread_pool = QThreadPool.globalInstance()
        self.periodo_final: Optional[str] = None

        self.setWindowTitle("Abrir nuevo mes operativo — CAAPD Ispacas")
        self.setMinimumWidth(520)
        self.setModal(True)

        self._construir_ui()
        self._verificar_estado_inicial()

    def _construir_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        # Encabezado
        lbl_titulo = QLabel("📅 Apertura de Mes Operativo")
        lbl_titulo.setStyleSheet("font-size: 18px; font-weight: bold; color: #0f172a;")
        lbl_sub = QLabel(
            "Crea la base de lecturas para todos los usuarios activos y habilita el registro de consumo."
        )
        lbl_sub.setStyleSheet("font-size: 13px; color: #64748b;")
        lbl_sub.setWordWrap(True)

        layout.addWidget(lbl_titulo)
        layout.addWidget(lbl_sub)

        # Alerta de validación (estado o existencia)
        self.alerta_estado = AlertaWidget(mensaje="", tipo="aviso", cerrable=False)
        self.alerta_estado.hide()
        layout.addWidget(self.alerta_estado)

        # Formulario de datos
        self.panel_form = QFrame()
        self.panel_form.setObjectName("panel_formulario_mes")
        self.panel_form.setStyleSheet("background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px;")
        layout_form = QVBoxLayout(self.panel_form)
        layout_form.setSpacing(14)

        # Campo: Periodo (AAAA-MM)
        fila_periodo = QHBoxLayout()
        lbl_p = QLabel("Periodo (Año-Mes):")
        lbl_p.setFixedWidth(150)
        lbl_p.setStyleSheet("font-weight: bold; color: #1e293b;")

        self.input_periodo = QLineEdit()
        self.input_periodo.setPlaceholderText("Ej. 2026-10")
        self.input_periodo.setMaxLength(7)
        self.input_periodo.textChanged.connect(self._al_cambiar_periodo)

        fila_periodo.addWidget(lbl_p)
        fila_periodo.addWidget(self.input_periodo)
        layout_form.addLayout(fila_periodo)

        # Alerta inline de periodo
        self.lbl_alerta_periodo = QLabel("")
        self.lbl_alerta_periodo.setStyleSheet("color: #b91c1c; font-size: 12px; font-weight: 500;")
        self.lbl_alerta_periodo.hide()
        layout_form.addWidget(self.lbl_alerta_periodo)

        # Campo: Fecha Emisión
        fila_emision = QHBoxLayout()
        lbl_e = QLabel("Fecha de emisión:")
        lbl_e.setFixedWidth(150)
        lbl_e.setStyleSheet("font-weight: bold; color: #1e293b;")

        self.date_emision = QDateEdit()
        self.date_emision.setCalendarPopup(True)
        self.date_emision.setDisplayFormat("yyyy-MM-dd")
        hoy = datetime.date.today()
        self.date_emision.setDate(hoy)
        self.date_emision.dateChanged.connect(self._al_cambiar_fecha_emision)

        fila_emision.addWidget(lbl_e)
        fila_emision.addWidget(self.date_emision)
        layout_form.addLayout(fila_emision)

        # Campo: Fecha Vencimiento
        fila_venc = QHBoxLayout()
        lbl_v = QLabel("Fecha de vencimiento:")
        lbl_v.setFixedWidth(150)
        lbl_v.setStyleSheet("font-weight: bold; color: #1e293b;")

        self.date_vencimiento = QDateEdit()
        self.date_vencimiento.setCalendarPopup(True)
        self.date_vencimiento.setDisplayFormat("yyyy-MM-dd")
        dias_venc = 15
        self.date_vencimiento.setDate(hoy + datetime.timedelta(days=dias_venc))

        fila_venc.addWidget(lbl_v)
        fila_venc.addWidget(self.date_vencimiento)
        layout_form.addLayout(fila_venc)

        # Nota informativa
        lbl_info = QLabel("💡 Las lecturas anteriores se copiarán del mes pasado o de la semilla inicial.")
        lbl_info.setStyleSheet("font-size: 12px; color: #0369a1; font-style: italic;")
        layout_form.addWidget(lbl_info)

        layout.addWidget(self.panel_form)

        # Indicador de carga
        self.indicador = IndicadorCarga()
        layout.addWidget(self.indicador)

        # Botones de acción
        fila_botones = QHBoxLayout()
        fila_botones.addStretch(1)

        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setProperty("class", "boton boton_secundario")
        self.btn_cancelar.clicked.connect(self.reject)
        fila_botones.addWidget(self.btn_cancelar)

        self.btn_abrir = QPushButton("🚀 Abrir mes ahora")
        self.btn_abrir.setProperty("class", "boton boton_exito boton_grande")
        self.btn_abrir.clicked.connect(self._ejecutar_apertura)
        fila_botones.addWidget(self.btn_abrir)

        layout.addLayout(fila_botones)

    def _verificar_estado_inicial(self) -> None:
        """Verifica si el sistema permite abrir un nuevo mes."""
        puede, motivo, periodo_sug = self.servicio.verificar_puede_abrir_mes()

        if not puede:
            self.alerta_estado.set_mensaje(motivo, "peligro")
            self.alerta_estado.show()
            self.panel_form.setEnabled(False)
            self.btn_abrir.setEnabled(False)
            self.btn_abrir.setToolTip(motivo)
        else:
            self.input_periodo.setText(periodo_sug)
            self.btn_abrir.setEnabled(True)

    def _al_cambiar_periodo(self, texto: str) -> None:
        """Valida dinámicamente si el periodo ingresado ya existe como base."""
        periodo = texto.strip()
        if len(periodo) == 7:  # Formato AAAA-MM
            disponible, motivo = self.servicio.verificar_periodo_disponible(periodo)
            if not disponible:
                self.lbl_alerta_periodo.setText(motivo)
                self.lbl_alerta_periodo.show()
                self.input_periodo.setStyleSheet("border: 2px solid #ef4444; color: #b91c1c;")
                self.btn_abrir.setEnabled(False)
            else:
                self.lbl_alerta_periodo.hide()
                self.input_periodo.setStyleSheet("")
                self.btn_abrir.setEnabled(True)
        else:
            self.lbl_alerta_periodo.hide()
            self.input_periodo.setStyleSheet("")

    def _al_cambiar_fecha_emision(self) -> None:
        """Ajusta fecha de vencimiento sumando días de configuración."""
        emision_qdate = self.date_emision.date()
        fecha_py = datetime.date(emision_qdate.year(), emision_qdate.month(), emision_qdate.day())
        cfg = self.servicio.cargar_config()
        dias = cfg.get("dias_vencimiento", 15)
        self.date_vencimiento.setDate(fecha_py + datetime.timedelta(days=dias))

    def _ejecutar_apertura(self) -> None:
        periodo = self.input_periodo.text().strip()
        if not periodo:
            QMessageBox.warning(self, "Atención", "Debes ingresar un periodo válido (ej. 2026-10).")
            return

        # Validación estricta final de base existente
        disponible, motivo = self.servicio.verificar_periodo_disponible(periodo)
        if not disponible:
            QMessageBox.critical(self, "No se puede abrir el mes", motivo)
            return

        fecha_emision = self.date_emision.date().toString("yyyy-MM-dd")
        fecha_vencimiento = self.date_vencimiento.date().toString("yyyy-MM-dd")

        confirmacion = QMessageBox.question(
            self,
            "Confirmar apertura de mes",
            f"¿Estás seguro de abrir el mes operativo {periodo}?\n\n"
            f"• Fecha de emisión: {fecha_emision}\n"
            f"• Fecha de vencimiento: {fecha_vencimiento}\n\n"
            f"Esta acción creará la colección de lecturas para todos los usuarios activos.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if confirmacion != QMessageBox.StandardButton.Yes:
            return

        self.indicador.iniciar("Creando base del mes y vinculando usuarios...")
        self.btn_abrir.setEnabled(False)
        self.btn_cancelar.setEnabled(False)
        self.panel_form.setEnabled(False)

        def tarea() -> Dict[str, Any]:
            return self.servicio.abrir_mes(
                periodo=periodo,
                fecha_emision=fecha_emision,
                fecha_vencimiento=fecha_vencimiento,
            )

        worker = Worker(tarea)
        worker.signals.resultado.connect(self._al_exito_apertura)
        worker.signals.error.connect(self._al_error_apertura)
        worker.signals.finalizado.connect(self._al_finalizar_tarea)
        self.thread_pool.start(worker)

    def _al_exito_apertura(self, resultado: Dict[str, Any]) -> None:
        self.periodo_final = resultado.get("periodo")
        total = resultado.get("usuarios_creados", 0)
        QMessageBox.information(
            self,
            "Mes abierto con éxito",
            f"¡El mes {self.periodo_final} fue abierto correctamente!\n\n"
            f"Se registraron {total} usuarios en la nueva base de lecturas.\n"
            f"La app móvil de los lectores ahora puede registrar lecturas.",
        )
        self.accept()

    def _al_error_apertura(self, err_msg: str) -> None:
        mostrar_dialogo_error(self, "Error al abrir mes", err_msg)
        self.btn_abrir.setEnabled(True)
        self.btn_cancelar.setEnabled(True)
        self.panel_form.setEnabled(True)

    def _al_finalizar_tarea(self) -> None:
        self.indicador.detener()
