"""
ui/paginas/asistente_recibos.py — Asistente modal "Emitir recibos del mes" (Fusión Recibos + Cobros).

Asistente guiado de 3 pasos para la revisión, estimación y generación masiva de recibos:
Paso 1: Revisión de faltantes y estimación de lecturas pendientes.
Paso 2: Generación en segundo plano con barra de progreso idempotente.
Paso 3: Resultados finales, resumen de facturación y acceso a ZIP y PDFs.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QThreadPool, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui import iconos

import rutas
from servicios.datos import ServicioDatos
from ui.hilos import Worker, mostrar_dialogo_error


class DialogoAsistenteEmitirRecibos(QDialog):
    """Diálogo modal guiado en 3 pasos para emitir recibos del mes."""

    recibos_emitidos = Signal()

    def __init__(self, servicio_datos: ServicioDatos, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.servicio = servicio_datos
        self.thread_pool = QThreadPool.globalInstance()

        self.setWindowTitle("Asistente — Emitir Recibos del Mes")
        self.resize(780, 540)
        self.setMinimumSize(680, 480)

        # Cargar info actual del mes
        cfg = self.servicio.cargar_config()
        self.periodo = cfg.get("mes_actual", {}).get("periodo") or "2026-10"
        self.info_estado = self.servicio.verificar_estado_generacion_recibos(
            self.periodo)

        self._construir_ui()
        self._cargar_paso_1()

    def _construir_ui(self) -> None:
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(24, 20, 24, 20)
        layout_principal.setSpacing(16)

        # Encabezado con indicador de pasos
        self.lbl_pasos = QLabel(
            "PASO 1 DE 3: Revisión de Lecturas y Faltantes")
        self.lbl_pasos.setStyleSheet(
            "color: #0369a1; font-weight: bold; font-size: 13px; text-transform: uppercase;")
        layout_principal.addWidget(self.lbl_pasos)

        # Contenedor apilado de pasos
        self.stacked_pasos = QStackedWidget()
        layout_principal.addWidget(self.stacked_pasos, stretch=1)

        # Paso 1: Revisión y Faltantes
        self.widget_paso1 = self._crear_widget_paso1()
        self.stacked_pasos.addWidget(self.widget_paso1)

        # Paso 2: Progreso de Generación
        self.widget_paso2 = self._crear_widget_paso2()
        self.stacked_pasos.addWidget(self.widget_paso2)

        # Paso 3: Resultados y Acceso a Documentos
        self.widget_paso3 = self._crear_widget_paso3()
        self.stacked_pasos.addWidget(self.widget_paso3)

        # Barra inferior de botones de navegación
        self.fila_botones = QHBoxLayout()
        self.fila_botones.setSpacing(12)

        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setProperty("class", "boton boton_secundario")
        self.btn_cancelar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancelar.clicked.connect(self.reject)
        self.fila_botones.addWidget(self.btn_cancelar)

        self.fila_botones.addStretch(1)

        self.btn_siguiente = QPushButton("Continuar a Generación →")
        self.btn_siguiente.setProperty(
            "class", "boton boton_primario boton_grande")
        self.btn_siguiente.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_siguiente.clicked.connect(self._avanzar_paso_2)
        self.fila_botones.addWidget(self.btn_siguiente)

        layout_principal.addLayout(self.fila_botones)

    # -----------------------------------------------------------------------
    # PASO 1: Revisión y Faltantes
    # -----------------------------------------------------------------------
    def _crear_widget_paso1(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        # Tarjeta informativa
        self.card_info_paso1 = QFrame()
        self.card_info_paso1.setStyleSheet("""
            QFrame {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 14px;
            }
        """)
        lay_card = QVBoxLayout(self.card_info_paso1)
        lay_card.setSpacing(6)

        self.lbl_titulo_paso1 = QLabel(
            f"Facturación para el Periodo: <b>{self.periodo}</b>")
        self.lbl_titulo_paso1.setStyleSheet("font-size: 15px; color: #0f172a;")
        lay_card.addWidget(self.lbl_titulo_paso1)

        self.lbl_resumen_lecturas = QLabel(
            "Verificando lecturas registradas...")
        self.lbl_resumen_lecturas.setStyleSheet(
            "font-size: 13px; color: #475569;")
        lay_card.addWidget(self.lbl_resumen_lecturas)

        lay.addWidget(self.card_info_paso1)

        # Banner de estado (verde si todo completo, amarillo si hay faltantes)
        self.banner_faltantes = QFrame()
        self.banner_faltantes.setStyleSheet("""
            QFrame {
                background-color: #fef3c7;
                border: 1px solid #fde68a;
                border-radius: 6px;
                padding: 10px 14px;
            }
        """)
        lay_banner = QHBoxLayout(self.banner_faltantes)
        self.lbl_banner_faltantes = QLabel(
            "Existen conexiones con lecturas pendientes.")
        self.lbl_banner_faltantes.setStyleSheet(
            "color: #92400e; font-size: 13px; font-weight: 500;")
        lay_banner.addWidget(self.lbl_banner_faltantes)
        lay.addWidget(self.banner_faltantes)

        # Tabla de faltantes
        self.tabla_faltantes = QTableWidget()
        self.tabla_faltantes.setColumnCount(5)
        self.tabla_faltantes.setHorizontalHeaderLabels([
            "CONEXIÓN", "TITULAR", "SECTOR", "MEDIDOR", "LECT. ANTERIOR"
        ])
        self.tabla_faltantes.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self.tabla_faltantes.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_faltantes.setAlternatingRowColors(True)
        lay.addWidget(self.tabla_faltantes, stretch=1)

        # Barra de acciones para resolver faltantes
        self.fila_acciones_faltantes = QHBoxLayout()
        self.fila_acciones_faltantes.setSpacing(10)

        self.btn_estimar_todos = QPushButton(
            "Estimar faltantes con lectura anterior (Consumo 0 m³)")
        iconos.aplicar(self.btn_estimar_todos, "bolt")
        self.btn_estimar_todos.setProperty("class", "boton boton_secundario")
        self.btn_estimar_todos.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_estimar_todos.clicked.connect(
            self._estimar_faltantes_automatico)
        self.fila_acciones_faltantes.addWidget(self.btn_estimar_todos)

        self.fila_acciones_faltantes.addStretch(1)
        lay.addLayout(self.fila_acciones_faltantes)

        return w

    def _cargar_paso_1(self) -> None:
        """Actualiza la vista del paso 1 con los datos de faltantes."""
        self.info_estado = self.servicio.verificar_estado_generacion_recibos(
            self.periodo)
        faltantes = self.info_estado.get("faltantes") or []
        tot_usr = self.info_estado.get("total_usuarios", 0)

        self.lbl_resumen_lecturas.setText(
            f"Total conexiones: {tot_usr} | "
            f"Lecturas completas: {tot_usr - len(faltantes)} | "
            f"Pendientes: {len(faltantes)}"
        )

        if len(faltantes) == 0:
            self.banner_faltantes.setStyleSheet("""
                QFrame {
                    background-color: #dcfce7;
                    border: 1px solid #bbf7d0;
                    border-radius: 6px;
                    padding: 10px 14px;
                }
            """)
            self.lbl_banner_faltantes.setText(
                "✓ Todas las lecturas están completas. Listo para generar recibos.")
            self.lbl_banner_faltantes.setStyleSheet(
                "color: #166534; font-size: 13px; font-weight: bold;")
            self.tabla_faltantes.hide()
            self.fila_acciones_faltantes.setEnabled(False)
            self.btn_siguiente.setEnabled(True)
            self.btn_siguiente.setText("Emitir Recibos Masivos →")
        else:
            self.banner_faltantes.setStyleSheet("""
                QFrame {
                    background-color: #fef3c7;
                    border: 1px solid #fde68a;
                    border-radius: 6px;
                    padding: 10px 14px;
                }
            """)
            self.lbl_banner_faltantes.setText(
                f"Hay {len(faltantes)} medidor(es) pendientes. Puedes estimarlos antes de continuar.")
            self.lbl_banner_faltantes.setStyleSheet(
                "color: #92400e; font-size: 13px; font-weight: 500;")
            self.tabla_faltantes.show()
            self.fila_acciones_faltantes.setEnabled(True)

            self.tabla_faltantes.setRowCount(len(faltantes))
            for r, item in enumerate(faltantes):
                con_str = str(item.get("nro_conexion") or "").zfill(6)
                self.tabla_faltantes.setItem(r, 0, QTableWidgetItem(con_str))
                self.tabla_faltantes.setItem(
                    r, 1, QTableWidgetItem(item.get("nombre") or ""))
                self.tabla_faltantes.setItem(
                    r, 2, QTableWidgetItem(item.get("sector") or ""))
                self.tabla_faltantes.setItem(r, 3, QTableWidgetItem(
                    str(item.get("nro_medidor") or "")))
                self.tabla_faltantes.setItem(r, 4, QTableWidgetItem(
                    str(item.get("lectura_anterior") or 0)))

            self.btn_siguiente.setEnabled(True)
            self.btn_siguiente.setText("Continuar con Estimación →")

    def _estimar_faltantes_automatico(self) -> None:
        """Estima las lecturas pendientes con la lectura anterior."""
        faltantes = self.info_estado.get("faltantes") or []
        if not faltantes:
            return

        for item in faltantes:
            uid = item.get("id_usuario")
            n_med = item.get("nro_medidor")
            l_ant = item.get("lectura_anterior", 0)
            self.servicio.guardar_lectura_medidor(
                periodo=self.periodo,
                id_usuario=uid,
                nro_medidor=n_med,
                lectura_actual=l_ant,
                novedad="ESTIMADO",
                nota="Estimado automáticamente (consumo 0 m³)",
                registrado_por="ADMIN",
            )

        self._cargar_paso_1()
        QMessageBox.information(
            self,
            "Estimación Completada",
            f"Se estimaron exitosamente {len(faltantes)} lecturas pendientes con consumo 0 m³.",
        )

    # -----------------------------------------------------------------------
    # PASO 2: Progreso de Generación Masiva
    # -----------------------------------------------------------------------
    def _crear_widget_paso2(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20, 40, 20, 20)
        lay.setSpacing(20)

        lbl_icono = iconos.etiqueta("receipt", "primario", 56)
        lay.addWidget(lbl_icono, alignment=Qt.AlignmentFlag.AlignCenter)

        self.lbl_estado_paso2 = QLabel("Generando recibos del mes...")
        self.lbl_estado_paso2.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #0f172a;")
        self.lbl_estado_paso2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.lbl_estado_paso2)

        self.barra_progreso = QProgressBar()
        self.barra_progreso.setRange(0, 100)
        self.barra_progreso.setValue(0)
        self.barra_progreso.setTextVisible(True)
        self.barra_progreso.setStyleSheet("""
            QProgressBar {
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                height: 24px;
                text-align: center;
                font-weight: bold;
                background-color: #f1f5f9;
            }
            QProgressBar::chunk {
                background-color: #0284c7;
                border-radius: 7px;
            }
        """)
        lay.addWidget(self.barra_progreso)

        self.lbl_detalle_paso2 = QLabel(
            "Calculando tarifas, correlativos y deudas...")
        self.lbl_detalle_paso2.setStyleSheet(
            "color: #64748b; font-size: 13px;")
        self.lbl_detalle_paso2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.lbl_detalle_paso2)

        lay.addStretch(1)
        return w

    def _avanzar_paso_2(self) -> None:
        """Pasa al paso 2 y dispara la generación de recibos en hilo de fondo."""
        faltantes = self.info_estado.get("faltantes") or []
        if len(faltantes) > 0:
            resp = QMessageBox.question(
                self,
                "Lecturas Pendientes",
                f"Aún hay {len(faltantes)} lecturas pendientes.\n\n"
                "¿Deseas estimarlas automáticamente con consumo 0 m³ y emitir los recibos ahora?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if resp != QMessageBox.StandardButton.Yes:
                return
            for item in faltantes:
                self.servicio.guardar_lectura_medidor(
                    periodo=self.periodo,
                    id_usuario=item.get("id_usuario"),
                    nro_medidor=item.get("nro_medidor"),
                    lectura_actual=item.get("lectura_anterior", 0),
                    novedad="ESTIMADO",
                    nota="Estimado automáticamente",
                    registrado_por="ADMIN",
                )

        self.lbl_pasos.setText("PASO 2 DE 3: Generación Masiva en Curso")
        self.stacked_pasos.setCurrentIndex(1)
        self.btn_cancelar.setEnabled(False)
        self.btn_siguiente.setEnabled(False)

        def progreso_cb(actual: int, total: int) -> None:
            pct = int((actual / max(total, 1)) * 100)
            self.barra_progreso.setValue(pct)
            self.lbl_detalle_paso2.setText(
                f"Procesando recibo {actual} de {total}...")

        def tarea():
            return self.servicio.generar_recibos_mes(self.periodo, callback_progreso=progreso_cb)

        worker = Worker(tarea)
        worker.signals.resultado.connect(self._al_finalizar_generacion)
        worker.signals.error.connect(self._al_fallar_generacion)
        self.thread_pool.start(worker)

    def _al_finalizar_generacion(self, res: Any) -> None:
        self.recibos_emitidos.emit()
        self._cargar_paso_3(res)

    def _al_fallar_generacion(self, err: str) -> None:
        self.btn_cancelar.setEnabled(True)
        mostrar_dialogo_error(self, "Error al generar recibos", err)

    # -----------------------------------------------------------------------
    # PASO 3: Resultados y Acceso a Documentos
    # -----------------------------------------------------------------------
    def _crear_widget_paso3(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(18)

        lbl_exito = iconos.etiqueta("confetti", "exito", 56)
        lay.addWidget(lbl_exito, alignment=Qt.AlignmentFlag.AlignCenter)

        self.lbl_titulo_paso3 = QLabel("¡Recibos emitidos exitosamente!")
        self.lbl_titulo_paso3.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #15803d;")
        self.lbl_titulo_paso3.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.lbl_titulo_paso3)

        # Tarjeta de resumen
        card_resumen = QFrame()
        card_resumen.setStyleSheet("""
            QFrame {
                background-color: #f0fdf4;
                border: 1px solid #bbf7d0;
                border-radius: 8px;
                padding: 16px;
            }
        """)
        lay_res = QVBoxLayout(card_resumen)
        lay_res.setSpacing(8)

        self.lbl_resumen_totales = QLabel(
            "Recibos generados: — | Total facturado: S/. —")
        self.lbl_resumen_totales.setStyleSheet(
            "font-size: 14px; font-weight: 500; color: #166534;")
        self.lbl_resumen_totales.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay_res.addWidget(self.lbl_resumen_totales)

        self.lbl_resumen_estado = QLabel(
            f"El periodo {self.periodo} ha pasado a estado FACTURADO.")
        self.lbl_resumen_estado.setStyleSheet(
            "font-size: 13px; color: #475569;")
        self.lbl_resumen_estado.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay_res.addWidget(self.lbl_resumen_estado)

        lay.addWidget(card_resumen)

        # Botones de descarga y carpetas
        fila_docs = QHBoxLayout()
        fila_docs.setSpacing(14)

        btn_zip = QPushButton("Descargar ZIP de Recibos")
        iconos.aplicar(btn_zip, "file-zip", "blanco")
        btn_zip.setProperty("class", "boton boton_primario")
        btn_zip.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_zip.clicked.connect(self._descargar_zip_completo)
        fila_docs.addWidget(btn_zip)

        btn_carpeta = QPushButton("Abrir Carpeta de Recibos")
        iconos.aplicar(btn_carpeta, "folder-open")
        btn_carpeta.setProperty("class", "boton boton_secundario")
        btn_carpeta.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_carpeta.clicked.connect(self._abrir_carpeta_recibos)
        fila_docs.addWidget(btn_carpeta)

        lay.addLayout(fila_docs)
        lay.addStretch(1)

        return w

    def _cargar_paso_3(self, res: Any) -> None:
        self.lbl_pasos.setText("PASO 3 DE 3: Emisión Completada")
        self.stacked_pasos.setCurrentIndex(2)

        st = self.servicio.verificar_estado_generacion_recibos(self.periodo)
        tot_gen = st.get("recibos_generados", 0)
        tot_fac = st.get("total_facturado", 0.0)

        self.lbl_resumen_totales.setText(
            f"Recibos generados: {tot_gen} | Total facturado: S/. {tot_fac:,.2f}"
        )

        self.btn_cancelar.hide()
        self.btn_siguiente.setEnabled(True)
        self.btn_siguiente.setText("Cerrar y Volver a Cobros")
        self.btn_siguiente.clicked.disconnect()
        self.btn_siguiente.clicked.connect(self.accept)

    def _descargar_zip_completo(self) -> None:
        ruta_zip = self.servicio.generar_zip_recibos(self.periodo)
        if ruta_zip and Path(ruta_zip).exists():
            QMessageBox.information(
                self,
                "Archivo ZIP Generado",
                f"Se empaquetaron todos los recibos en:\n\n{ruta_zip}",
            )
        else:
            QMessageBox.warning(
                self, "Aviso", "No se encontraron recibos generados para empaquetar.")

    def _abrir_carpeta_recibos(self) -> None:
        dir_recibos = rutas.ruta_recibos(self.periodo)
        os.startfile(str(dir_recibos))
