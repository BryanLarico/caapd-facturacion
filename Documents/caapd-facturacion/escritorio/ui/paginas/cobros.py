"""
ui/paginas/cobros.py — Pantalla unificada de Cobros y Facturación.

Versión simplificada:
- 3 Tarjetas KPI compactas (Total facturado, Recaudado, En lista de corte)
- Chips de filtro por estado de mora y alertas
- Barra única: Sector + Buscador + "Imprimir / Descargar recibo PDF" + "Carpeta de recibos"
- Tabla con deudas editables, total calculado y filas coloreadas por morosidad
- Ficha lateral con detalle y cobro todo o nada
- Avisos en forma de pop-up (toast) de 5 segundos en la esquina superior derecha
- Diseño responsive: en ventanas angostas la ficha pasa debajo de la tabla
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListView,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

import rutas
from servicios.datos import ServicioDatos
from ui import iconos
from ui.componentes.toast import Toast
from ui.hilos import Worker, mostrar_dialogo_error
from ui.paginas.cobros_modelo import DelegadoFilasCobros, ModeloCobros, ProxyCobros

# Ancho (px) por debajo del cual la ficha lateral se coloca debajo de la tabla
ANCHO_MINIMO_DOS_COLUMNAS = 1150

NOMBRES_MESES_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}


def formatear_mes_espanol(periodo: str) -> str:
    """Devuelve 'Septiembre 2026' dado '2026-09'."""
    try:
        partes = str(periodo or "").strip().split("-")
        if len(partes) == 2:
            y, m = int(partes[0]), int(partes[1])
            nombre = NOMBRES_MESES_ES.get(m, f"Mes {m:02d}")
            return f"{nombre} {y}"
    except Exception:
        pass
    return str(periodo or "")


class PaginaCobros(QWidget):
    """Pantalla interactiva unificada de facturación, cobranza y control de morosidad."""

    TEXTO_BTN_ACTUALIZAR = "Actualizar"

    def __init__(self, servicio_datos: ServicioDatos, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.servicio = servicio_datos
        self.thread_pool = QThreadPool.globalInstance()
        self._worker = None

        self.periodo_actual: str = ""
        self.estado_mes: str = "ABIERTO"
        self.config_actual: Dict[str, Any] = {}
        self.lista_items_completa: List[Dict[str, Any]] = []
        self.item_seleccionado: Optional[Dict[str, Any]] = None
        self._modo_compacto: Optional[bool] = None

        # Debounce buscador (150ms)
        self.timer_busqueda = QTimer(self)
        self.timer_busqueda.setSingleShot(True)
        self.timer_busqueda.setInterval(150)
        self.timer_busqueda.timeout.connect(self._ejecutar_busqueda)

        self._filtro_estado = "todos"

        self._construir_ui()

    # -----------------------------------------------------------------------
    # Construcción de la interfaz
    # -----------------------------------------------------------------------
    def _construir_ui(self) -> None:
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(24, 14, 24, 14)
        layout_principal.setSpacing(10)

        # 1. Encabezado de la página
        fila_encabezado = QHBoxLayout()
        fila_encabezado.setSpacing(12)

        col_titulos = QVBoxLayout()
        col_titulos.setSpacing(2)
        lbl_titulo = QLabel("Cobros y Facturación")
        lbl_titulo.setObjectName("encabezado_titulo")
        col_titulos.addWidget(lbl_titulo)

        lbl_subtitulo = QLabel(
            "Control diario de cobranzas, emisión mensual y morosidad")
        lbl_subtitulo.setObjectName("encabezado_subtitulo")
        col_titulos.addWidget(lbl_subtitulo)
        fila_encabezado.addLayout(col_titulos)

        fila_encabezado.addStretch(1)

        # Selector de Periodo en Cobros (Botón con Menú y Submenús por año)
        self.lbl_badge_periodo = QLabel("Periodo: —")
        self.lbl_badge_periodo.hide()

        self.btn_periodo = QPushButton("Periodo: —")
        self.btn_periodo.setObjectName("btn_periodo_cobros")
        self.btn_periodo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_periodo.setToolTip("Cambiar periodo de cobranza o consultar meses anteriores")
        self.btn_periodo.setStyleSheet(
            "QPushButton#btn_periodo_cobros { "
            "  background-color: #ffffff; color: #0f172a; font-weight: 600; font-size: 13px; "
            "  border: 1.5px solid #cbd5e1; border-radius: 8px; padding: 6px 32px 6px 14px; text-align: left; "
            "} "
            "QPushButton#btn_periodo_cobros:hover { "
            "  border-color: #0284c7; background-color: #f8fafc; "
            "} "
            "QPushButton#btn_periodo_cobros::menu-indicator { "
            "  subcontrol-origin: padding; subcontrol-position: center right; right: 12px; "
            "}"
        )
        self.combo_periodo = self.btn_periodo  # Compatibilidad
        self.menu_periodo = QMenu(self.btn_periodo)
        self.btn_periodo.setMenu(self.menu_periodo)
        fila_encabezado.addWidget(self.btn_periodo)

        # Botón Carpeta de recibos (Escritorio/recibos) — entre Periodo y Actualizar
        self.btn_carpeta_recibos = QPushButton("Carpeta de recibos")
        iconos.aplicar(self.btn_carpeta_recibos, "folder-open")
        self.btn_carpeta_recibos.setProperty("class", "boton boton_secundario")
        self.btn_carpeta_recibos.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_carpeta_recibos.setToolTip(
            "Abre la carpeta Escritorio/recibos donde se guardan los PDF")
        self.btn_carpeta_recibos.clicked.connect(self._abrir_carpeta_recibos)
        fila_encabezado.addWidget(self.btn_carpeta_recibos)

        # Botón Actualizar
        self.btn_actualizar = QPushButton(self.TEXTO_BTN_ACTUALIZAR)
        iconos.aplicar(self.btn_actualizar, "refresh")
        self.btn_actualizar.setProperty("class", "boton boton_secundario")
        self.btn_actualizar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_actualizar.clicked.connect(self.accion_actualizar)
        fila_encabezado.addWidget(self.btn_actualizar)

        layout_principal.addLayout(fila_encabezado)

        # 2. Tarjetas KPI (compactas)
        fila_kpi = QHBoxLayout()
        fila_kpi.setSpacing(10)

        self.card_facturado = self._crear_tarjeta_kpi(
            "Total Facturado", "S/. 0.00", "chart-bar", "primario")
        self.card_recaudado = self._crear_tarjeta_kpi(
            "Recaudado", "S/. 0.00", "coins", "exito")
        self.card_corte = self._crear_tarjeta_kpi(
            "En Lista de Corte", "0 usuarios", "alert-octagon", "peligro")

        fila_kpi.addWidget(self.card_facturado)
        fila_kpi.addWidget(self.card_recaudado)
        fila_kpi.addWidget(self.card_corte)

        layout_principal.addLayout(fila_kpi)

        # 3. Chips de Filtro
        fila_chips = QHBoxLayout()
        fila_chips.setSpacing(8)

        self.btn_filtro_todos = self._crear_boton_filtro("Todos (0)", "todos")
        self.btn_filtro_pendientes = self._crear_boton_filtro(
            "Pendientes (0)", "pendientes")
        self.btn_filtro_dos_meses = self._crear_boton_filtro(
            "2 Meses (0)", "dos_meses")
        self.btn_filtro_corte = self._crear_boton_filtro(
            "Corte 3+ m. (0)", "corte")
        self.btn_filtro_pagados = self._crear_boton_filtro(
            "Pagados (0)", "pagados")
        self.btn_filtro_alertas = self._crear_boton_filtro(
            "Con Alertas (0)", "alertas")

        # Botón Actualizar Excel — recarga modificaciones de la base de datos Excel sin reiniciar la app
        self.btn_actualizar_excel = QPushButton("Actualizar Excel")
        self.btn_actualizar_excel.setProperty("class", "filtro_btn_excel")
        self.btn_actualizar_excel.setProperty("activo", "false")
        self.btn_actualizar_excel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_actualizar_excel.setToolTip(
            "Recarga las modificaciones del archivo Excel del padrón sin reiniciar el programa"
        )
        self.btn_actualizar_excel.clicked.connect(self.accion_recargar_excel)

        for chip in (
            self.btn_filtro_todos,
            self.btn_filtro_pendientes,
            self.btn_filtro_dos_meses,
            self.btn_filtro_corte,
            self.btn_filtro_pagados,
            self.btn_filtro_alertas,
            self.btn_actualizar_excel,
        ):
            fila_chips.addWidget(chip)
        fila_chips.addStretch(1)

        # Columna izquierda: chips + buscador + tabla (comparten el mismo ancho)
        self.panel_izquierdo = QWidget()
        col_izquierda = QVBoxLayout(self.panel_izquierdo)
        col_izquierda.setContentsMargins(0, 0, 0, 0)
        col_izquierda.setSpacing(10)
        col_izquierda.addLayout(fila_chips)

        # 4. Barra única: Sector + Buscador + Acciones
        fila_filtros = QHBoxLayout()
        fila_filtros.setSpacing(10)

        lbl_sec = QLabel("Sector:")
        lbl_sec.setStyleSheet("font-weight: 500; color: #475569;")
        fila_filtros.addWidget(lbl_sec)

        self.combo_sector = QComboBox()
        self.combo_sector.setView(QListView())
        self.combo_sector.setMinimumWidth(170)
        self.combo_sector.addItem("Todos los sectores", "todos")
        self.combo_sector.currentIndexChanged.connect(self._al_cambiar_sector)
        fila_filtros.addWidget(self.combo_sector)

        self.input_buscar = QLineEdit()
        self.input_buscar.setPlaceholderText(
            "Buscar por titular, DNI, conexión, N° recibo o medidor...")
        self.input_buscar.addAction(
            iconos.icono("search", "gris"), QLineEdit.ActionPosition.LeadingPosition)
        self.input_buscar.setClearButtonEnabled(True)
        self.input_buscar.setMinimumWidth(220)
        self.input_buscar.textChanged.connect(
            lambda: self.timer_busqueda.start())
        fila_filtros.addWidget(self.input_buscar, stretch=1)

        col_izquierda.addLayout(fila_filtros)

        # 5. Splitter: [chips + buscador + tabla] | Ficha Detalle (la ficha sube hasta la altura de los chips)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)

        # Tabla
        self.modelo = ModeloCobros([], self)
        self.modelo.cambio_deuda_solicitado.connect(self._al_cambiar_deuda)
        self.proxy = ProxyCobros(self)
        self.proxy.setSourceModel(self.modelo)

        self.tabla = QTableView()
        self.tabla.setObjectName("tabla_cobros")
        self.tabla.setModel(self.proxy)
        self.tabla.setItemDelegate(DelegadoFilasCobros(self.tabla))
        self.tabla.setSelectionBehavior(
            QTableView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.tabla.setSortingEnabled(True)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setShowGrid(False)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(34)
        self.tabla.setMinimumHeight(320)
        self.tabla.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.tabla.selectionModel().selectionChanged.connect(self._al_seleccionar_fila)
        self.tabla.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabla.customContextMenuRequested.connect(
            self._menu_contextual_tabla)

        # Anchos de 9 columnas: todas fijas salvo "Titular", que se estira para
        # ocupar el espacio sobrante en cualquier tamaño de pantalla.
        header = self.tabla.horizontalHeader()
        header.setMinimumSectionSize(60)
        header.setStretchLastSection(False)

        anchos_fijos = {
            0: 95,    # Conexión
            1: 100,   # N° Recibo
            3: 110,   # Sector
            4: 70,    # m³
            5: 125,   # Deuda anterior
            6: 125,   # Deuda actual
            7: 110,   # Total S/.
            8: 120,   # Estado
        }
        for col, ancho in anchos_fijos.items():
            header.setSectionResizeMode(
                col, QHeaderView.ResizeMode.Interactive)
            header.resizeSection(col, ancho)

        header.setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch)  # Titular

        col_izquierda.addWidget(self.tabla, stretch=1)
        self.splitter.addWidget(self.panel_izquierdo)

        # Ficha lateral
        self.ficha = self._crear_ficha_lateral()
        self.splitter.addWidget(self.ficha)
        self.splitter.setStretchFactor(0, 7)
        self.splitter.setStretchFactor(1, 3)

        layout_principal.addWidget(self.splitter, stretch=1)

        # 6. Toast flotante (no forma parte del layout: se dibuja encima del contenido)
        self.toast = Toast(self)

    def _crear_tarjeta_kpi(self, titulo: str, valor_defecto: str,
                           icono: str, color_icono: str = "texto") -> QFrame:
        card = QFrame()
        card.setProperty("class", "tarjeta")
        card.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(10)

        col = QVBoxLayout()
        col.setSpacing(2)
        lbl_tit = QLabel(titulo)
        lbl_tit.setStyleSheet(
            "color: #64748b; font-size: 11px; font-weight: bold; text-transform: uppercase;")
        col.addWidget(lbl_tit)

        lbl_val = QLabel(valor_defecto)
        lbl_val.setStyleSheet(
            "font-size: 17px; font-weight: bold; color: #0f172a;")
        col.addWidget(lbl_val)
        lay.addLayout(col, stretch=1)

        lbl_ico = iconos.etiqueta(icono, color_icono, 22)
        lay.addWidget(lbl_ico, alignment=Qt.AlignmentFlag.AlignTop)

        card.lbl_valor = lbl_val  # type: ignore
        return card

    def _crear_boton_filtro(self, texto: str, clave: str) -> QPushButton:
        btn = QPushButton(texto)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setProperty("filtro_clave", clave)
        btn.setProperty("activo", "true" if clave == "todos" else "false")
        # El filtro "Con Alertas" usa el estilo ámbar de advertencia, igual que "Pendientes de DNI"
        if clave == "alertas":
            btn.setProperty("class", "filtro_btn filtro_btn_aviso")
            iconos.aplicar(btn, "alert-triangle", "aviso", 15)
        else:
            btn.setProperty("class", "filtro_btn")
        btn.clicked.connect(lambda: self._al_clic_filtro(clave))
        return btn

    def _crear_ficha_lateral(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMinimumWidth(320)
        scroll.setMaximumWidth(480)

        contenedor = QFrame()
        contenedor.setProperty("class", "tarjeta")
        lay = QVBoxLayout(contenedor)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(8)

        # Título Ficha
        lbl_tit_ficha = QLabel("Ficha del Usuario")
        lbl_tit_ficha.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #0f172a;")
        lay.addWidget(lbl_tit_ficha)

        # Estado visual de mora (Badge)
        self.lbl_ficha_badge_mora = QLabel("Al día (1 mes)")
        self.lbl_ficha_badge_mora.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_ficha_badge_mora.setStyleSheet(
            "background-color: #dcfce7; color: #166534; font-weight: bold; padding: 6px; border-radius: 6px; font-size: 12px;"
        )
        lay.addWidget(self.lbl_ficha_badge_mora)

        # Datos Generales
        self.lbl_ficha_nombre = QLabel("—")
        self.lbl_ficha_nombre.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #0369a1;")
        self.lbl_ficha_nombre.setWordWrap(True)
        lay.addWidget(self.lbl_ficha_nombre)

        self.lbl_ficha_dni = QLabel("DNI: —")
        self.lbl_ficha_dni.setStyleSheet("font-size: 12px; color: #475569;")
        lay.addWidget(self.lbl_ficha_dni)

        self.lbl_ficha_medidores = QLabel("Medidores: —")
        self.lbl_ficha_medidores.setStyleSheet(
            "font-size: 12px; color: #475569;")
        self.lbl_ficha_medidores.setWordWrap(True)
        lay.addWidget(self.lbl_ficha_medidores)

        # Recuadro Alerta de Medidor (Novedades / Notas)
        self.box_alerta_medidor = QFrame()
        self.box_alerta_medidor.setStyleSheet("""
            QFrame {
                background-color: #fef3c7;
                border: 1px solid #fde68a;
                border-radius: 6px;
                padding: 8px 10px;
            }
        """)
        lay_alerta = QVBoxLayout(self.box_alerta_medidor)
        lay_alerta.setContentsMargins(4, 4, 4, 4)
        self.lbl_texto_alerta_medidor = QLabel("Observación en medidor")
        self.lbl_texto_alerta_medidor.setStyleSheet(
            "color: #92400e; font-size: 12px; font-weight: 500;")
        self.lbl_texto_alerta_medidor.setWordWrap(True)
        lay_alerta.addWidget(self.lbl_texto_alerta_medidor)
        lay.addWidget(self.box_alerta_medidor)
        self.box_alerta_medidor.hide()

        # Separador
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setStyleSheet("color: #e2e8f0;")
        lay.addWidget(sep1)

        # Desglose de Cuenta
        lbl_desglose_tit = QLabel("DESGLOSE DE CUENTA")
        lbl_desglose_tit.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #64748b;")
        lay.addWidget(lbl_desglose_tit)

        self.lbl_ficha_deuda_ant = QLabel("Deuda anterior: S/. 0.00")
        self.lbl_ficha_deuda_ant.setStyleSheet(
            "font-size: 12px; color: #475569;")
        lay.addWidget(self.lbl_ficha_deuda_ant)

        self.lbl_ficha_mes_actual = QLabel("Consumo mes: S/. 0.00")
        self.lbl_ficha_mes_actual.setStyleSheet(
            "font-size: 12px; color: #475569;")
        lay.addWidget(self.lbl_ficha_mes_actual)

        self.lbl_ficha_cargo_fijo = QLabel("Cargo fijo: S/. 1.50")
        self.lbl_ficha_cargo_fijo.setStyleSheet(
            "font-size: 12px; color: #475569;")
        lay.addWidget(self.lbl_ficha_cargo_fijo)

        self.lbl_ficha_total = QLabel("Total a pagar: S/. 0.00")
        self.lbl_ficha_total.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #0f172a; margin-top: 4px;")
        lay.addWidget(self.lbl_ficha_total)

        # Separador
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: #e2e8f0;")
        lay.addWidget(sep2)

        # Botones de Acción
        self.btn_marcar_pagado = QPushButton("Marcar como pagado")
        iconos.aplicar(self.btn_marcar_pagado, "credit-card", "blanco", 18)
        self.btn_marcar_pagado.setProperty(
            "class", "boton boton_exito boton_grande")
        self.btn_marcar_pagado.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_marcar_pagado.setStyleSheet("""
            QPushButton {
                background-color: #16a34a; color: #ffffff;
                font-weight: bold; font-size: 13px; padding: 8px; border-radius: 6px;
            }
            QPushButton:hover { background-color: #15803d; }
            QPushButton:disabled { background-color: #94a3b8; color: #f1f5f9; }
        """)
        self.btn_marcar_pagado.clicked.connect(self._accion_marcar_pagado)
        lay.addWidget(self.btn_marcar_pagado)

        self.btn_ver_recibo = QPushButton("Imprimir / Descargar recibo PDF")
        iconos.aplicar(self.btn_ver_recibo, "printer", "blanco", 18)
        self.btn_ver_recibo.setProperty(
            "class", "boton boton_primario boton_grande")
        self.btn_ver_recibo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ver_recibo.setStyleSheet("""
            QPushButton {
                background-color: #0284c7; color: #ffffff;
                font-weight: bold; font-size: 13px; padding: 8px; border-radius: 6px;
            }
            QPushButton:hover { background-color: #0369a1; }
            QPushButton:disabled { background-color: #94a3b8; color: #f1f5f9; }
        """)
        self.btn_ver_recibo.clicked.connect(self._accion_ver_recibo)
        lay.addWidget(self.btn_ver_recibo)

        self.btn_anular_cobro = QPushButton("Anular cobro")
        iconos.aplicar(self.btn_anular_cobro, "arrow-back-up", "blanco")
        self.btn_anular_cobro.setProperty("class", "boton boton_peligro")
        self.btn_anular_cobro.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_anular_cobro.clicked.connect(self._accion_anular_cobro)
        lay.addWidget(self.btn_anular_cobro)

        lay.addStretch(1)

        scroll.setWidget(contenedor)
        return scroll

    # -----------------------------------------------------------------------
    # Diseño responsive
    # -----------------------------------------------------------------------
    def resizeEvent(self, event) -> None:  # noqa: N802 (nombre de Qt)
        super().resizeEvent(event)
        self._aplicar_modo_responsive(event.size().width())
        if hasattr(self, "toast") and self.toast.isVisible():
            self.toast.reposicionar()

    def _aplicar_modo_responsive(self, ancho: int) -> None:
        """En ventanas angostas la ficha pasa debajo de la tabla; en anchas va al costado."""
        compacto = ancho < ANCHO_MINIMO_DOS_COLUMNAS
        if compacto == self._modo_compacto:
            return
        self._modo_compacto = compacto

        if compacto:
            self.splitter.setOrientation(Qt.Orientation.Vertical)
            self.ficha.setMaximumWidth(16777215)
            self.ficha.setMinimumWidth(0)
            self.ficha.setMaximumHeight(300)
            self.splitter.setStretchFactor(0, 6)
            self.splitter.setStretchFactor(1, 4)
        else:
            self.splitter.setOrientation(Qt.Orientation.Horizontal)
            self.ficha.setMaximumHeight(16777215)
            self.ficha.setMinimumWidth(320)
            self.ficha.setMaximumWidth(480)
            self.splitter.setStretchFactor(0, 7)
            self.splitter.setStretchFactor(1, 3)

    def _set_cargando(self, activo: bool, texto: str = "Actualizando…") -> None:
        """Indica carga en el propio botón Actualizar (sin barra ni texto adicional en pantalla)."""
        self.btn_actualizar.setEnabled(not activo)
        self.btn_actualizar.setText(
            f"{texto}" if activo else self.TEXTO_BTN_ACTUALIZAR)

    # -----------------------------------------------------------------------
    # Carga Asíncrona de Datos
    # -----------------------------------------------------------------------
    def accion_actualizar(self) -> None:
        """Actualiza desde el padrón local, sube a Firebase o descarga de lectores móviles."""
        if getattr(self.servicio, "es_local_first", False):
            from ui.componentes.dialogo_actualizar import DialogoActualizarBaseDatos
            dlg = DialogoActualizarBaseDatos(self)
            acceptado = dlg.exec() == QDialog.DialogCode.Accepted
            dlg.deleteLater()
            if not acceptado:
                return

            ventana = self.window()

            if dlg.resultado_accion == DialogoActualizarBaseDatos.ACCION_LOCAL:
                if hasattr(ventana, "mostrar_progreso"):
                    ventana.mostrar_progreso(50, "Recargando padrón local...")
                self.cargar_datos_asincrono(forzar=True, periodo=self.periodo_actual)
                if hasattr(ventana, "ocultar_progreso"):
                    ventana.ocultar_progreso("¡Padrón local recargado!")
                return

            elif dlg.resultado_accion == DialogoActualizarBaseDatos.ACCION_SUBIR_FIREBASE:
                self._set_cargando(True, "Subiendo a Firebase…")

                def progreso_callback(pct, txt):
                    if hasattr(ventana, "mostrar_progreso"):
                        ventana.mostrar_progreso(pct, txt)

                def tarea_subir():
                    return self.servicio.reescribir_a_firebase(callback_progreso=progreso_callback)

                def al_terminar_subida(res):
                    if hasattr(ventana, "ocultar_progreso"):
                        ventana.ocultar_progreso(
                            "¡Bases sincronizadas con Firebase!")
                    self.cargar_datos_asincrono(forzar=True, periodo=self.periodo_actual)
                    QMessageBox.information(
                        self,
                        "Sincronización Completada",
                        f"Se subieron a Firebase:\n\n"
                        f"• {res.get('usuarios', 0)} usuarios en la colección 'usuarios'.\n"
                        f"• {len(res.get('meses', []))} colecciones mensuales.\n"
                        f"• {res.get('operaciones_escritura', 0)} operaciones de escritura totales.",
                    )

                worker = Worker(tarea_subir)
                worker.signals.resultado.connect(al_terminar_subida)
                worker.signals.error.connect(self._al_fallar_carga)
                self.thread_pool.start(worker)
                return

            elif dlg.resultado_accion == DialogoActualizarBaseDatos.ACCION_DESCARGAR_FIREBASE:
                self._set_cargando(True, "Sincronizando…")

                def tarea_sync():
                    res = self.servicio.sincronizar_desde_firebase()
                    self.servicio.limpiar_cache()
                    return res

                def al_terminar_descarga(res):
                    if hasattr(ventana, "ocultar_progreso"):
                        ventana.ocultar_progreso("¡Lecturas descargadas y recibos emitidos!")
                    if hasattr(self, "toast"):
                        self.toast.mostrar(
                            "¡Lecturas descargadas y recibos emitidos con éxito!", "exito"
                        )
                    p_descargado = (res or {}).get("periodo")
                    if not p_descargado and hasattr(self.servicio, "obtener_periodo_cobranza"):
                        p_descargado = self.servicio.obtener_periodo_cobranza()
                    if p_descargado:
                        self.periodo_actual = p_descargado
                    self.cargar_datos_asincrono(forzar=True, periodo=self.periodo_actual)

                worker = Worker(tarea_sync)
                worker.signals.resultado.connect(al_terminar_descarga)
                worker.signals.error.connect(self._al_fallar_carga)
                self.thread_pool.start(worker)
                return

        self.cargar_datos_asincrono(forzar=True, periodo=self.periodo_actual)

    def accion_recargar_excel(self) -> None:
        """Recarga los datos directamente desde el Excel del padrón sin reiniciar el programa."""
        self.btn_actualizar_excel.setProperty("activo", "true")
        self.btn_actualizar_excel.style().unpolish(self.btn_actualizar_excel)
        self.btn_actualizar_excel.style().polish(self.btn_actualizar_excel)
        self.btn_actualizar_excel.setEnabled(False)
        self.btn_actualizar_excel.setText("Actualizando…")

        ventana = self.window()
        if hasattr(ventana, "mostrar_progreso"):
            ventana.mostrar_progreso(50, "Recargando datos desde el Excel...")

        def tarea():
            self.servicio.limpiar_cache()
            cfg = self.servicio.cargar_config()
            periodos_disp = (
                self.servicio.obtener_periodos_disponibles()
                if hasattr(self.servicio, "obtener_periodos_disponibles")
                else []
            )
            periodo = self.periodo_actual
            if not periodo or (periodos_disp and periodo not in periodos_disp):
                if hasattr(self.servicio, "obtener_periodo_cobranza"):
                    periodo = self.servicio.obtener_periodo_cobranza()
                else:
                    mes_act = cfg.get("mes_actual") or {}
                    periodo = mes_act.get("periodo") or "2026-09"
            docs = self.servicio.cargar_mes(periodo)
            return cfg, periodo, docs

        def al_terminar(resultado):
            self._al_recibir_datos(resultado)
            self.btn_actualizar_excel.setEnabled(True)
            self.btn_actualizar_excel.setText("Actualizar Excel")
            if hasattr(ventana, "ocultar_progreso"):
                ventana.ocultar_progreso("¡Padrón Excel recargado!")
            self.toast.mostrar(
                "¡Excel recargado con éxito! Se sincronizaron los cambios.", "exito"
            )
            QTimer.singleShot(2000, self._desactivar_estado_btn_excel)

        def al_fallar(err_msg):
            self.btn_actualizar_excel.setEnabled(True)
            self.btn_actualizar_excel.setText("Actualizar Excel")
            self._desactivar_estado_btn_excel()
            self._al_fallar_carga(err_msg)

        worker = Worker(tarea)
        worker.signals.resultado.connect(al_terminar)
        worker.signals.error.connect(al_fallar)
        self.thread_pool.start(worker)

    def _desactivar_estado_btn_excel(self) -> None:
        """Restaura el botón Actualizar Excel a su estado de reposo (fondo blanco, borde verde)."""
        if hasattr(self, "btn_actualizar_excel"):
            self.btn_actualizar_excel.setProperty("activo", "false")
            self.btn_actualizar_excel.style().unpolish(self.btn_actualizar_excel)
            self.btn_actualizar_excel.style().polish(self.btn_actualizar_excel)

    def cargar_datos_asincrono(self, forzar: bool = False, periodo: Optional[str] = None) -> None:
        self._set_cargando(True)

        def tarea():
            if forzar:
                self.servicio.limpiar_cache()
            cfg = self.servicio.cargar_config()

            p_cobranza = periodo
            periodos_disp = (
                self.servicio.obtener_periodos_disponibles()
                if hasattr(self.servicio, "obtener_periodos_disponibles")
                else []
            )
            if not p_cobranza or (periodos_disp and p_cobranza not in periodos_disp):
                if hasattr(self.servicio, "obtener_periodo_cobranza"):
                    p_cobranza = self.servicio.obtener_periodo_cobranza()
                else:
                    mes_act = cfg.get("mes_actual") or {}
                    p_cobranza = mes_act.get("periodo") or "2026-09"

            docs = self.servicio.cargar_mes(p_cobranza)
            return cfg, p_cobranza, docs

        worker = Worker(tarea)
        worker.signals.resultado.connect(self._al_recibir_datos)
        worker.signals.error.connect(self._al_fallar_carga)
        worker.signals.finalizado.connect(lambda: self._set_cargando(False))
        self.thread_pool.start(worker)

    def _al_seleccionar_periodo_menu(self, periodo: str) -> None:
        if periodo and periodo != self.periodo_actual:
            self.cargar_datos_asincrono(periodo=periodo)

    def _actualizar_menu_periodos(self) -> None:
        """Construye el menú organizado de periodos: meses activos arriba y años anteriores en submenús."""
        if not hasattr(self, "btn_periodo"):
            return

        periodos_disp: List[str] = []
        if hasattr(self.servicio, "obtener_periodos_disponibles"):
            periodos_disp = self.servicio.obtener_periodos_disponibles()
        elif hasattr(self.servicio, "meses_encontrados"):
            periodos_disp = sorted(self.servicio.meses_encontrados.keys(), reverse=True)
        if not periodos_disp:
            periodos_disp = [self.periodo_actual]

        p_cobranza = (
            self.servicio.obtener_periodo_cobranza()
            if hasattr(self.servicio, "obtener_periodo_cobranza")
            else None
        )
        p_lecturas = (
            self.servicio.obtener_periodo_lecturas()
            if hasattr(self.servicio, "obtener_periodo_lecturas")
            else None
        )

        # Agrupar periodos por año
        periodos_por_anio: Dict[int, List[str]] = {}
        for p in periodos_disp:
            try:
                y = int(str(p).split("-")[0])
            except Exception:
                y = 2026
            periodos_por_anio.setdefault(y, []).append(p)

        anios_ordenados = sorted(periodos_por_anio.keys(), reverse=True)
        anio_reciente = anios_ordenados[0] if anios_ordenados else 2026

        # Crear nuevo menú estilizado
        menu = QMenu(self.btn_periodo)
        menu.setStyleSheet(
            "QMenu { "
            "  background-color: #ffffff; color: #0f172a; "
            "  border: 1.5px solid #cbd5e1; border-radius: 8px; padding: 6px; "
            "} "
            "QMenu::item { "
            "  padding: 8px 24px 8px 12px; border-radius: 6px; "
            "  font-size: 13px; font-weight: 500; min-width: 230px; "
            "} "
            "QMenu::item:selected { "
            "  background-color: #e0f2fe; color: #0369a1; "
            "} "
            "QMenu::separator { "
            "  height: 1px; background: #e2e8f0; margin: 4px 6px; "
            "} "
            "QMenu::section { "
            "  color: #64748b; font-size: 11px; font-weight: bold; "
            "  padding: 4px 10px; margin-top: 2px; "
            "}"
        )

        def agregar_item_periodo(parent_menu: QMenu, per: str) -> None:
            etiqueta = formatear_mes_espanol(per)
            ico = iconos.icono("circle-check" if per == p_cobranza else "calendar-plus", "gris")

            if per == p_cobranza:
                etiqueta += "  ·  Cobranza activa"
                ico = iconos.icono("circle-check", "exito")
            elif per == p_lecturas and p_lecturas != p_cobranza:
                etiqueta += "  ·  En lecturas"
                ico = iconos.icono("clock", "aviso")

            accion = parent_menu.addAction(ico, etiqueta)
            accion.setCheckable(True)
            if per == self.periodo_actual:
                accion.setChecked(True)
                accion.setIcon(iconos.icono("check", "primario"))

            accion.triggered.connect(
                lambda checked=False, p_sel=per: self._al_seleccionar_periodo_menu(p_sel)
            )

        # 1. Meses del año en curso
        for p in periodos_por_anio.get(anio_reciente, []):
            agregar_item_periodo(menu, p)

        # 2. Años anteriores como submenús (máximo 12 meses por año)
        anios_anteriores = [y for y in anios_ordenados if y < anio_reciente]
        if anios_anteriores:
            menu.addSeparator()
            for y_prev in anios_anteriores:
                meses_prev = periodos_por_anio[y_prev]
                contiene_seleccionado = self.periodo_actual in meses_prev
                sub_ico = (
                    iconos.icono("check", "primario")
                    if contiene_seleccionado
                    else iconos.icono("folder-open", "gris")
                )
                titulo_sub = f"Año {y_prev}  ({len(meses_prev)} meses)"
                if contiene_seleccionado:
                    titulo_sub += "  ·  [Activo]"
                submenu = menu.addMenu(sub_ico, titulo_sub)
                submenu.setStyleSheet(menu.styleSheet())
                for p_sub in meses_prev:
                    agregar_item_periodo(submenu, p_sub)

        self.btn_periodo.setMenu(menu)

        # Actualizar texto e icono del botón principal
        texto_btn = formatear_mes_espanol(self.periodo_actual)
        ico_btn = iconos.icono("calendar-plus", "primario")
        if self.periodo_actual == p_cobranza:
            texto_btn += " (Cobranza activa)"
            ico_btn = iconos.icono("circle-check", "exito")
        elif self.periodo_actual == p_lecturas and p_lecturas != p_cobranza:
            texto_btn += " (En lecturas)"
            ico_btn = iconos.icono("clock", "aviso")

        self.btn_periodo.setIcon(ico_btn)
        self.btn_periodo.setText(f"  {texto_btn}  ")

    def _al_recibir_datos(self, resultado: tuple) -> None:
        self.config_actual, self.periodo_actual, mes_dict = resultado
        self._set_cargando(False)

        if hasattr(self.servicio, "_estado_de_periodo"):
            self.estado_mes = self.servicio._estado_de_periodo(self.periodo_actual)
        else:
            mes_act = self.config_actual.get("mes_actual") or {}
            self.estado_mes = mes_act.get("estado") or "ABIERTO"

        self.lbl_badge_periodo.setText(f"Periodo: {self.periodo_actual}")

        # Actualizar botón y menú de selección de periodos
        self._actualizar_menu_periodos()

        # Actualizar sectores en el combo
        sectores = self.config_actual.get("sectores") or []
        sector_actual = self.combo_sector.currentData() or "todos"
        self.combo_sector.blockSignals(True)
        self.combo_sector.clear()
        self.combo_sector.addItem("Todos los sectores", "todos")
        for s in sectores:
            self.combo_sector.addItem(s, s)
        idx = self.combo_sector.findData(sector_actual)
        if idx >= 0:
            self.combo_sector.setCurrentIndex(idx)
        self.combo_sector.blockSignals(False)

        # Cargar lista
        self.lista_items_completa = list(mes_dict.values())
        self.modelo.actualizar_datos(self.lista_items_completa)

        # Actualizar KPIs y Chips
        self._actualizar_kpis_y_chips()

        # Seleccionar primera fila si existe
        if self.proxy.rowCount() > 0:
            self.tabla.selectRow(0)
        else:
            self._limpiar_ficha()

    def _al_fallar_carga(self, err_msg: str) -> None:
        self._set_cargando(False)
        mostrar_dialogo_error(self, "Error al cargar datos de cobros", err_msg)

    def _al_cambiar_deuda(self, id_usuario: str, campo: str, valor: float) -> None:
        """Persiste la deuda editada en el padrón antes de refrescar la tabla."""
        try:
            doc_actualizado = self.servicio.actualizar_deuda(
                self.periodo_actual, id_usuario, campo, valor
            )
            for doc in self.lista_items_completa:
                if str(doc.get("id_usuario") or doc.get("_id") or "") == id_usuario:
                    doc.update(doc_actualizado)
                    break
            self.modelo.notificar_cambio_deuda(id_usuario)
            if (
                self.item_seleccionado
                and str(self.item_seleccionado.get("id_usuario") or self.item_seleccionado.get("_id") or "") == id_usuario
            ):
                self.item_seleccionado.update(doc_actualizado)
                self._actualizar_ficha(self.item_seleccionado)
            self.proxy.refrescar_filtros()
            self._actualizar_kpis_y_chips()
            self.toast.mostrar(
                "Deuda actualizada y guardada en el padrón.", "exito")
        except Exception as exc:
            mostrar_dialogo_error(
                self,
                "No se pudo guardar la deuda",
                f"No se aplicó el cambio al padrón.\n\n{exc}",
            )

    def _actualizar_kpis_y_chips(self) -> None:
        tot_usuarios = len(self.lista_items_completa)
        tot_facturado = 0.0
        tot_recaudado = 0.0
        n_corte = 0
        n_pendientes = 0
        n_dos_meses = 0
        n_pagados = 0
        n_alertas = 0

        for d in self.lista_items_completa:
            tot = float(d.get("total_a_pagar") or 0.0)
            pag = float(d.get("monto_pagado") or 0.0)
            saldo = max(0.0, round(tot - pag, 2))
            meses = int(d.get("meses_adeudados") or 1)
            tiene_rec = bool(d.get("nro_recibo"))
            esta_pag = (saldo <= 0.0 and tot > 0.0)

            tot_facturado += tot
            tot_recaudado += pag

            if esta_pag:
                n_pagados += 1
            else:
                if tiene_rec:
                    n_pendientes += 1
                    if meses == 2:
                        n_dos_meses += 1
                    elif meses >= 3:
                        n_corte += 1

            # Alertas
            meds = d.get("medidores") or []
            if any(str(m.get("novedad") or "").strip().upper() not in ("", "NORMAL") or bool(str(m.get("nota") or "").strip()) for m in meds):
                n_alertas += 1

        # Actualizar KPIs
        self.card_facturado.lbl_valor.setText(f"S/. {tot_facturado:,.2f}")
        self.card_recaudado.lbl_valor.setText(f"S/. {tot_recaudado:,.2f}")
        self.card_corte.lbl_valor.setText(f"{n_corte} usuarios")

        # Actualizar textos en chips
        self.btn_filtro_todos.setText(f"Todos ({tot_usuarios})")
        self.btn_filtro_pendientes.setText(f"Pendientes ({n_pendientes})")
        self.btn_filtro_dos_meses.setText(f"2 Meses ({n_dos_meses})")
        self.btn_filtro_corte.setText(f"Corte 3+ m. ({n_corte})")
        self.btn_filtro_pagados.setText(f"Pagados ({n_pagados})")
        self.btn_filtro_alertas.setText(f"Con Alertas ({n_alertas})")

    # -----------------------------------------------------------------------
    # Filtros y Búsqueda
    # -----------------------------------------------------------------------
    def _al_clic_filtro(self, clave: str) -> None:
        self._filtro_estado = clave
        self.proxy.set_filtro_estado(clave)
        self._desactivar_estado_btn_excel()

        # Actualizar estilo de chips
        chips = [
            self.btn_filtro_todos,
            self.btn_filtro_pendientes,
            self.btn_filtro_dos_meses,
            self.btn_filtro_corte,
            self.btn_filtro_pagados,
            self.btn_filtro_alertas,
        ]
        for btn in chips:
            activo = (btn.property("filtro_clave") == clave)
            btn.setProperty("activo", "true" if activo else "false")
            # El chip de alertas lleva ícono: blanco cuando está activo, ámbar si no
            iconos.recolorear(btn, "blanco" if activo else "aviso")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        if self.proxy.rowCount() > 0:
            self.tabla.selectRow(0)
        else:
            self._limpiar_ficha()

    def _al_cambiar_sector(self) -> None:
        sec = self.combo_sector.currentData() or "todos"
        self.proxy.set_filtro_sector(sec)
        if self.proxy.rowCount() > 0:
            self.tabla.selectRow(0)
        else:
            self._limpiar_ficha()

    def _ejecutar_busqueda(self) -> None:
        txt = self.input_buscar.text().strip()
        self.proxy.set_texto_filtro(txt)
        if self.proxy.rowCount() > 0:
            self.tabla.selectRow(0)
        else:
            self._limpiar_ficha()

    # -----------------------------------------------------------------------
    # Ficha del Usuario Seleccionado
    # -----------------------------------------------------------------------
    def _al_seleccionar_fila(self) -> None:
        indexes = self.tabla.selectionModel().selectedRows()
        if not indexes:
            self._limpiar_ficha()
            return

        proxy_index = indexes[0]
        if not proxy_index.isValid():
            self._limpiar_ficha()
            return
        source_index = self.proxy.mapToSource(proxy_index)
        if not source_index.isValid():
            self._limpiar_ficha()
            return
        doc = self.modelo.obtener_item(source_index.row())
        if not doc:
            self._limpiar_ficha()
            return

        self.item_seleccionado = doc
        self._actualizar_ficha(doc)

    def _actualizar_ficha(self, doc: Dict[str, Any]) -> None:
        nom = doc.get("nombre") or "—"
        dni = doc.get("id_usuario") or doc.get("_id") or "—"

        self.lbl_ficha_nombre.setText(nom)
        self.lbl_ficha_dni.setText(f"DNI: {dni}")

        raw_meds = doc.get("medidores") or []
        meds_txt = ", ".join(m.get("nro_medidor", "") if isinstance(
            m, dict) else str(m) for m in raw_meds) or "Sin medidor"
        self.lbl_ficha_medidores.setText(f"Medidores: {meds_txt}")

        # Alerta de medidor
        alertas = []
        for m in raw_meds:
            if isinstance(m, dict):
                nov = str(m.get("novedad") or "").strip()
                nota = str(m.get("nota") or "").strip()
                if nov and nov != "NORMAL":
                    alertas.append(f"Medidor {m.get('nro_medidor')}: {nov}")
                if nota:
                    alertas.append(f"Nota: {nota}")
        if alertas:
            self.lbl_texto_alerta_medidor.setText("\n".join(alertas))
            self.box_alerta_medidor.show()
        else:
            self.box_alerta_medidor.hide()

        # Desglose de cuenta
        tot = float(doc.get("total_a_pagar") or 0.0)
        pag = float(doc.get("monto_pagado") or 0.0)
        deuda_ant = float(doc.get("deuda_anterior") or 0.0)
        cargo_fijo = float(doc.get("cargo_fijo") or 0.0)
        monto_agua = float(doc.get("monto_agua") or 0.0)
        meses = int(doc.get("meses_adeudados") or 1)
        tiene_recibo = bool(doc.get("nro_recibo"))
        esta_pagado = (pag >= tot and tot > 0.0)

        self.lbl_ficha_deuda_ant.setText(
            f"Deuda anterior: S/. {deuda_ant:,.2f}")
        self.lbl_ficha_mes_actual.setText(
            f"Consumo mes: S/. {monto_agua:,.2f}")
        self.lbl_ficha_cargo_fijo.setText(f"Cargo fijo: S/. {cargo_fijo:,.2f}")
        self.lbl_ficha_total.setText(f"Total a pagar: S/. {tot:,.2f}")

        # Badge de Mora
        if not tiene_recibo:
            self.lbl_ficha_badge_mora.setText("Sin Facturar")
            self.lbl_ficha_badge_mora.setStyleSheet(
                "background-color: #f1f5f9; color: #475569; font-weight: bold; padding: 6px; border-radius: 6px;"
            )
        elif esta_pagado:
            self.lbl_ficha_badge_mora.setText("Pagado")
            self.lbl_ficha_badge_mora.setStyleSheet(
                "background-color: #dcfce7; color: #166534; font-weight: bold; padding: 6px; border-radius: 6px;"
            )
        elif meses >= 3:
            self.lbl_ficha_badge_mora.setText(
                f"CORTE — {meses} meses sin pagar")
            self.lbl_ficha_badge_mora.setStyleSheet(
                "background-color: #fee2e2; color: #991b1b; font-weight: bold; padding: 6px; border-radius: 6px;"
            )
        elif meses == 2:
            self.lbl_ficha_badge_mora.setText("2 Meses adeudados")
            self.lbl_ficha_badge_mora.setStyleSheet(
                "background-color: #ffedd5; color: #9a3412; font-weight: bold; padding: 6px; border-radius: 6px;"
            )
        else:
            self.lbl_ficha_badge_mora.setText("Pendiente (1 mes)")
            self.lbl_ficha_badge_mora.setStyleSheet(
                "background-color: #fef3c7; color: #92400e; font-weight: bold; padding: 6px; border-radius: 6px;"
            )

        # Reglas de habilitación de botones
        self.btn_marcar_pagado.setEnabled(not esta_pagado)
        self.btn_marcar_pagado.setVisible(not esta_pagado)
        if not tiene_recibo:
            self.btn_marcar_pagado.setText("Emitir y cobrar")
        else:
            self.btn_marcar_pagado.setText("Marcar como pagado")

        self.btn_anular_cobro.setEnabled(esta_pagado)
        self.btn_anular_cobro.setVisible(esta_pagado)

        self.btn_ver_recibo.setEnabled(True)
        self.btn_ver_recibo.setVisible(True)
        if tiene_recibo:
            self.btn_ver_recibo.setText("Imprimir / Descargar recibo PDF")
        else:
            self.btn_ver_recibo.setText("Emitir e imprimir PDF")

    def _limpiar_ficha(self) -> None:
        self.item_seleccionado = None
        self.lbl_ficha_nombre.setText("Selecciona una conexión")
        self.lbl_ficha_dni.setText("DNI: —")
        self.lbl_ficha_medidores.setText("Medidores: —")
        self.box_alerta_medidor.hide()
        self.lbl_ficha_badge_mora.setText("—")
        self.lbl_ficha_deuda_ant.setText("Deuda anterior: S/. 0.00")
        self.lbl_ficha_mes_actual.setText("Consumo mes: S/. 0.00")
        self.lbl_ficha_cargo_fijo.setText("Cargo fijo: S/. 0.00")
        self.lbl_ficha_total.setText("Total a pagar: S/. 0.00")
        self.btn_marcar_pagado.setEnabled(False)
        self.btn_anular_cobro.setEnabled(False)
        self.btn_ver_recibo.setEnabled(False)
        self.btn_ver_recibo.setText("Imprimir / Descargar recibo PDF")

    # -----------------------------------------------------------------------
    # Acciones de Cobro y Recibos
    # -----------------------------------------------------------------------
    def _accion_marcar_pagado(self) -> None:
        if not self.item_seleccionado:
            return

        uid = str(self.item_seleccionado.get(
            "id_usuario") or self.item_seleccionado.get("_id") or "")
        nom = self.item_seleccionado.get("nombre") or "Usuario"
        tiene_rec = bool(self.item_seleccionado.get("nro_recibo"))

        # Si aún no tiene recibo emitido, ofrecer emitir y cobrar en un solo paso
        if not tiene_rec:
            resp_emitir = QMessageBox.question(
                self,
                "Emitir Recibo y Cobrar",
                f"El usuario {nom} aún no tiene recibo emitido en este mes.\n\n"
                f"¿Deseas emitir su recibo y registrar el pago ahora?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if resp_emitir != QMessageBox.StandardButton.Yes:
                return
            try:
                doc = self.servicio.generar_recibo_usuario(
                    self.periodo_actual, uid)
                self.item_seleccionado.update(doc)
            except Exception as e:
                mostrar_dialogo_error(self, "Error al emitir recibo", str(e))
                return

        total = float(self.item_seleccionado.get("total_a_pagar") or 0.0)

        # Si figura con 0.00 pero tiene cargos del mes o deuda, recalcular automáticamente
        if total <= 0.0:
            monto_agua = float(self.item_seleccionado.get("monto_agua") or 0.0)
            cargo_fijo = float(self.item_seleccionado.get("cargo_fijo") or 0.0)
            deuda_ant = float(self.item_seleccionado.get("deuda_anterior") or 0.0)
            if round(monto_agua + cargo_fijo + deuda_ant, 2) > 0.0:
                try:
                    doc = self.servicio.generar_recibo_usuario(self.periodo_actual, uid)
                    self.item_seleccionado.update(doc)
                    total = float(self.item_seleccionado.get("total_a_pagar") or 0.0)
                except Exception:
                    pass

        resp = QMessageBox.question(
            self,
            "Confirmar Cobro",
            f"¿Registrar el pago completo de S/. {total:,.2f} para:\n\n{nom}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        try:
            doc_actualizado = self.servicio.registrar_pago(self.periodo_actual, uid, total)
            self.item_seleccionado.update(doc_actualizado)
            for d in self.lista_items_completa:
                if str(d.get("id_usuario") or d.get("_id") or "") == uid:
                    d.update(doc_actualizado)
                    break
            self._actualizar_ficha(self.item_seleccionado)
            self.modelo.notificar_cambio_usuario(uid)
            self.proxy.refrescar_filtros()
            self._actualizar_kpis_y_chips()
            self.toast.mostrar(
                f"Cobro de S/. {total:,.2f} registrado para {nom}.", "exito")
        except Exception as e:
            mostrar_dialogo_error(self, "Error al registrar cobro", str(e))

    def _accion_anular_cobro(self) -> None:
        if not self.item_seleccionado:
            return

        uid = str(self.item_seleccionado.get(
            "id_usuario") or self.item_seleccionado.get("_id") or "")
        nom = self.item_seleccionado.get("nombre") or "Usuario"

        resp = QMessageBox.question(
            self,
            "Anular Cobro",
            f"¿Seguro que deseas anular el pago registrado para:\n\n{nom}?\n\nLa cuenta volverá a estado pendiente.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        try:
            doc_actualizado = self.servicio.anular_pago(self.periodo_actual, uid)
            self.item_seleccionado.update(doc_actualizado)
            for d in self.lista_items_completa:
                if str(d.get("id_usuario") or d.get("_id") or "") == uid:
                    d.update(doc_actualizado)
                    break
            self._actualizar_ficha(self.item_seleccionado)
            self.modelo.notificar_cambio_usuario(uid)
            self.proxy.refrescar_filtros()
            self._actualizar_kpis_y_chips()
            self.toast.mostrar(
                f"Pago anulado. {nom} vuelve a estado pendiente.", "aviso")
        except Exception as e:
            mostrar_dialogo_error(self, "Error al anular cobro", str(e))

    def _accion_ver_recibo(self) -> None:
        """Abre el PDF del recibo del usuario seleccionado, listo para imprimir o descargar."""
        if not self.item_seleccionado:
            QMessageBox.information(
                self,
                "Seleccionar Usuario",
                "Por favor, selecciona una fila de la tabla para imprimir o descargar su recibo PDF.",
            )
            return

        uid = str(self.item_seleccionado.get(
            "id_usuario") or self.item_seleccionado.get("_id") or "")
        nom = self.item_seleccionado.get("nombre") or "Usuario"
        tiene_rec = bool(self.item_seleccionado.get("nro_recibo"))

        # Si aún no tiene recibo emitido, ofrecer emitirlo inmediatamente
        if not tiene_rec:
            resp = QMessageBox.question(
                self,
                "Emitir Recibo",
                f"El usuario {nom} aún no tiene un recibo emitido en este periodo.\n\n"
                f"¿Deseas emitir su recibo ahora para poder imprimirlo / descargarlo?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if resp != QMessageBox.StandardButton.Yes:
                return
            try:
                doc = self.servicio.generar_recibo_usuario(
                    self.periodo_actual, uid)
                self.item_seleccionado.update(doc)
                self._actualizar_ficha(self.item_seleccionado)
                self.modelo.notificar_cambio_usuario(uid)
                self.proxy.refrescar_filtros()
                self._actualizar_kpis_y_chips()
            except Exception as e:
                mostrar_dialogo_error(
                    self, "Error al generar recibo individual", str(e))
                return

        try:
            ruta_pdf = self.servicio.generar_pdf_recibo(
                self.periodo_actual, uid)
            if ruta_pdf and Path(ruta_pdf).exists():
                os.startfile(ruta_pdf)
                # Pop-up de 5 segundos en la esquina superior derecha
                self.toast.mostrar(f"Recibo PDF abierto: {nom}", "exito")
            else:
                QMessageBox.warning(
                    self, "Aviso", "No se pudo encontrar el archivo PDF generado.")
        except Exception as e:
            mostrar_dialogo_error(self, "Error al abrir recibo PDF", str(e))

    def _accion_guardar_recibo_como(self) -> None:
        """Permite guardar una copia del recibo PDF en la carpeta que el usuario elija (Descargar)."""
        if not self.item_seleccionado:
            QMessageBox.information(
                self,
                "Seleccionar Usuario",
                "Por favor, selecciona una fila de la tabla para descargar su recibo PDF.",
            )
            return

        uid = str(self.item_seleccionado.get(
            "id_usuario") or self.item_seleccionado.get("_id") or "")
        nom = self.item_seleccionado.get("nombre") or "Usuario"
        tiene_rec = bool(self.item_seleccionado.get("nro_recibo"))

        if not tiene_rec:
            resp = QMessageBox.question(
                self,
                "Emitir Recibo",
                f"El usuario {nom} aún no tiene un recibo emitido.\n\n"
                f"¿Deseas emitir su recibo ahora para poder descargarlo?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if resp != QMessageBox.StandardButton.Yes:
                return
            try:
                doc = self.servicio.generar_recibo_usuario(
                    self.periodo_actual, uid)
                self.item_seleccionado.update(doc)
                self._actualizar_ficha(self.item_seleccionado)
                self.modelo.notificar_cambio_usuario(uid)
                self.proxy.refrescar_filtros()
                self._actualizar_kpis_y_chips()
            except Exception as e:
                mostrar_dialogo_error(self, "Error al generar recibo", str(e))
                return

        try:
            ruta_pdf = self.servicio.generar_pdf_recibo(
                self.periodo_actual, uid)
            if not ruta_pdf or not Path(ruta_pdf).exists():
                QMessageBox.warning(
                    self, "Aviso", "No se encontró el archivo PDF para descargar.")
                return

            nro_rec = str(self.item_seleccionado.get("nro_recibo") or "000000")
            nombre_sugerido = f"Recibo_{self.periodo_actual}_{nro_rec}_{nom.replace(' ', '_')}.pdf"
            ruta_destino, _ = QFileDialog.getSaveFileName(
                self,
                "Guardar Recibo PDF Como...",
                str(rutas.ruta_recibos(self.periodo_actual) / nombre_sugerido),
                "Documentos PDF (*.pdf)",
            )
            if ruta_destino:
                import shutil
                shutil.copy2(ruta_pdf, ruta_destino)
                self.toast.mostrar(
                    f"Recibo guardado: {Path(ruta_destino).name}", "exito")
        except Exception as e:
            mostrar_dialogo_error(self, "Error al guardar recibo PDF", str(e))

    def _accion_generar_individual(self) -> None:
        if not self.item_seleccionado:
            return

        uid = str(self.item_seleccionado.get(
            "id_usuario") or self.item_seleccionado.get("_id") or "")
        nom = self.item_seleccionado.get("nombre") or "Usuario"

        try:
            doc = self.servicio.generar_recibo_usuario(
                self.periodo_actual, uid)
            self.item_seleccionado.update(doc)
            self._actualizar_ficha(self.item_seleccionado)
            self.modelo.notificar_cambio_usuario(uid)
            self.proxy.refrescar_filtros()
            self._actualizar_kpis_y_chips()
            self.toast.mostrar(
                f"Recibo N° {doc.get('nro_recibo')} emitido para {nom}.", "exito")
        except Exception as e:
            mostrar_dialogo_error(
                self, "Error al generar recibo individual", str(e))

    def _menu_contextual_tabla(self, pos) -> None:
        """Menú contextual con clic derecho sobre cualquier fila de la tabla."""
        index = self.tabla.indexAt(pos)
        if not index.isValid():
            return
        self.tabla.selectRow(index.row())
        doc = self.item_seleccionado
        if not doc:
            return

        menu = QMenu(self)
        nom = doc.get("nombre") or "Usuario"
        tiene_rec = bool(doc.get("nro_recibo"))
        tot = float(doc.get("total_a_pagar") or 0.0)
        pag = float(doc.get("monto_pagado") or 0.0)
        esta_pag = (pag >= tot and tot > 0.0)

        if not tiene_rec:
            act_emitir = menu.addAction(iconos.icono("receipt"), f"Emitir recibo a {nom}")
            act_emitir.triggered.connect(self._accion_generar_individual)
            act_cobrar = menu.addAction(iconos.icono("credit-card"), f"Emitir y cobrar S/. {tot:,.2f}")
            act_cobrar.triggered.connect(self._accion_marcar_pagado)
            act_ver = menu.addAction(iconos.icono("printer"), "Emitir e imprimir PDF")
            act_ver.triggered.connect(self._accion_ver_recibo)
        else:
            if not esta_pag:
                act_cobrar = menu.addAction(
                    iconos.icono("credit-card"), f"Marcar como pagado (S/. {tot:,.2f})")
                act_cobrar.triggered.connect(self._accion_marcar_pagado)
            else:
                act_anular = menu.addAction(iconos.icono("arrow-back-up"), f"Anular cobro de {nom}")
                act_anular.triggered.connect(self._accion_anular_cobro)
            act_ver = menu.addAction(iconos.icono("printer"), "Imprimir / Descargar recibo PDF")
            act_ver.triggered.connect(self._accion_ver_recibo)
            act_guardar = menu.addAction(
                iconos.icono("device-floppy"), "Guardar recibo PDF en otra carpeta...")
            act_guardar.triggered.connect(self._accion_guardar_recibo_como)

        menu.addSeparator()
        act_carpeta = menu.addAction(iconos.icono("folder-open"), "Abrir carpeta de recibos")
        act_carpeta.triggered.connect(self._abrir_carpeta_recibos)

        menu.exec(self.tabla.viewport().mapToGlobal(pos))

    def _abrir_carpeta_recibos(self) -> None:
        """Abre la carpeta Escritorio/recibos/<periodo> (se crea si no existe)."""
        try:
            dir_recibos = rutas.ruta_recibos(
                self.periodo_actual) if self.periodo_actual else rutas.ruta_recibos()
            os.startfile(str(dir_recibos))
        except Exception as e:
            mostrar_dialogo_error(
                self, "Error al abrir la carpeta de recibos", str(e))
