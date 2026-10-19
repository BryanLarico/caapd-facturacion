from __future__ import annotations
import copy
import json
from typing import Any, Dict, List, Optional
from PySide6.QtCore import QLocale, QThreadPool, Qt
from PySide6.QtGui import QDoubleValidator, QIntValidator
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
    QScrollArea,
    QSpinBox,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui import iconos
from servicios.datos import ServicioDatos
from ui.componentes.alerta import AlertaWidget
from ui.componentes.indicador_carga import IndicadorCarga
from ui.hilos import Worker, mostrar_dialogo_error
"""
ui/paginas/configuracion.py — Pantalla de Configuración del Sistema (Fase 6).

Permite visualizar y editar:
1. Datos institucionales del Comité (empresa, resolución, teléfonos, dirección).
2. Tarifas por categoría (A, B, C) con escala de rangos de consumo (modo rango único).
3. Parámetros tributarios (IGV) y políticas de morosidad.
4. Sectores / barrios de la comunidad.
5. Catálogo de observaciones y novedades de medidores para la App y la PC.
"""


class DelegadoEdicionEnFila(QStyledItemDelegate):
    """
    Editor plano que ocupa exactamente la celda de la tabla.

    Evita la 'caja flotante' que produce el estilo global de QLineEdit
    (border-radius, padding y min-height definidos en tema.qss).

    tipos_columna: {indice_columna: "entero" | "entero_opcional" | "decimal"}
    """

    def __init__(self, tipos_columna: Dict[int, str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tipos = tipos_columna

    def createEditor(self, parent, option, index):  # noqa: N802
        editor = QLineEdit(parent)
        editor.setFrame(False)
        editor.setStyleSheet(
            "QLineEdit { border: none; border-radius: 0; padding: 0 8px; margin: 0; "
            "min-height: 0; background-color: #ffffff; color: #0f172a; font-size: 13px; }"
        )
        tipo = self._tipos.get(index.column())
        if tipo in ("entero", "entero_opcional"):
            editor.setValidator(QIntValidator(0, 999999, editor))
        elif tipo == "decimal":
            validador = QDoubleValidator(0.0, 9999.0, 2, editor)
            validador.setNotation(QDoubleValidator.Notation.StandardNotation)
            validador.setLocale(QLocale.c())  # acepta punto decimal (1.50)
            editor.setValidator(validador)
        editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return editor

    def updateEditorGeometry(self, editor, option, index):  # noqa: N802
        editor.setGeometry(option.rect)


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

        # Control de cambios pendientes (habilita/deshabilita "Guardar Configuración")
        # True mientras se llena el formulario
        self._poblando: bool = False
        # snapshot del formulario sin cambios
        self._config_base: Optional[Dict[str, Any]] = None
        # categoría visible en la pestaña Tarifas
        self._cat_key_actual: str = "A"

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

        # Botón Reestablecer
        self.btn_recargar = QPushButton("Reestablecer")
        iconos.aplicar(self.btn_recargar, "refresh")
        self.btn_recargar.setProperty("class", "boton boton_secundario")
        self.btn_recargar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_recargar.clicked.connect(
            lambda: self.cargar_datos_asincrono(forzar=True))
        fila_encabezado.addWidget(self.btn_recargar)

        # Botón Guardar
        self.btn_guardar = QPushButton("Guardar Configuración")
        iconos.aplicar(self.btn_guardar, "device-floppy", "blanco")
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
        # deshabilitado hasta que exista algún cambio
        self.btn_guardar.setEnabled(False)
        self.btn_guardar.setToolTip("No hay cambios pendientes por guardar")
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
        self.tabs.addTab(self._crear_tab_tarifas(),
                         iconos.icono("droplet", "primario"), "Tarifas y Categorías")

        # Pestaña 2: Impuestos y Mora
        self.tabs.addTab(self._crear_tab_impuestos(),
                         iconos.icono("receipt-tax", "primario"), "Impuestos (IGV) y Mora")

        # Pestaña 3: Sectores
        self.tabs.addTab(self._crear_tab_sectores(),
                         iconos.icono("map-pin", "primario"), "Sectores / Barrios")

        # Pestaña 4: Observaciones de Medidor
        self.tabs.addTab(self._crear_tab_observaciones(),
                         iconos.icono("clipboard-list", "primario"), "Catálogo de Novedades")

        layout_principal.addWidget(self.tabs, stretch=1)

        # Conectar señales de todos los campos para detectar cambios
        self._conectar_senales_cambios()

    # -----------------------------------------------------------------------
    # TAB 1: DATOS INSTITUCIONALES DEL COMITÉ (oculta, se conserva internamente)
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
        self.txt_empresa_nombre.setPlaceholderText(
            "Nombre completo del comité de agua")
        f_lay.addRow("Nombre del Comité:", self.txt_empresa_nombre)

        self.txt_empresa_resolucion = QLineEdit()
        self.txt_empresa_resolucion.setPlaceholderText("Ej. 192-2017")
        f_lay.addRow("Resolución de Creación:", self.txt_empresa_resolucion)

        self.txt_empresa_telefono = QLineEdit()
        self.txt_empresa_telefono.setPlaceholderText(
            "Teléfono institucional o celular de contacto")
        f_lay.addRow("Teléfono de Contacto:", self.txt_empresa_telefono)

        self.txt_empresa_whatsapp = QLineEdit()
        self.txt_empresa_whatsapp.setPlaceholderText(
            "Número de WhatsApp para avisos (opcional)")
        f_lay.addRow("WhatsApp de Cobranza:", self.txt_empresa_whatsapp)

        self.txt_empresa_direccion = QLineEdit()
        self.txt_empresa_direccion.setPlaceholderText(
            "Dirección institucional, distrito, provincia, región")
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
            "<i>Los nuevos recibos que emita el sistema continuarán automáticamente a partir de este número + 1.</i>"
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
        lbl_cat_tit.setStyleSheet(
            "font-weight: bold; font-size: 13px; color: #0f172a;")
        fila_sel.addWidget(lbl_cat_tit)

        self.combo_categoria = QComboBox()
        self.combo_categoria.setView(QListView())
        self.combo_categoria.setMinimumWidth(260)
        self.combo_categoria.addItem("Categoría A — Doméstico", "A")
        self.combo_categoria.addItem(
            "Categoría B — Negocio pequeño / Comercial", "B")
        self.combo_categoria.addItem(
            "Categoría C — Hotel / Restaurante / Especial", "C")
        self.combo_categoria.currentIndexChanged.connect(
            self._al_cambiar_categoria_seleccionada)
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
        self.spin_cat_cargo_fijo.setToolTip(
            "Cargo fijo mensual regular cuando el usuario registra consumo de agua"
        )
        f_cat.addRow("Cargo Fijo Mensual:", self.spin_cat_cargo_fijo)

        self.spin_cat_cargo_fijo_sin_consumo = QDoubleSpinBox()
        self.spin_cat_cargo_fijo_sin_consumo.setRange(0.0, 999.0)
        self.spin_cat_cargo_fijo_sin_consumo.setValue(5.00)
        self.spin_cat_cargo_fijo_sin_consumo.setSingleStep(0.50)
        self.spin_cat_cargo_fijo_sin_consumo.setPrefix("S/. ")
        self.spin_cat_cargo_fijo_sin_consumo.setToolTip(
            "Monto fijo a cobrar cuando el usuario no registre consumo de agua (0 m³)"
        )
        f_cat.addRow("Cargo Fijo sin Consumo:",
                     self.spin_cat_cargo_fijo_sin_consumo)

        self.spin_cat_tarifa_desague = QDoubleSpinBox()
        self.spin_cat_tarifa_desague.setRange(0.0, 999.0)
        self.spin_cat_tarifa_desague.setValue(0.00)
        self.spin_cat_tarifa_desague.setSingleStep(0.50)
        self.spin_cat_tarifa_desague.setPrefix("S/. ")
        f_cat.addRow("Tarifa Desagüe / Alcantarillado:",
                     self.spin_cat_tarifa_desague)

        lay.addWidget(self.grp_cat)

        # Tabla de Rangos de Consumo
        grp_rangos = QGroupBox("Escala de Rangos de Consumo (m³)")
        grp_rangos.setStyleSheet("font-weight: bold; color: #0f172a;")
        lay_r = QVBoxLayout(grp_rangos)
        lay_r.setContentsMargins(16, 16, 16, 16)
        lay_r.setSpacing(10)

        fila_btn_r = QHBoxLayout()
        self.btn_agregar_rango = QPushButton("Agregar Rango")
        iconos.aplicar(self.btn_agregar_rango, "plus")
        self.btn_agregar_rango.setProperty("class", "boton boton_secundario")
        self.btn_agregar_rango.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_agregar_rango.clicked.connect(self._accion_agregar_rango)
        fila_btn_r.addWidget(self.btn_agregar_rango)

        self.btn_eliminar_rango = QPushButton("Eliminar Rango Seleccionado")
        iconos.aplicar(self.btn_eliminar_rango, "trash", "peligro")
        self.btn_eliminar_rango.setProperty("class", "boton boton_peligro_secundario")
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
        self.tabla_rangos.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.tabla_rangos.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla_rangos.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla_rangos.setMinimumHeight(180)
        # Edición directa en la fila (sin caja flotante)
        self.tabla_rangos.verticalHeader().setDefaultSectionSize(36)
        self.tabla_rangos.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        self.tabla_rangos.setItemDelegate(
            DelegadoEdicionEnFila(
                {0: "entero", 1: "entero_opcional", 2: "decimal"}, self.tabla_rangos)
        )
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

        self.chk_igv_activo = QCheckBox(
            "Activar cálculo y cobro de IGV en los recibos mensuales")
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
        grp_mora = QGroupBox(
            "Niveles Oficiales de Morosidad y Corte de Servicio")
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
            lbl_b.setStyleSheet(
                f"background-color: {color_fg}; color: #ffffff; font-weight: bold; padding: 4px 8px; border-radius: 4px;")
            h.addWidget(lbl_b)
            lbl_m = QLabel(f"<b>{meses}:</b> {desc}")
            lbl_m.setStyleSheet("color: #1e293b; font-size: 13px;")
            h.addWidget(lbl_m)
            h.addStretch(1)
            return f

        lay_m.addWidget(_item_mora("#e0f2fe", "#0284c7", "NIVEL AZUL", "1 Mes Adeudado",
                        "Estado regular / Al día. El recibo se emite con normalidad."))
        lay_m.addWidget(_item_mora("#ffedd5", "#ea580c", "NIVEL NARANJA", "2 Meses Adeudados",
                        "Aviso preventivo destacado en color naranja en el recibo de cobro."))
        lay_m.addWidget(_item_mora("#fee2e2", "#dc2626", "NIVEL ROJO", "3 o más Meses",
                        "En lista de corte de servicio. Requiere regularización prioritaria en el reporte de morosos."))

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
        self.btn_agregar_sector = QPushButton("Agregar Sector")
        iconos.aplicar(self.btn_agregar_sector, "plus")
        self.btn_agregar_sector.setProperty("class", "boton boton_secundario")
        self.btn_agregar_sector.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_agregar_sector.clicked.connect(self._accion_agregar_sector)
        fila_btn.addWidget(self.btn_agregar_sector)

        self.btn_eliminar_sector = QPushButton("Eliminar Sector")
        iconos.aplicar(self.btn_eliminar_sector, "trash", "blanco")
        self.btn_eliminar_sector.setProperty("class", "boton boton_peligro")
        self.btn_eliminar_sector.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_eliminar_sector.clicked.connect(self._accion_eliminar_sector)
        fila_btn.addWidget(self.btn_eliminar_sector)

        fila_btn.addStretch(1)
        lay.addLayout(fila_btn)

        self.tabla_sectores = QTableWidget(0, 2)
        self.tabla_sectores.setHorizontalHeaderLabels(
            ["N°", "Nombre del Sector / Barrio"])
        self.tabla_sectores.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Fixed)
        self.tabla_sectores.setColumnWidth(0, 60)
        self.tabla_sectores.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self.tabla_sectores.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla_sectores.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla_sectores.setMinimumHeight(240)
        self.tabla_sectores.verticalHeader().setDefaultSectionSize(36)
        self.tabla_sectores.setItemDelegate(
            DelegadoEdicionEnFila({}, self.tabla_sectores))
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
        self.btn_agregar_obs = QPushButton("Agregar Novedad")
        iconos.aplicar(self.btn_agregar_obs, "plus")
        self.btn_agregar_obs.setProperty("class", "boton boton_secundario")
        self.btn_agregar_obs.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_agregar_obs.clicked.connect(self._accion_agregar_observacion)
        fila_btn.addWidget(self.btn_agregar_obs)

        self.btn_eliminar_obs = QPushButton("Eliminar Novedad")
        iconos.aplicar(self.btn_eliminar_obs, "trash", "blanco")
        self.btn_eliminar_obs.setProperty("class", "boton boton_peligro")
        self.btn_eliminar_obs.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_eliminar_obs.clicked.connect(
            self._accion_eliminar_observacion)
        fila_btn.addWidget(self.btn_eliminar_obs)

        fila_btn.addStretch(1)
        lay.addLayout(fila_btn)

        self.tabla_observaciones = QTableWidget(0, 3)
        self.tabla_observaciones.setHorizontalHeaderLabels([
            "Código Interno",
            "Descripción en App Móvil y Recibos",
            "¿Alerta Crítica al Cobrar?",
        ])
        self.tabla_observaciones.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Interactive)
        self.tabla_observaciones.setColumnWidth(0, 180)
        self.tabla_observaciones.horizontalHeader().setSectionResizeMode(1,
                                                                         QHeaderView.ResizeMode.Stretch)
        self.tabla_observaciones.horizontalHeader().setSectionResizeMode(2,
                                                                         QHeaderView.ResizeMode.Fixed)
        self.tabla_observaciones.setColumnWidth(2, 170)
        self.tabla_observaciones.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla_observaciones.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla_observaciones.setMinimumHeight(240)
        self.tabla_observaciones.verticalHeader().setDefaultSectionSize(36)
        self.tabla_observaciones.setItemDelegate(
            DelegadoEdicionEnFila({}, self.tabla_observaciones))
        lay.addWidget(self.tabla_observaciones)

        lay.addStretch(1)

        scroll.setWidget(contenido)
        return scroll

    # -----------------------------------------------------------------------
    # CARGA ASÍNCRONA
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
            self.config_actual = copy.deepcopy(cfg or {})
            self.config_cargada = True
            self._poblar_formulario(self.config_actual)
            self._establecer_linea_base()  # a partir de aquí no hay cambios pendientes

        def al_error(err: str) -> None:
            self.indicador_carga.detener()
            self.btn_recargar.setEnabled(True)
            self._verificar_cambios()
            self.alerta_flash.set_mensaje(
                f"Error al cargar configuración: {err}", "peligro")
            mostrar_dialogo_error(self, "Error de Configuración", str(err))

        self._worker = Worker(tarea)
        self._worker.signals.resultado.connect(al_terminar)
        self._worker.signals.error.connect(al_error)
        self.thread_pool.start(self._worker)

    def _poblar_formulario(self, cfg: Dict[str, Any]) -> None:
        """Llena todos los campos de la interfaz con el diccionario de configuración."""
        self._poblando = True
        try:
            # 1. Empresa
            emp = cfg.get("empresa") or {}
            self.txt_empresa_nombre.setText(str(emp.get("nombre") or ""))
            self.txt_empresa_resolucion.setText(
                str(emp.get("resolucion") or ""))
            self.txt_empresa_telefono.setText(str(emp.get("telefono") or ""))
            self.txt_empresa_whatsapp.setText(str(emp.get("whatsapp") or ""))
            self.txt_empresa_direccion.setText(str(emp.get("direccion") or ""))
            self.spin_dias_vencimiento.setValue(
                int(cfg.get("dias_vencimiento") or 15))
            self.spin_ultimo_recibo.setValue(
                int(cfg.get("ultimo_recibo") or 0))

            # 2. IGV
            igv = cfg.get("igv") or {}
            self.chk_igv_activo.setChecked(bool(igv.get("activo", False)))
            porc = float(igv.get("porcentaje") or 0.18) * 100.0
            self.spin_igv_porcentaje.setValue(round(porc, 2))

            # 3. Categorías
            self._cat_key_actual = self.combo_categoria.currentData() or "A"
            self._cargar_categoria_en_formulario(self._cat_key_actual)

            # 4. Sectores
            self._poblar_sectores(cfg.get("sectores") or [])

            # 5. Observaciones
            self._poblar_observaciones(cfg.get("observaciones") or [])
        finally:
            self._poblando = False

    def _al_cambiar_categoria_seleccionada(self) -> None:
        """Al cambiar el combo: guarda en caché la categoría anterior y carga la nueva."""
        if self._poblando:
            return
        nueva_key = self.combo_categoria.currentData() or "A"

        # Conservar lo editado en la categoría que se estaba viendo
        if self.config_cargada:
            self._guardar_categoria_actual_en_cache(self._cat_key_actual)

        self._poblando = True
        try:
            self._cat_key_actual = nueva_key
            self._cargar_categoria_en_formulario(nueva_key)
        finally:
            self._poblando = False
        self._verificar_cambios()

    def _cargar_categoria_en_formulario(self, cat_key: str) -> None:
        """Vuelca los datos de una categoría (A/B/C) en los campos y la tabla de rangos."""
        categorias = self.config_actual.get("categorias") or {}
        cat_data = categorias.get(cat_key) or {}

        self.txt_cat_nombre.setText(
            str(cat_data.get("nombre") or f"Categoría {cat_key}"))
        cargo_fijo_val = cat_data.get("cargo_fijo")
        cf_num = float(5.00 if cargo_fijo_val is None else cargo_fijo_val)
        self.spin_cat_cargo_fijo.setValue(cf_num)
        cargo_fijo_sc_val = cat_data.get("cargo_fijo_sin_consumo")
        cf_sc_num = float(cf_num if cargo_fijo_sc_val is None else cargo_fijo_sc_val)
        self.spin_cat_cargo_fijo_sin_consumo.setValue(cf_sc_num)
        self.spin_cat_tarifa_desague.setValue(
            float(cat_data.get("tarifa_desague") or 0.0))

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
            hasta_val = str(h_val) if (h_val is not None and str(
                h_val).strip() != "" and str(h_val).lower() != "none") else ""
            precio_val = f"{float(r.get('precio_m3', 1.0)):.2f}"

            item_desde = QTableWidgetItem(desde_val)
            item_desde.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_hasta = QTableWidgetItem(hasta_val)
            item_hasta.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_precio = QTableWidgetItem(precio_val)
            item_precio.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

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
            item_chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable |
                              Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            item_chk.setCheckState(
                Qt.CheckState.Checked if alerta else Qt.CheckState.Unchecked)
            item_chk.setText("Alerta al cobrar" if alerta else "Normal")

            self.tabla_observaciones.setItem(row, 0, item_cod)
            self.tabla_observaciones.setItem(row, 1, item_txt)
            self.tabla_observaciones.setItem(row, 2, item_chk)

    # -----------------------------------------------------------------------
    # ACCIONES DE EDICIÓN LOCAL
    # -----------------------------------------------------------------------
    def _guardar_categoria_actual_en_cache(self, cat_key: Optional[str] = None) -> None:
        cat_key = cat_key or self._cat_key_actual
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

            rangos.append(
                {"m3_desde": desde, "m3_hasta": hasta, "precio_m3": precio})

        self.config_actual["categorias"][cat_key] = {
            "nombre": self.txt_cat_nombre.text().strip() or f"Categoría {cat_key}",
            "cargo_fijo": round(self.spin_cat_cargo_fijo.value(), 2),
            "cargo_fijo_sin_consumo": round(self.spin_cat_cargo_fijo_sin_consumo.value(), 2),
            "tarifa_desague": round(self.spin_cat_tarifa_desague.value(), 2),
            # siempre rango único (calculos.py sigue leyendo esta clave)
            "modo_rangos": "unico",
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
        for c in range(3):
            it = self.tabla_rangos.item(row, c)
            if it:
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tabla_rangos.selectRow(row)
        self.tabla_rangos.editItem(self.tabla_rangos.item(
            row, 0))  # empieza a editar en la fila
        self._verificar_cambios()

    def _accion_eliminar_rango(self) -> None:
        row = self.tabla_rangos.currentRow()
        if row >= 0:
            if self.tabla_rangos.rowCount() <= 1:
                QMessageBox.warning(
                    self, "Aviso", "Debe existir al menos un rango de consumo.")
                return
            self.tabla_rangos.removeRow(row)
            self._verificar_cambios()

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
            self._verificar_cambios()

    def _accion_eliminar_sector(self) -> None:
        row = self.tabla_sectores.currentRow()
        if row >= 0:
            if self.tabla_sectores.rowCount() <= 1:
                QMessageBox.warning(
                    self, "Aviso", "Debe existir al menos un sector en la comunidad.")
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
                self._verificar_cambios()

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
        item_chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable |
                          Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        item_chk.setCheckState(Qt.CheckState.Unchecked)
        item_chk.setText("Normal")

        self.tabla_observaciones.setItem(row, 0, QTableWidgetItem(cod_limpio))
        self.tabla_observaciones.setItem(row, 1, QTableWidgetItem(txt_limpio))
        self.tabla_observaciones.setItem(row, 2, item_chk)
        self._verificar_cambios()

    def _accion_eliminar_observacion(self) -> None:
        row = self.tabla_observaciones.currentRow()
        if row >= 0:
            cod = self.tabla_observaciones.item(row, 0).text()
            if cod == "NORMAL":
                QMessageBox.warning(
                    self, "Aviso", "El estado NORMAL no puede ser eliminado.")
                return
            self.tabla_observaciones.removeRow(row)
            self._verificar_cambios()

    # -----------------------------------------------------------------------
    # DETECCIÓN DE CAMBIOS PENDIENTES
    # -----------------------------------------------------------------------
    def _conectar_senales_cambios(self) -> None:
        """Conecta todos los campos editables a _verificar_cambios."""
        for w in (
            self.txt_empresa_nombre,
            self.txt_empresa_resolucion,
            self.txt_empresa_telefono,
            self.txt_empresa_whatsapp,
            self.txt_empresa_direccion,
            self.txt_cat_nombre,
        ):
            w.textChanged.connect(self._verificar_cambios)
        for w in (
            self.spin_dias_vencimiento,
            self.spin_ultimo_recibo,
            self.spin_igv_porcentaje,
            self.spin_cat_cargo_fijo,
            self.spin_cat_cargo_fijo_sin_consumo,
            self.spin_cat_tarifa_desague,
        ):
            w.valueChanged.connect(self._verificar_cambios)
        self.chk_igv_activo.toggled.connect(self._verificar_cambios)
        for t in (self.tabla_rangos, self.tabla_sectores, self.tabla_observaciones):
            t.itemChanged.connect(self._verificar_cambios)

    def _construir_config_desde_formulario(self) -> Dict[str, Any]:
        """Arma el diccionario de configuración completo a partir de lo que hay en pantalla."""
        self._guardar_categoria_actual_en_cache()

        emp_cfg = copy.deepcopy(self.config_actual.get("empresa") or {})
        nom_emp = self.txt_empresa_nombre.text().strip() or emp_cfg.get("nombre") or (
            "COMITÉ DE ADMINISTRACIÓN DE AGUA POTABLE Y DESAGÜE DE LA COMUNIDAD CAMPESINA DE ISPACAS"
        )
        res_emp = self.txt_empresa_resolucion.text().strip(
        ) or emp_cfg.get("resolucion") or "192-2017"
        tel_emp = self.txt_empresa_telefono.text().strip(
        ) or emp_cfg.get("telefono") or "986054179"
        ws_emp = self.txt_empresa_whatsapp.text().strip() or emp_cfg.get("whatsapp") or None
        dir_emp = self.txt_empresa_direccion.text(
        ).strip() or emp_cfg.get("direccion") or ""

        sectores_lista: List[str] = []
        for r in range(self.tabla_sectores.rowCount()):
            it = self.tabla_sectores.item(r, 1)
            if it and it.text().strip():
                sectores_lista.append(it.text().strip().upper())

        obs_lista: List[Dict[str, Any]] = []
        for r in range(self.tabla_observaciones.rowCount()):
            it_cod = self.tabla_observaciones.item(r, 0)
            it_txt = self.tabla_observaciones.item(r, 1)
            it_chk = self.tabla_observaciones.item(r, 2)
            c = it_cod.text().strip() if it_cod else ""
            t = it_txt.text().strip() if it_txt else c
            es_alerta = (it_chk.checkState() ==
                         Qt.CheckState.Checked) if it_chk else False
            if c:
                obs_lista.append(
                    {"codigo": c, "texto": t, "alerta": es_alerta})

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
        return nueva_cfg

    @staticmethod
    def _huella(cfg: Any) -> str:
        """Representación estable para comparar configuraciones."""
        return json.dumps(cfg, sort_keys=True, ensure_ascii=False, default=str)

    def _establecer_linea_base(self) -> None:
        """Toma el estado actual del formulario como 'sin cambios pendientes'."""
        self._config_base = self._construir_config_desde_formulario()
        self._verificar_cambios()

    def _hay_cambios(self) -> bool:
        if not self.config_cargada or self._config_base is None:
            return False
        return self._huella(self._construir_config_desde_formulario()) != self._huella(self._config_base)

    def _verificar_cambios(self, *_args: Any) -> None:
        """Habilita 'Guardar Configuración' solo si hay cambios pendientes."""
        if self._poblando:
            return
        hay = self._hay_cambios()
        self.btn_guardar.setEnabled(hay)
        self.btn_guardar.setToolTip(
            "Guardar los cambios pendientes" if hay else "No hay cambios pendientes por guardar"
        )

    def _secciones_modificadas(self, nueva_cfg: Dict[str, Any]) -> List[str]:
        """Devuelve los nombres de las secciones que cambiaron respecto a la línea base."""
        base = self._config_base or {}
        etiquetas = [
            (("empresa", "dias_vencimiento", "ultimo_recibo"), "Datos generales"),
            (("categorias",), "Tarifas y Categorías"),
            (("igv",), "IGV"),
            (("sectores",), "Sectores / Barrios"),
            (("observaciones",), "Catálogo de Novedades"),
        ]
        cambios: List[str] = []
        for claves, nombre in etiquetas:
            if any(self._huella(base.get(k)) != self._huella(nueva_cfg.get(k)) for k in claves):
                cambios.append(nombre)
        return cambios

    # -----------------------------------------------------------------------
    # GUARDAR EN SERVIDOR
    # -----------------------------------------------------------------------
    def _accion_guardar_configuracion(self) -> None:
        """Valida y guarda únicamente si hay cambios pendientes."""
        if not self.servicio:
            QMessageBox.warning(
                self, "Aviso", "No hay conexión al servicio de datos.")
            return

        if not self._hay_cambios():
            self.alerta_flash.set_mensaje(
                "No hay cambios pendientes por guardar.", "info")
            self._verificar_cambios()
            return

        nueva_cfg = self._construir_config_desde_formulario()

        if not nueva_cfg["sectores"]:
            mostrar_dialogo_error(
                self, "Validación", "Debe existir al menos un sector registrado.")
            self.tabs.setCurrentIndex(2)
            return

        secciones = self._secciones_modificadas(nueva_cfg)
        detalle = ", ".join(
            secciones) if secciones else "Configuración general"

        conf = QMessageBox.question(
            self,
            "Confirmar Guardado",
            f"Se guardarán cambios en: {detalle}.\n\n"
            "Los nuevos parámetros se aplicarán de inmediato a los recibos y a la app móvil.\n"
            "¿Desea continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if conf != QMessageBox.StandardButton.Yes:
            return

        self.indicador_carga.iniciar("Guardando configuración...")
        self.btn_guardar.setEnabled(False)

        def tarea() -> None:
            self.servicio.guardar_config(nueva_cfg)

        def al_terminar(_res: Any) -> None:
            self.indicador_carga.detener()
            self.config_actual = copy.deepcopy(nueva_cfg)
            self._establecer_linea_base()  # el botón vuelve a quedar deshabilitado
            self.alerta_flash.set_mensaje(
                f"Configuración guardada correctamente. Secciones actualizadas: {detalle}.",
                "exito",
            )

        def al_error(err: str) -> None:
            self.indicador_carga.detener()
            self._verificar_cambios()
            self.alerta_flash.set_mensaje(
                f"Error al guardar configuración: {err}", "peligro")
            mostrar_dialogo_error(
                self, "Error al guardar configuración", str(err))

        self._worker = Worker(tarea)
        self._worker.signals.resultado.connect(al_terminar)
        self._worker.signals.error.connect(al_error)
        self.thread_pool.start(self._worker)
