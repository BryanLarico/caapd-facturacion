"""
ui/paginas/configuracion.py — Pantalla de Configuración del Sistema (Fase 6).

Permite visualizar y editar:
1. Datos institucionales del Comité (empresa, resolución, teléfonos, dirección).
2. Tarifas por categoría (A, B, C) con soporte para modo tramos y tarifas planas.
3. Parámetros tributarios (IGV) y políticas de morosidad.
4. Sectores / barrios de la comunidad.
5. Catálogo de observaciones y novedades de medidores para la App y la PC.
6. Gestión de respaldos Excel y contingencia.
"""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QThreadPool, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import respaldo
from servicios.datos import ServicioDatos
from ui.componentes.alerta import AlertaWidget
from ui.componentes.indicador_carga import IndicadorCarga
from ui.hilos import Worker, mostrar_dialogo_error


class PaginaConfiguracion(QWidget):
    """Pantalla completa de Configuración del Sistema CAAPD Ispacas."""

    def __init__(
        self,
        servicio_datos: Optional[ServicioDatos] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.servicio = servicio_datos
        self.thread_pool = QThreadPool.globalInstance()

        self.config_actual: Dict[str, Any] = {}
        self.config_cargada: bool = False
        self._worker = None

        self._construir_ui()

    def _construir_ui(self) -> None:
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(28, 20, 28, 20)
        layout_principal.setSpacing(14)

        # 1. Encabezado de la página
        fila_encabezado = QHBoxLayout()
        fila_encabezado.setSpacing(12)

        col_titulos = QVBoxLayout()
        col_titulos.setSpacing(4)
        lbl_titulo = QLabel("Configuración del Sistema")
        lbl_titulo.setObjectName("encabezado_titulo")
        col_titulos.addWidget(lbl_titulo)

        lbl_subtitulo = QLabel(
            "Tarifas de agua, cargo fijo, IGV, sectores, catálogo de novedades y parámetros generales"
        )
        lbl_subtitulo.setObjectName("encabezado_subtitulo")
        col_titulos.addWidget(lbl_subtitulo)
        fila_encabezado.addLayout(col_titulos)

        fila_encabezado.addStretch(1)

        # Indicador de carga
        self.indicador_carga = IndicadorCarga()
        fila_encabezado.addWidget(self.indicador_carga)

        # Botón Recargar
        self.btn_recargar = QPushButton("🔄 Recargar")
        self.btn_recargar.setProperty("class", "boton boton_secundario")
        self.btn_recargar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_recargar.clicked.connect(lambda: self.cargar_datos_asincrono(forzar=True))
        fila_encabezado.addWidget(self.btn_recargar)

        # Botón Guardar
        self.btn_guardar = QPushButton("💾 Guardar Configuración")
        self.btn_guardar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_guardar.setStyleSheet("""
            QPushButton {
                background-color: #0369a1; color: #ffffff;
                font-weight: bold; font-size: 13px;
                padding: 8px 18px; border-radius: 6px;
            }
            QPushButton:hover { background-color: #0284c7; }
            QPushButton:disabled { background-color: #94a3b8; }
        """)
        self.btn_guardar.clicked.connect(self._accion_guardar_configuracion)
        fila_encabezado.addWidget(self.btn_guardar)

        layout_principal.addLayout(fila_encabezado)

        # Alerta Flash
        self.alerta_flash = AlertaWidget("", tipo="exito", cerrable=True)
        self.alerta_flash.hide()
        layout_principal.addWidget(self.alerta_flash)

        # 2. Pestañas de Configuración (QTabWidget)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                background-color: #ffffff;
                top: -1px;
            }
            QTabBar::tab {
                background-color: #f1f5f9;
                color: #475569;
                font-weight: bold;
                font-size: 13px;
                padding: 10px 18px;
                margin-right: 4px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                border: 1px solid #cbd5e1;
                border-bottom: none;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                color: #0369a1;
                border-bottom: 2px solid #ffffff;
            }
            QTabBar::tab:hover:!selected {
                background-color: #e2e8f0;
            }
        """)

        # Los campos institucionales (empresa) se conservan internamente
        # pero la pestaña no se añade a la interfaz visual (Etapa 1.2)
        self.widget_tab_empresa = self._crear_tab_empresa()

        # Pestaña 1: Tarifas y Categorías
        self.tabs.addTab(self._crear_tab_tarifas(), "💧 Tarifas y Categorías")

        # Pestaña 2: Impuestos y Mora
        self.tabs.addTab(self._crear_tab_impuestos(), "💰 Impuestos (IGV) y Mora")

        # Pestaña 3: Sectores
        self.tabs.addTab(self._crear_tab_sectores(), "📍 Sectores / Barrios")

        # Pestaña 4: Observaciones de Medidor
        self.tabs.addTab(self._crear_tab_observaciones(), "📋 Catálogo de Novedades")

        # Pestaña 5: Respaldo y Contingencia
        self.tabs.addTab(self._crear_tab_respaldo(), "📦 Respaldo y Contingencia")

        layout_principal.addWidget(self.tabs, stretch=1)

    # -----------------------------------------------------------------------
    # TAB 1: DATOS INSTITUCIONALES DEL COMITÉ
    # -----------------------------------------------------------------------
    def _crear_tab_empresa(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        contenido = QWidget()
        lay = QVBoxLayout(contenido)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(16)

        grp_comite = QGroupBox("Datos Institucionales de la Entidad Emisora")
        grp_comite.setStyleSheet("font-weight: bold; color: #0f172a;")
        f_lay = QFormLayout(grp_comite)
        f_lay.setContentsMargins(16, 20, 16, 20)
        f_lay.setSpacing(12)
        f_lay.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.txt_empresa_nombre = QLineEdit()
        self.txt_empresa_nombre.setPlaceholderText("Nombre completo del comité de agua")
        f_lay.addRow("Nombre del Comité:", self.txt_empresa_nombre)

        self.txt_empresa_resolucion = QLineEdit()
        self.txt_empresa_resolucion.setPlaceholderText("Ej. 192-2017")
        f_lay.addRow("Resolución de Creación:", self.txt_empresa_resolucion)

        self.txt_empresa_telefono = QLineEdit()
        self.txt_empresa_telefono.setPlaceholderText("Teléfono institucional o celular de contacto")
        f_lay.addRow("Teléfono de Contacto:", self.txt_empresa_telefono)

        self.txt_empresa_whatsapp = QLineEdit()
        self.txt_empresa_whatsapp.setPlaceholderText("Número de WhatsApp para avisos (opcional)")
        f_lay.addRow("WhatsApp de Cobranza:", self.txt_empresa_whatsapp)

        self.txt_empresa_direccion = QLineEdit()
        self.txt_empresa_direccion.setPlaceholderText("Dirección institucional, distrito, provincia, región")
        f_lay.addRow("Dirección Legal:", self.txt_empresa_direccion)

        lay.addWidget(grp_comite)

        grp_fact = QGroupBox("Parámetros Operativos de Facturación")
        grp_fact.setStyleSheet("font-weight: bold; color: #0f172a;")
        f_fact = QFormLayout(grp_fact)
        f_fact.setContentsMargins(16, 20, 16, 20)
        f_fact.setSpacing(12)
        f_fact.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.spin_dias_vencimiento = QSpinBox()
        self.spin_dias_vencimiento.setRange(1, 90)
        self.spin_dias_vencimiento.setValue(15)
        self.spin_dias_vencimiento.setSuffix(" días")
        f_fact.addRow("Plazo de Vencimiento:", self.spin_dias_vencimiento)

        self.spin_ultimo_recibo = QSpinBox()
        self.spin_ultimo_recibo.setRange(0, 999999999)
        self.spin_ultimo_recibo.setValue(0)
        self.spin_ultimo_recibo.setDisplayIntegerBase(10)
        f_fact.addRow("Último N° de Recibo:", self.spin_ultimo_recibo)

        lbl_aviso_correlativo = QLabel(
            "⚠️ <i>Los nuevos recibos que emita el sistema continuarán automáticamente a partir de este número + 1.</i>"
        )
        lbl_aviso_correlativo.setStyleSheet("color: #64748b; font-size: 11px;")
        f_fact.addRow("", lbl_aviso_correlativo)

        lay.addWidget(grp_fact)
        lay.addStretch(1)

        scroll.setWidget(contenido)
        return scroll

    # -----------------------------------------------------------------------
    # TAB 2: TARIFAS Y CATEGORÍAS
    # -----------------------------------------------------------------------
    def _crear_tab_tarifas(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        contenido = QWidget()
        lay = QVBoxLayout(contenido)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        # Selector de Categoría A, B o C
        fila_sel = QHBoxLayout()
        lbl_cat_tit = QLabel("Seleccione la Categoría a configurar:")
        lbl_cat_tit.setStyleSheet("font-weight: bold; font-size: 13px; color: #0f172a;")
        fila_sel.addWidget(lbl_cat_tit)

        self.combo_categoria = QComboBox()
        self.combo_categoria.setView(QListView())
        self.combo_categoria.setMinimumWidth(260)
        self.combo_categoria.addItem("Categoría A — Doméstico", "A")
        self.combo_categoria.addItem("Categoría B — Negocio pequeño / Comercial", "B")
        self.combo_categoria.addItem("Categoría C — Hotel / Restaurante / Especial", "C")
        self.combo_categoria.currentIndexChanged.connect(self._al_cambiar_categoria_seleccionada)
        fila_sel.addWidget(self.combo_categoria)
        fila_sel.addStretch(1)

        lay.addLayout(fila_sel)

        # Tarjeta de Datos de la Categoría
        self.grp_cat = QGroupBox("Parámetros de la Categoría")
        self.grp_cat.setStyleSheet("font-weight: bold; color: #0f172a;")
        f_cat = QFormLayout(self.grp_cat)
        f_cat.setContentsMargins(16, 16, 16, 16)
        f_cat.setSpacing(10)
        f_cat.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.txt_cat_nombre = QLineEdit()
        f_cat.addRow("Nombre descriptivo:", self.txt_cat_nombre)

        self.spin_cat_cargo_fijo = QDoubleSpinBox()
        self.spin_cat_cargo_fijo.setRange(0.0, 999.0)
        self.spin_cat_cargo_fijo.setValue(5.00)
        self.spin_cat_cargo_fijo.setSingleStep(0.50)
        self.spin_cat_cargo_fijo.setPrefix("S/. ")
        f_cat.addRow("Cargo Fijo Mensual:", self.spin_cat_cargo_fijo)

        self.spin_cat_tarifa_desague = QDoubleSpinBox()
        self.spin_cat_tarifa_desague.setRange(0.0, 999.0)
        self.spin_cat_tarifa_desague.setValue(0.00)
        self.spin_cat_tarifa_desague.setSingleStep(0.50)
        self.spin_cat_tarifa_desague.setPrefix("S/. ")
        f_cat.addRow("Tarifa Desagüe / Alcantarillado:", self.spin_cat_tarifa_desague)

        # Modo de Rangos
        fila_modo = QHBoxLayout()
        self.rb_modo_tramos = QRadioButton("Modo Tramos (Escalonado progresivo por volumen)")
        self.rb_modo_unico = QRadioButton("Modo Rango Único (Tarifa plana según volumen alcanzado)")
        self.rb_modo_unico.setChecked(True)
        fila_modo.addWidget(self.rb_modo_tramos)
        fila_modo.addWidget(self.rb_modo_unico)
        fila_modo.addStretch(1)
        f_cat.addRow("Método de Facturación:", fila_modo)

        lay.addWidget(self.grp_cat)

        # Tabla de Rangos de Consumo
        grp_rangos = QGroupBox("Escala de Rangos de Consumo (m³)")
        grp_rangos.setStyleSheet("font-weight: bold; color: #0f172a;")
        lay_r = QVBoxLayout(grp_rangos)
        lay_r.setContentsMargins(16, 16, 16, 16)
        lay_r.setSpacing(10)

        fila_btn_r = QHBoxLayout()
        self.btn_agregar_rango = QPushButton("➕ Agregar Rango")
        self.btn_agregar_rango.setProperty("class", "boton boton_secundario")
        self.btn_agregar_rango.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_agregar_rango.clicked.connect(self._accion_agregar_rango)
        fila_btn_r.addWidget(self.btn_agregar_rango)

        self.btn_eliminar_rango = QPushButton("🗑️ Eliminar Rango Seleccionado")
        self.btn_eliminar_rango.setProperty("class", "boton boton_peligro")
        self.btn_eliminar_rango.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_eliminar_rango.clicked.connect(self._accion_eliminar_rango)
        fila_btn_r.addWidget(self.btn_eliminar_rango)
        fila_btn_r.addStretch(1)

        lay_r.addLayout(fila_btn_r)

        self.tabla_rangos = QTableWidget(0, 3)
        self.tabla_rangos.setHorizontalHeaderLabels([
            "Consumo Desde (m³)",
            "Consumo Hasta (m³ — vacío = Sin Límite)",
            "Precio por m³ (S/.)",
        ])
        self.tabla_rangos.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabla_rangos.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla_rangos.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla_rangos.setMinimumHeight(180)
        lay_r.addWidget(self.tabla_rangos)

        lay.addWidget(grp_rangos)
        lay.addStretch(1)

        scroll.setWidget(contenido)
        return scroll

    # -----------------------------------------------------------------------
    # TAB 3: IMPUESTOS (IGV) Y POLÍTICAS DE MORA
    # -----------------------------------------------------------------------
    def _crear_tab_impuestos(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        contenido = QWidget()
        lay = QVBoxLayout(contenido)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(16)

        # IGV
        grp_igv = QGroupBox("Impuesto General a las Ventas (IGV)")
        grp_igv.setStyleSheet("font-weight: bold; color: #0f172a;")
        f_igv = QFormLayout(grp_igv)
        f_igv.setContentsMargins(16, 20, 16, 20)
        f_igv.setSpacing(12)
        f_igv.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.chk_igv_activo = QCheckBox("Activar cálculo y cobro de IGV en los recibos mensuales")
        self.chk_igv_activo.setStyleSheet("font-weight: 500; font-size: 13px;")
        f_igv.addRow("Aplicación de IGV:", self.chk_igv_activo)

        self.spin_igv_porcentaje = QDoubleSpinBox()
        self.spin_igv_porcentaje.setRange(0.0, 100.0)
        self.spin_igv_porcentaje.setValue(18.0)
        self.spin_igv_porcentaje.setSuffix(" %")
        f_igv.addRow("Porcentaje de IGV:", self.spin_igv_porcentaje)

        lbl_info_igv = QLabel(
            "ℹ️ <i>Si el IGV está desactivado, el monto de IGV en los recibos será S/. 0.00 "
            "y no se recargará impuesto a los beneficiarios de la comunidad.</i>"
        )
        lbl_info_igv.setStyleSheet("color: #64748b; font-size: 11px;")
        f_igv.addRow("", lbl_info_igv)

        lay.addWidget(grp_igv)

        # Políticas de Morosidad y Corte
        grp_mora = QGroupBox("Niveles Oficiales de Morosidad y Corte de Servicio")
        grp_mora.setStyleSheet("font-weight: bold; color: #0f172a;")
        lay_m = QVBoxLayout(grp_mora)
        lay_m.setContentsMargins(16, 20, 16, 20)
        lay_m.setSpacing(10)

        lbl_mora_desc = QLabel(
            "Reglas comunitarias para el cálculo de estados de deuda según meses vencidos:"
        )
        lbl_mora_desc.setStyleSheet("font-weight: 500; color: #475569;")
        lay_m.addWidget(lbl_mora_desc)

        def _item_mora(color_bg: str, color_fg: str, nivel: str, meses: str, desc: str) -> QFrame:
            f = QFrame()
            f.setStyleSheet(f"""
                QFrame {{
                    background-color: {color_bg};
                    border: 1px solid #cbd5e1;
                    border-radius: 6px;
                    padding: 8px 12px;
                }}
            """)
            h = QHBoxLayout(f)
            h.setContentsMargins(4, 4, 4, 4)
            lbl_b = QLabel(nivel)
            lbl_b.setStyleSheet(f"background-color: {color_fg}; color: #ffffff; font-weight: bold; padding: 4px 8px; border-radius: 4px;")
            h.addWidget(lbl_b)
            lbl_m = QLabel(f"<b>{meses}:</b> {desc}")
            lbl_m.setStyleSheet("color: #1e293b; font-size: 13px;")
            h.addWidget(lbl_m)
            h.addStretch(1)
            return f

        lay_m.addWidget(_item_mora("#e0f2fe", "#0284c7", "NIVEL AZUL", "1 Mes Adeudado", "Estado regular / Al día. El recibo se emite con normalidad."))
        lay_m.addWidget(_item_mora("#ffedd5", "#ea580c", "NIVEL NARANJA", "2 Meses Adeudados", "Aviso preventivo destacado en color naranja en el recibo de cobro."))
        lay_m.addWidget(_item_mora("#fee2e2", "#dc2626", "NIVEL ROJO", "3 o más Meses", "En lista de corte de servicio. Requiere regularización prioritaria en el reporte de morosos."))

        lay.addWidget(grp_mora)
        lay.addStretch(1)

        scroll.setWidget(contenido)
        return scroll

    # -----------------------------------------------------------------------
    # TAB 4: SECTORES / BARRIOS
    # -----------------------------------------------------------------------
    def _crear_tab_sectores(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        contenido = QWidget()
        lay = QVBoxLayout(contenido)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        lbl_desc = QLabel(
            "Administración de los barrios y sectores de la comunidad de Ispacas. "
            "Estos sectores se sincronizan con la aplicación móvil de los lectores."
        )
        lbl_desc.setStyleSheet("color: #475569; font-size: 13px;")
        lay.addWidget(lbl_desc)

        fila_btn = QHBoxLayout()
        self.btn_agregar_sector = QPushButton("➕ Agregar Sector")
        self.btn_agregar_sector.setProperty("class", "boton boton_secundario")
        self.btn_agregar_sector.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_agregar_sector.clicked.connect(self._accion_agregar_sector)
        fila_btn.addWidget(self.btn_agregar_sector)

        self.btn_eliminar_sector = QPushButton("🗑️ Eliminar Sector")
        self.btn_eliminar_sector.setProperty("class", "boton boton_peligro")
        self.btn_eliminar_sector.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_eliminar_sector.clicked.connect(self._accion_eliminar_sector)
        fila_btn.addWidget(self.btn_eliminar_sector)

        self.btn_subir_sector = QPushButton("⬆️ Subir")
        self.btn_subir_sector.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_subir_sector.clicked.connect(lambda: self._mover_sector(-1))
        fila_btn.addWidget(self.btn_subir_sector)

        self.btn_bajar_sector = QPushButton("⬇️ Bajar")
        self.btn_bajar_sector.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_bajar_sector.clicked.connect(lambda: self._mover_sector(1))
        fila_btn.addWidget(self.btn_bajar_sector)

        fila_btn.addStretch(1)
        lay.addLayout(fila_btn)

        self.tabla_sectores = QTableWidget(0, 2)
        self.tabla_sectores.setHorizontalHeaderLabels(["N°", "Nombre del Sector / Barrio"])
        self.tabla_sectores.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.tabla_sectores.setColumnWidth(0, 60)
        self.tabla_sectores.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabla_sectores.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla_sectores.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla_sectores.setMinimumHeight(240)
        lay.addWidget(self.tabla_sectores)

        lay.addStretch(1)

        scroll.setWidget(contenido)
        return scroll

    # -----------------------------------------------------------------------
    # TAB 5: CATÁLOGO DE OBSERVACIONES DEL MEDIDOR
    # -----------------------------------------------------------------------
    def _crear_tab_observaciones(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        contenido = QWidget()
        lay = QVBoxLayout(contenido)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        lbl_desc = QLabel(
            "Catálogo de novedades que los lectores pueden seleccionar desde la app móvil. "
            "Las novedades marcadas como <b>Alerta Crítica</b> se destacarán automáticamente en Cobros."
        )
        lbl_desc.setStyleSheet("color: #475569; font-size: 13px;")
        lay.addWidget(lbl_desc)

        fila_btn = QHBoxLayout()
        self.btn_agregar_obs = QPushButton("➕ Agregar Novedad")
        self.btn_agregar_obs.setProperty("class", "boton boton_secundario")
        self.btn_agregar_obs.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_agregar_obs.clicked.connect(self._accion_agregar_observacion)
        fila_btn.addWidget(self.btn_agregar_obs)

        self.btn_eliminar_obs = QPushButton("🗑️ Eliminar Novedad")
        self.btn_eliminar_obs.setProperty("class", "boton boton_peligro")
        self.btn_eliminar_obs.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_eliminar_obs.clicked.connect(self._accion_eliminar_observacion)
        fila_btn.addWidget(self.btn_eliminar_obs)

        fila_btn.addStretch(1)
        lay.addLayout(fila_btn)

        self.tabla_observaciones = QTableWidget(0, 3)
        self.tabla_observaciones.setHorizontalHeaderLabels([
            "Código Interno",
            "Descripción en App Móvil y Recibos",
            "¿Alerta Crítica al Cobrar?",
        ])
        self.tabla_observaciones.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.tabla_observaciones.setColumnWidth(0, 180)
        self.tabla_observaciones.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabla_observaciones.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.tabla_observaciones.setColumnWidth(2, 170)
        self.tabla_observaciones.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla_observaciones.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla_observaciones.setMinimumHeight(240)
        lay.addWidget(self.tabla_observaciones)

        lay.addStretch(1)

        scroll.setWidget(contenido)
        return scroll

    # -----------------------------------------------------------------------
    # TAB 6: GESTIÓN DE RESPALDOS Y CONTINGENCIA
    # -----------------------------------------------------------------------
    def _crear_tab_respaldo(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        contenido = QWidget()
        lay = QVBoxLayout(contenido)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(16)

        grp_info = QGroupBox("Estado del Respaldo Local en Excel")
        grp_info.setStyleSheet("font-weight: bold; color: #0f172a;")
        lay_i = QVBoxLayout(grp_info)
        lay_i.setContentsMargins(16, 18, 16, 18)
        lay_i.setSpacing(10)

        self.lbl_info_respaldo_archivo = QLabel("Archivo de respaldo: —")
        self.lbl_info_respaldo_archivo.setStyleSheet("font-weight: bold; color: #0369a1; font-size: 13px;")
        lay_i.addWidget(self.lbl_info_respaldo_archivo)

        self.lbl_info_respaldo_fecha = QLabel("Último respaldo generado: Pendiente")
        self.lbl_info_respaldo_fecha.setStyleSheet("color: #475569; font-size: 13px;")
        lay_i.addWidget(self.lbl_info_respaldo_fecha)

        self.lbl_info_respaldo_docs = QLabel("Total de documentos respaldados: 0")
        self.lbl_info_respaldo_docs.setStyleSheet("color: #475569; font-size: 13px;")
        lay_i.addWidget(self.lbl_info_respaldo_docs)

        fila_acciones = QHBoxLayout()
        fila_acciones.setSpacing(10)

        btn_respaldar_manual = QPushButton("💾 Respaldar Ahora a Excel")
        btn_respaldar_manual.setProperty("class", "boton boton_primario")
        btn_respaldar_manual.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_respaldar_manual.clicked.connect(self._accion_ejecutar_respaldo_manual)
        fila_acciones.addWidget(btn_respaldar_manual)

        btn_abrir_carpeta = QPushButton("📂 Abrir Carpeta de Respaldos")
        btn_abrir_carpeta.setProperty("class", "boton boton_secundario")
        btn_abrir_carpeta.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_abrir_carpeta.clicked.connect(self._accion_abrir_carpeta_respaldos)
        fila_acciones.addWidget(btn_abrir_carpeta)

        btn_ver_manual = QPushButton("📖 Ver Manual de Contingencia")
        btn_ver_manual.setProperty("class", "boton boton_secundario")
        btn_ver_manual.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ver_manual.clicked.connect(self._accion_abrir_manual_contingencia)
        fila_acciones.addWidget(btn_ver_manual)

        fila_acciones.addStretch(1)
        lay_i.addLayout(fila_acciones)

        lay.addWidget(grp_info)

        # Tarjeta explicativa de contingencia
        grp_guia = QGroupBox("Guía Rápida de Contingencia para la Secretaria")
        grp_guia.setStyleSheet("font-weight: bold; color: #0f172a;")
        lay_g = QVBoxLayout(grp_guia)
        lay_g.setContentsMargins(16, 16, 16, 16)
        lay_g.setSpacing(8)

        txt_guia = (
            "• <b>Sin conexión a Internet:</b> El sistema no se bloquea. Puedes continuar cobrando normalmente. "
            "Los pagos se guardan localmente y se subirán a la nube automáticamente al retornar la red.<br>"
            "• <b>Respaldo en memoria USB:</b> Cada viernes se recomienda copiar los archivos de la carpeta "
            "<code>respaldos/</code> a una memoria USB o Google Drive.<br>"
            "• <b>Restauración de emergencia:</b> Si se requiere restaurar los datos en una nueva máquina o tras "
            "una pérdida accidental, se ejecuta el script <code>scripts/restaurar_excel.py</code>."
        )
        lbl_guia = QLabel(txt_guia)
        lbl_guia.setStyleSheet("color: #334155; font-size: 12px; line-height: 1.4;")
        lbl_guia.setWordWrap(True)
        lay_g.addWidget(lbl_guia)

        lay.addWidget(grp_guia)
        lay.addStretch(1)

        scroll.setWidget(contenido)
        return scroll

    # -----------------------------------------------------------------------
    # CARGA Y GUARDADO ASÍNCRONO
    # -----------------------------------------------------------------------
    def cargar_datos_asincrono(self, forzar: bool = False) -> None:
        """Carga la configuración desde el servicio en segundo plano."""
        if not self.servicio:
            return

        self.indicador_carga.iniciar("Cargando configuración...")
        self.btn_recargar.setEnabled(False)
        self.btn_guardar.setEnabled(False)

        def tarea() -> Dict[str, Any]:
            return self.servicio.cargar_config()

        def al_terminar(cfg: Dict[str, Any]) -> None:
            self.indicador_carga.detener()
            self.btn_recargar.setEnabled(True)
            self.btn_guardar.setEnabled(True)
            self.config_actual = copy.deepcopy(cfg or {})
            self.config_cargada = True
            self._poblar_formulario(self.config_actual)
            self._actualizar_info_respaldo()

        def al_error(err: str) -> None:
            self.indicador_carga.detener()
            self.btn_recargar.setEnabled(True)
            self.btn_guardar.setEnabled(True)
            self.alerta_flash.set_mensaje(f"Error al cargar configuración: {err}", "peligro")
            mostrar_dialogo_error(self, "Error de Configuración", str(err))

        self._worker = Worker(tarea)
        self._worker.signals.resultado.connect(al_terminar)
        self._worker.signals.error.connect(al_error)
        self.thread_pool.start(self._worker)

    def _poblar_formulario(self, cfg: Dict[str, Any]) -> None:
        """Llena todos los campos de la interfaz con el diccionario de configuración."""
        # 1. Empresa
        emp = cfg.get("empresa") or {}
        self.txt_empresa_nombre.setText(str(emp.get("nombre") or ""))
        self.txt_empresa_resolucion.setText(str(emp.get("resolucion") or ""))
        self.txt_empresa_telefono.setText(str(emp.get("telefono") or ""))
        self.txt_empresa_whatsapp.setText(str(emp.get("whatsapp") or ""))
        self.txt_empresa_direccion.setText(str(emp.get("direccion") or ""))
        self.spin_dias_vencimiento.setValue(int(cfg.get("dias_vencimiento") or 15))
        self.spin_ultimo_recibo.setValue(int(cfg.get("ultimo_recibo") or 0))

        # 2. IGV
        igv = cfg.get("igv") or {}
        self.chk_igv_activo.setChecked(bool(igv.get("activo", False)))
        porc = float(igv.get("porcentaje") or 0.18) * 100.0
        self.spin_igv_porcentaje.setValue(round(porc, 2))

        # 3. Categorías
        self._al_cambiar_categoria_seleccionada()

        # 4. Sectores
        sectores = cfg.get("sectores") or []
        self._poblar_sectores(sectores)

        # 5. Observaciones
        obs = cfg.get("observaciones") or []
        self._poblar_observaciones(obs)

    def _al_cambiar_categoria_seleccionada(self) -> None:
        cat_key = self.combo_categoria.currentData() or "A"
        categorias = self.config_actual.get("categorias") or {}
        cat_data = categorias.get(cat_key) or {}

        self.txt_cat_nombre.setText(str(cat_data.get("nombre") or f"Categoría {cat_key}"))
        cargo_fijo_val = cat_data.get("cargo_fijo")
        self.spin_cat_cargo_fijo.setValue(float(5.00 if cargo_fijo_val is None else cargo_fijo_val))
        self.spin_cat_tarifa_desague.setValue(float(cat_data.get("tarifa_desague") or 0.0))

        modo = str(cat_data.get("modo_rangos") or "unico").lower()
        if modo == "tramos":
            self.rb_modo_tramos.setChecked(True)
        else:
            self.rb_modo_unico.setChecked(True)

        rangos_defecto = [
            {"m3_desde": 1, "m3_hasta": 10, "precio_m3": 1.0},
            {"m3_desde": 11, "m3_hasta": 15, "precio_m3": 1.5},
            {"m3_desde": 16, "m3_hasta": None, "precio_m3": 4.0},
        ]
        rangos = cat_data.get("rangos")
        if not rangos or (len(rangos) == 1 and rangos[0].get("m3_desde") == 0 and rangos[0].get("m3_hasta") is None):
            rangos = rangos_defecto
        self._poblar_rangos(rangos)

    def _poblar_rangos(self, rangos: List[Dict[str, Any]]) -> None:
        self.tabla_rangos.setRowCount(0)
        for r in rangos:
            row = self.tabla_rangos.rowCount()
            self.tabla_rangos.insertRow(row)

            d_val = r.get("m3_desde")
            desde_val = str(d_val) if d_val is not None else "0"
            h_val = r.get("m3_hasta")
            hasta_val = str(h_val) if (h_val is not None and str(h_val).strip() != "" and str(h_val).lower() != "none") else ""
            precio_val = f"{float(r.get('precio_m3', 1.0)):.2f}"

            item_desde = QTableWidgetItem(desde_val)
            item_desde.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_hasta = QTableWidgetItem(hasta_val)
            item_hasta.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_precio = QTableWidgetItem(precio_val)
            item_precio.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            self.tabla_rangos.setItem(row, 0, item_desde)
            self.tabla_rangos.setItem(row, 1, item_hasta)
            self.tabla_rangos.setItem(row, 2, item_precio)

    def _poblar_sectores(self, sectores: List[str]) -> None:
        self.tabla_sectores.setRowCount(0)
        for i, s in enumerate(sectores):
            row = self.tabla_sectores.rowCount()
            self.tabla_sectores.insertRow(row)

            item_num = QTableWidgetItem(str(i + 1))
            item_num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_num.setFlags(item_num.flags() & ~Qt.ItemFlag.ItemIsEditable)

            item_nom = QTableWidgetItem(s)
            self.tabla_sectores.setItem(row, 0, item_num)
            self.tabla_sectores.setItem(row, 1, item_nom)

    def _poblar_observaciones(self, observaciones: List[Dict[str, Any]]) -> None:
        self.tabla_observaciones.setRowCount(0)
        for ob in observaciones:
            row = self.tabla_observaciones.rowCount()
            self.tabla_observaciones.insertRow(row)

            cod = str(ob.get("codigo") or "")
            txt = str(ob.get("texto") or cod)
            alerta = bool(ob.get("alerta", False))

            item_cod = QTableWidgetItem(cod)
            item_txt = QTableWidgetItem(txt)

            item_chk = QTableWidgetItem()
            item_chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            item_chk.setCheckState(Qt.CheckState.Checked if alerta else Qt.CheckState.Unchecked)
            item_chk.setText("Alerta al cobrar" if alerta else "Normal")

            self.tabla_observaciones.setItem(row, 0, item_cod)
            self.tabla_observaciones.setItem(row, 1, item_txt)
            self.tabla_observaciones.setItem(row, 2, item_chk)

    # -----------------------------------------------------------------------
    # ACCIONES DE EDICIÓN LOCAL
    # -----------------------------------------------------------------------
    def _guardar_categoria_actual_en_cache(self) -> None:
        cat_key = self.combo_categoria.currentData() or "A"
        if "categorias" not in self.config_actual:
            self.config_actual["categorias"] = {}

        rangos = []
        for r in range(self.tabla_rangos.rowCount()):
            d_item = self.tabla_rangos.item(r, 0)
            h_item = self.tabla_rangos.item(r, 1)
            p_item = self.tabla_rangos.item(r, 2)

            d_txt = d_item.text().strip() if d_item else "0"
            h_txt = h_item.text().strip() if h_item else ""
            p_txt = p_item.text().strip().replace("S/.", "") if p_item else "1.0"

            desde = int(d_txt) if d_txt.isdigit() else 0
            hasta = int(h_txt) if h_txt.isdigit() else None
            try:
                precio = float(p_txt)
            except Exception:
                precio = 1.0

            rangos.append({"m3_desde": desde, "m3_hasta": hasta, "precio_m3": precio})

        modo = "unico" if self.rb_modo_unico.isChecked() else "tramos"

        self.config_actual["categorias"][cat_key] = {
            "nombre": self.txt_cat_nombre.text().strip() or f"Categoría {cat_key}",
            "cargo_fijo": round(self.spin_cat_cargo_fijo.value(), 2),
            "tarifa_desague": round(self.spin_cat_tarifa_desague.value(), 2),
            "modo_rangos": modo,
            "rangos": rangos if rangos else [
                {"m3_desde": 1, "m3_hasta": 10, "precio_m3": 1.0},
                {"m3_desde": 11, "m3_hasta": 15, "precio_m3": 1.5},
                {"m3_desde": 16, "m3_hasta": None, "precio_m3": 4.0},
            ],
        }

    def _accion_agregar_rango(self) -> None:
        row = self.tabla_rangos.rowCount()
        self.tabla_rangos.insertRow(row)
        self.tabla_rangos.setItem(row, 0, QTableWidgetItem(str(row * 10)))
        self.tabla_rangos.setItem(row, 1, QTableWidgetItem(""))
        self.tabla_rangos.setItem(row, 2, QTableWidgetItem("1.00"))

    def _accion_eliminar_rango(self) -> None:
        row = self.tabla_rangos.currentRow()
        if row >= 0:
            if self.tabla_rangos.rowCount() <= 1:
                QMessageBox.warning(self, "Aviso", "Debe existir al menos un rango de consumo.")
                return
            self.tabla_rangos.removeRow(row)

    def _accion_agregar_sector(self) -> None:
        nom, ok = QInputDialog.getText(
            self,
            "Nuevo Sector / Barrio",
            "Ingrese el nombre del nuevo sector (ej. BARRIO NUEVO):",
        )
        if ok and nom.strip():
            nombre_limpio = nom.strip().upper()
            row = self.tabla_sectores.rowCount()
            self.tabla_sectores.insertRow(row)

            item_num = QTableWidgetItem(str(row + 1))
            item_num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_num.setFlags(item_num.flags() & ~Qt.ItemFlag.ItemIsEditable)

            item_nom = QTableWidgetItem(nombre_limpio)
            self.tabla_sectores.setItem(row, 0, item_num)
            self.tabla_sectores.setItem(row, 1, item_nom)

    def _accion_eliminar_sector(self) -> None:
        row = self.tabla_sectores.currentRow()
        if row >= 0:
            if self.tabla_sectores.rowCount() <= 1:
                QMessageBox.warning(self, "Aviso", "Debe existir al menos un sector en la comunidad.")
                return
            sec_nom = self.tabla_sectores.item(row, 1).text()
            conf = QMessageBox.question(
                self,
                "Eliminar Sector",
                f"¿Está seguro de eliminar el sector '{sec_nom}' de la configuración?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if conf == QMessageBox.StandardButton.Yes:
                self.tabla_sectores.removeRow(row)
                for i in range(self.tabla_sectores.rowCount()):
                    self.tabla_sectores.item(i, 0).setText(str(i + 1))

    def _mover_sector(self, direccion: int) -> None:
        row = self.tabla_sectores.currentRow()
        target = row + direccion
        if 0 <= target < self.tabla_sectores.rowCount():
            nom_act = self.tabla_sectores.item(row, 1).text()
            nom_tar = self.tabla_sectores.item(target, 1).text()
            self.tabla_sectores.item(row, 1).setText(nom_tar)
            self.tabla_sectores.item(target, 1).setText(nom_act)
            self.tabla_sectores.selectRow(target)

    def _accion_agregar_observacion(self) -> None:
        cod, ok1 = QInputDialog.getText(
            self,
            "Nueva Observación / Novedad",
            "Código interno en mayúsculas (ej. FUGA_VEREDA):",
        )
        if not ok1 or not cod.strip():
            return
        cod_limpio = cod.strip().upper().replace(" ", "_")

        txt, ok2 = QInputDialog.getText(
            self,
            "Descripción de Novedad",
            f"Texto que se mostrará al lector para {cod_limpio}:",
        )
        if not ok2 or not txt.strip():
            return
        txt_limpio = txt.strip()

        row = self.tabla_observaciones.rowCount()
        self.tabla_observaciones.insertRow(row)

        item_chk = QTableWidgetItem()
        item_chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        item_chk.setCheckState(Qt.CheckState.Unchecked)
        item_chk.setText("Normal")

        self.tabla_observaciones.setItem(row, 0, QTableWidgetItem(cod_limpio))
        self.tabla_observaciones.setItem(row, 1, QTableWidgetItem(txt_limpio))
        self.tabla_observaciones.setItem(row, 2, item_chk)

    def _accion_eliminar_observacion(self) -> None:
        row = self.tabla_observaciones.currentRow()
        if row >= 0:
            cod = self.tabla_observaciones.item(row, 0).text()
            if cod == "NORMAL":
                QMessageBox.warning(self, "Aviso", "El estado NORMAL no puede ser eliminado.")
                return
            self.tabla_observaciones.removeRow(row)

    # -----------------------------------------------------------------------
    # GUARDAR EN SERVIDOR Y RESPALDO
    # -----------------------------------------------------------------------
    def _accion_guardar_configuracion(self) -> None:
        """Valida y guarda todos los cambios en Firestore y dispara respaldo."""
        if not self.servicio:
            QMessageBox.warning(self, "Aviso", "No hay conexión al servicio de datos.")
            return

        # 1. Guardar categoría actual
        self._guardar_categoria_actual_en_cache()

        # 2. Extraer datos del formulario
        emp_cfg = copy.deepcopy(self.config_actual.get("empresa") or {})
        nom_emp = self.txt_empresa_nombre.text().strip() or emp_cfg.get("nombre") or (
            "COMITÉ DE ADMINISTRACIÓN DE AGUA POTABLE Y DESAGÜE DE LA COMUNIDAD CAMPESINA DE ISPACAS"
        )
        res_emp = self.txt_empresa_resolucion.text().strip() or emp_cfg.get("resolucion") or "192-2017"
        tel_emp = self.txt_empresa_telefono.text().strip() or emp_cfg.get("telefono") or "986054179"
        ws_emp = self.txt_empresa_whatsapp.text().strip() or emp_cfg.get("whatsapp") or None
        dir_emp = self.txt_empresa_direccion.text().strip() or emp_cfg.get("direccion") or ""

        sectores_lista = []
        for r in range(self.tabla_sectores.rowCount()):
            it = self.tabla_sectores.item(r, 1)
            if it and it.text().strip():
                sectores_lista.append(it.text().strip().upper())

        if not sectores_lista:
            mostrar_dialogo_error(self, "Validación", "Debe existir al menos un sector registrado.")
            self.tabs.setCurrentIndex(2)
            return

        obs_lista = []
        for r in range(self.tabla_observaciones.rowCount()):
            it_cod = self.tabla_observaciones.item(r, 0)
            it_txt = self.tabla_observaciones.item(r, 1)
            it_chk = self.tabla_observaciones.item(r, 2)
            c = it_cod.text().strip() if it_cod else ""
            t = it_txt.text().strip() if it_txt else c
            es_alerta = (it_chk.checkState() == Qt.CheckState.Checked) if it_chk else False
            if c:
                obs_lista.append({"codigo": c, "texto": t, "alerta": es_alerta})

        # Armar diccionario final
        nueva_cfg = copy.deepcopy(self.config_actual)
        nueva_cfg["empresa"] = {
            "nombre": nom_emp,
            "resolucion": res_emp,
            "telefono": tel_emp,
            "whatsapp": ws_emp,
            "direccion": dir_emp,
        }
        nueva_cfg["dias_vencimiento"] = self.spin_dias_vencimiento.value()
        nueva_cfg["ultimo_recibo"] = self.spin_ultimo_recibo.value()
        nueva_cfg["igv"] = {
            "activo": self.chk_igv_activo.isChecked(),
            "porcentaje": round(self.spin_igv_porcentaje.value() / 100.0, 4),
        }
        nueva_cfg["sectores"] = sectores_lista
        nueva_cfg["observaciones"] = obs_lista

        # Confirmación
        conf = QMessageBox.question(
            self,
            "Confirmar Guardado",
            "¿Desea guardar los cambios en la configuración del sistema?\n\n"
            "Los nuevos parámetros se aplicarán de inmediato a los recibos y a la app móvil.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if conf != QMessageBox.StandardButton.Yes:
            return

        self.indicador_carga.iniciar("Guardando configuración en Firestore...")
        self.btn_guardar.setEnabled(False)

        def tarea() -> None:
            self.servicio.guardar_config(nueva_cfg)

        def al_terminar(_res: Any) -> None:
            self.indicador_carga.detener()
            self.btn_guardar.setEnabled(True)
            self.config_actual = nueva_cfg
            self.alerta_flash.set_mensaje(
                "✅ ¡Configuración guardada y sincronizada exitosamente!",
                "exito",
            )
            self._actualizar_info_respaldo()

        def al_error(err: str) -> None:
            self.indicador_carga.detener()
            self.btn_guardar.setEnabled(True)
            self.alerta_flash.set_mensaje(f"Error al guardar configuración: {err}", "peligro")
            mostrar_dialogo_error(self, "Error al guardar configuración", str(err))

        self._worker = Worker(tarea)
        self._worker.signals.resultado.connect(al_terminar)
        self._worker.signals.error.connect(al_error)
        self.thread_pool.start(self._worker)

    # -----------------------------------------------------------------------
    # RESPALDO MANUAL Y CONTINGENCIA
    # -----------------------------------------------------------------------
    def _actualizar_info_respaldo(self) -> None:
        info = respaldo.obtener_info_ultimo_respaldo()
        fecha_h = info.get("fecha_hora") or "Pendiente"
        ruta_p = info.get("ruta") or "RESPALDO_2026-10.xlsx"
        docs_cnt = info.get("total_docs") or 0

        self.lbl_info_respaldo_archivo.setText(f"Archivo de respaldo: {os.path.basename(ruta_p)}")
        self.lbl_info_respaldo_fecha.setText(f"Último respaldo generado: {fecha_h}")
        self.lbl_info_respaldo_docs.setText(f"Total de registros respaldados: {docs_cnt}")

    def _accion_ejecutar_respaldo_manual(self) -> None:
        self.indicador_carga.iniciar("Generando respaldo Excel...")

        def tarea() -> Optional[Path]:
            return respaldo.ejecutar_respaldo_ahora()

        def al_terminar(ruta_generada: Optional[Path]) -> None:
            self.indicador_carga.detener()
            if ruta_generada and os.path.exists(ruta_generada):
                self._actualizar_info_respaldo()
                self.alerta_flash.set_mensaje(
                    f"📦 Respaldo manual completado exitosamente: {os.path.basename(str(ruta_generada))}",
                    "exito",
                )
                resp = QMessageBox.question(
                    self,
                    "Respaldo Completado",
                    f"El archivo de respaldo fue generado exitosamente en:\n\n{ruta_generada}\n\n¿Desea abrir la carpeta de respaldos?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if resp == QMessageBox.StandardButton.Yes:
                    self._accion_abrir_carpeta_respaldos()
            else:
                mostrar_dialogo_error(self, "Error de Respaldo", "No se pudo generar el archivo de respaldo.")

        def al_error(err: str) -> None:
            self.indicador_carga.detener()
            mostrar_dialogo_error(self, "Error al generar respaldo", str(err))

        self._worker = Worker(tarea)
        self._worker.signals.resultado.connect(al_terminar)
        self._worker.signals.error.connect(al_error)
        self.thread_pool.start(self._worker)

    def _accion_abrir_carpeta_respaldos(self) -> None:
        dir_resp = respaldo._obtener_directorio_respaldos()
        dir_resp.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(dir_resp)))

    def _accion_abrir_manual_contingencia(self) -> None:
        try:
            import rutas
            base = rutas.DIR_BASE.parent
        except Exception:
            base = Path(__file__).resolve().parent.parent.parent.parent

        ruta_manual = base / "docs" / "PLAN_CONTINGENCIA.md"
        if ruta_manual.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(ruta_manual)))
        else:
            QMessageBox.information(
                self,
                "Manual de Contingencia",
                "El manual se encuentra en docs/PLAN_CONTINGENCIA.md.",
            )
