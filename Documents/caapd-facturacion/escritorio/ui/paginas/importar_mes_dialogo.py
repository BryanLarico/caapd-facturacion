"""
ui/paginas/importar_mes_dialogo.py — Modal para importar padrones o lecturas de meses históricos desde Excel.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict, Optional
from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
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
from servicios.importador_mes import importar_mes_desde_excel
from ui.componentes.alerta import AlertaWidget
from ui.componentes.indicador_carga import IndicadorCarga
from ui.hilos import Worker, mostrar_dialogo_error


class DialogoImportarMesExcel(QDialog):
    """Diálogo modal para subir y procesar un archivo Excel de un mes específico."""

    def __init__(self, servicio: ServicioDatos, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.servicio = servicio
        self.thread_pool = QThreadPool.globalInstance()
        self.ruta_archivo_seleccionado: Optional[str] = None

        self.setWindowTitle("Importar Padrón y Lecturas del Mes desde Excel — CAAPD")
        self.setMinimumWidth(540)
        self.setModal(True)

        self._construir_ui()

    def _construir_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Encabezado
        lbl_titulo = QLabel("📥 Importación de Lecturas / Padrón Mensual")
        lbl_titulo.setStyleSheet("font-size: 17px; font-weight: bold; color: #0369a1;")
        layout.addWidget(lbl_titulo)

        lbl_desc = QLabel(
            "Carga archivos Excel (.xlsx) de meses pasados para poblar el historial de consumos "
            "(histograma de recibos) o para restaurar lecturas por contingencia."
        )
        lbl_desc.setStyleSheet("font-size: 13px; color: #475569;")
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)

        # Panel de selección de archivo
        panel_file = QFrame()
        panel_file.setStyleSheet("background: #f8fafc; border: 1.5px dashed #cbd5e1; border-radius: 8px; padding: 14px;")
        layout_file = QVBoxLayout(panel_file)
        layout_file.setSpacing(10)

        fila_sel = QHBoxLayout()
        self.lbl_archivo = QLabel("Ningún archivo seleccionado")
        self.lbl_archivo.setStyleSheet("color: #64748b; font-size: 13px; font-style: italic;")
        fila_sel.addWidget(self.lbl_archivo, stretch=1)

        btn_examinar = QPushButton("📂 Seleccionar Excel (.xlsx)...")
        btn_examinar.setProperty("class", "boton boton_secundario")
        btn_examinar.clicked.connect(self._examinar_archivo)
        fila_sel.addWidget(btn_examinar)
        layout_file.addLayout(fila_sel)

        # Botón para abrir plantilla modelo
        btn_plantilla = QPushButton("📄 Ver / Abrir Plantilla de Excel de Prueba")
        btn_plantilla.setStyleSheet("background: transparent; color: #0284c7; border: none; text-align: left; font-size: 12px; font-weight: bold;")
        btn_plantilla.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_plantilla.clicked.connect(self._abrir_plantilla_modelo)
        layout_file.addWidget(btn_plantilla)

        layout.addWidget(panel_file)

        # Formulario de parámetros
        panel_params = QFrame()
        panel_params.setStyleSheet("background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px;")
        layout_params = QVBoxLayout(panel_params)
        layout_params.setSpacing(12)

        fila_p = QHBoxLayout()
        lbl_p = QLabel("Periodo correspondiente (AAAA-MM):")
        lbl_p.setStyleSheet("font-weight: bold; color: #1e293b;")
        self.input_periodo = QLineEdit()
        self.input_periodo.setPlaceholderText("Ej. 2026-08")
        self.input_periodo.setMaxLength(7)
        self.input_periodo.setFixedWidth(130)
        fila_p.addWidget(lbl_p)
        fila_p.addWidget(self.input_periodo)
        fila_p.addStretch(1)
        layout_params.addLayout(fila_p)

        self.chk_activo = QCheckBox("Establecer como el mes activo del sistema (habilita cobros/lecturas de este mes)")
        self.chk_activo.setStyleSheet("color: #334155; font-size: 13px;")
        layout_params.addWidget(self.chk_activo)

        layout.addWidget(panel_params)

        # Indicador de carga
        self.indicador = IndicadorCarga()
        layout.addWidget(self.indicador)

        # Botones
        fila_btns = QHBoxLayout()
        fila_btns.addStretch(1)

        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setProperty("class", "boton boton_secundario")
        self.btn_cancelar.clicked.connect(self.reject)
        fila_btns.addWidget(self.btn_cancelar)

        self.btn_importar = QPushButton("🚀 Iniciar Importación")
        self.btn_importar.setProperty("class", "boton boton_primario boton_grande")
        self.btn_importar.setEnabled(False)
        self.btn_importar.clicked.connect(self._ejecutar_importacion)
        fila_btns.addWidget(self.btn_importar)

        layout.addLayout(fila_btns)

    def _examinar_archivo(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar archivo Excel de lecturas",
            "",
            "Archivos Excel (*.xlsx *.xls)",
        )
        if ruta:
            self.ruta_archivo_seleccionado = ruta
            nombre = Path(ruta).name
            self.lbl_archivo.setText(f"📄 {nombre}")
            self.lbl_archivo.setStyleSheet("color: #0f172a; font-weight: bold; font-size: 13px;")
            self.btn_importar.setEnabled(True)

    def _abrir_plantilla_modelo(self) -> None:
        p = Path(__file__).resolve().parent.parent.parent / "datos" / "PLANTILLA_IMPORTAR_MES.xlsx"
        if p.exists():
            try:
                os.startfile(str(p))
            except Exception:
                QMessageBox.information(
                    self,
                    "Plantilla de Excel",
                    f"La plantilla modelo se encuentra guardada en:\n\n{p}",
                )
        else:
            QMessageBox.warning(self, "Aviso", f"No se encontró el archivo en:\n{p}")

    def _ejecutar_importacion(self) -> None:
        if not self.ruta_archivo_seleccionado:
            QMessageBox.warning(self, "Atención", "Debe seleccionar un archivo Excel.")
            return

        periodo = self.input_periodo.text().strip()
        if len(periodo) != 7 or "-" not in periodo:
            QMessageBox.warning(self, "Atención", "Debe ingresar un periodo válido en formato AAAA-MM (ej. 2026-08).")
            return

        es_activo = self.chk_activo.isChecked()

        confirm = QMessageBox.question(
            self,
            "Confirmar Importación",
            f"Se importarán las lecturas del archivo Excel para el mes {periodo}.\n\n"
            f"• Archivo: {Path(self.ruta_archivo_seleccionado).name}\n"
            f"• Establecer como mes activo: {'SÍ' if es_activo else 'NO (solo histórico)'}\n\n"
            "¿Desea continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.indicador.iniciar("Procesando Excel y subiendo lecturas a Firestore...")
        self.btn_importar.setEnabled(False)
        self.btn_cancelar.setEnabled(False)

        def tarea() -> Dict[str, Any]:
            return importar_mes_desde_excel(
                ruta_excel=self.ruta_archivo_seleccionado,
                periodo=periodo,
                es_mes_activo=es_activo,
            )

        worker = Worker(tarea)
        worker.signals.resultado.connect(self._al_exito)
        worker.signals.error.connect(self._al_error)
        worker.signals.finalizado.connect(self.indicador.detener)
        self.thread_pool.start(worker)

    def _al_exito(self, res: Dict[str, Any]) -> None:
        p = res.get("periodo")
        u = res.get("usuarios_procesados", 0)
        m = res.get("medidores_procesados", 0)
        n = res.get("usuarios_nuevos_padron", 0)
        QMessageBox.information(
            self,
            "Importación Exitosa",
            f"¡Mes {p} importado correctamente!\n\n"
            f"• Usuarios vinculados: {u}\n"
            f"• Medidores procesados: {m}\n"
            f"• Clientes nuevos agregados al padrón: {n}\n\n"
            "El historial de consumos ha sido actualizado.",
        )
        self.accept()

    def _al_error(self, err: str) -> None:
        mostrar_dialogo_error(self, "Error al importar Excel", err)
        self.btn_importar.setEnabled(True)
        self.btn_cancelar.setEnabled(True)
