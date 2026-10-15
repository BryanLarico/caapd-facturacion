"""
ui/paginas/lecturas.py — Pantalla de Lecturas del mes para CAAPD Ispacas.

Funcionalidades de Fase 3:
- Pestañas por sector con indicador de avance (leídos / total).
- Filtros rápidos por estado (Todos, Faltan por leer, Sin acceso, Con observación).
- Búsqueda inteligente con debounce de 150 ms (codigos.buscar).
- Tabla virtual estilizada con medidores individuales.
- Diálogo de corrección de lecturas con validación de alertas (negativo, > 100 m³, 3x histórico).
- Acciones de ciclo de vida: Cerrar lecturas, Reabrir lecturas y Abrir mes nuevo.
- Cero congelamientos (carga en hilos secundarios).
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

import codigos
from servicios.datos import ServicioDatos
from ui.componentes.alerta import AlertaWidget
from ui.componentes.indicador_carga import IndicadorCarga
from ui.hilos import Worker, mostrar_dialogo_error
from ui.paginas.lecturas_dialogo import DialogoLectura
from ui.paginas.lecturas_modelo import ModeloLecturas, ProxyLecturas
from ui.paginas.mes_dialogo import DialogoAbrirMes


class PaginaLecturas(QWidget):
    """Pantalla completa de consulta, auditoría y corrección de lecturas del mes."""

    def __init__(self, servicio_datos: ServicioDatos, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.servicio = servicio_datos
        self.thread_pool = QThreadPool.globalInstance()

        self.lista_items_completa: List[Dict[str, Any]] = []
        self.config_actual: Dict[str, Any] = {}
        self.periodo_actual: Optional[str] = None
        self.estado_mes: str = "ABIERTO"

        # Debounce de 150 ms para búsqueda
        self.timer_busqueda = QTimer(self)
        self.timer_busqueda.setSingleShot(True)
        self.timer_busqueda.setInterval(150)
        self.timer_busqueda.timeout.connect(self._ejecutar_busqueda)

        self._construir_ui()

    def _construir_ui(self) -> None:
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(28, 20, 28, 20)
        layout_principal.setSpacing(14)

        # 1. Encabezado principal
        fila_encabezado = QHBoxLayout()
        col_titulos = QVBoxLayout()
        col_titulos.setSpacing(4)

        self.lbl_titulo = QLabel("Lecturas del mes")
        self.lbl_titulo.setObjectName("encabezado_titulo")
        col_titulos.addWidget(self.lbl_titulo)

        self.lbl_subtitulo = QLabel("Registro y validación de consumos de agua potable")
        self.lbl_subtitulo.setObjectName("encabezado_subtitulo")
        col_titulos.addWidget(self.lbl_subtitulo)
        fila_encabezado.addLayout(col_titulos, stretch=1)

        # Indicador de carga
        self.indicador_carga = IndicadorCarga()
        fila_encabezado.addWidget(self.indicador_carga)

        # Botón Cerrar / Reabrir lecturas
        self.btn_estado_mes = QPushButton("🔒 Cerrar lecturas")
        self.btn_estado_mes.setProperty("class", "boton boton_secundario")
        self.btn_estado_mes.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_estado_mes.clicked.connect(self._alternar_estado_lecturas)
        fila_encabezado.addWidget(self.btn_estado_mes)

        # Botón Abrir mes nuevo
        self.btn_abrir_mes = QPushButton("📅 Abrir mes nuevo")
        self.btn_abrir_mes.setProperty("class", "boton boton_exito")
        self.btn_abrir_mes.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_abrir_mes.clicked.connect(self._abrir_modal_mes)
        fila_encabezado.addWidget(self.btn_abrir_mes)

        # Botón Actualizar
        self.btn_actualizar = QPushButton("🔄 Actualizar")
        self.btn_actualizar.setProperty("class", "boton boton_secundario")
        self.btn_actualizar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_actualizar.clicked.connect(self.actualizar_datos)
        fila_encabezado.addWidget(self.btn_actualizar)

        layout_principal.addLayout(fila_encabezado)

        # 2. Alerta flash
        self.alerta_flash = AlertaWidget(mensaje="", tipo="info", cerrable=True)
        self.alerta_flash.hide()
        layout_principal.addWidget(self.alerta_flash)

        # 3. Banner de estado del mes activo / sin mes
        self.banner_mes = QFrame()
        self.banner_mes.setObjectName("banner_info_lecturas")
        self.banner_mes.setProperty("estado", "activo")
        layout_banner = QHBoxLayout(self.banner_mes)
        layout_banner.setContentsMargins(8, 6, 8, 6)

        self.lbl_info_mes = QLabel("Periodo activo: <b>Cargando...</b>")
        self.lbl_info_mes.setObjectName("info_mes_lecturas")
        self.lbl_info_mes.setProperty("estado", "activo")
        layout_banner.addWidget(self.lbl_info_mes, stretch=1)

        self.lbl_avance_total = QLabel("Avance general: 0 de 0 (0%)")
        self.lbl_avance_total.setObjectName("avance_lecturas")
        layout_banner.addWidget(self.lbl_avance_total)

        layout_principal.addWidget(self.banner_mes)

        # 4. Pestañas de Sectores
        self.contenedor_sectores = QWidget()
        self.layout_sectores = QHBoxLayout(self.contenedor_sectores)
        self.layout_sectores.setContentsMargins(0, 0, 0, 0)
        self.layout_sectores.setSpacing(8)
        layout_principal.addWidget(self.contenedor_sectores)

        # 5. Barra de búsqueda y Filtros de Estado
        fila_filtros = QHBoxLayout()
        fila_filtros.setSpacing(12)

        # Buscador inteligente
        self.campo_busqueda = QLineEdit()
        self.campo_busqueda.setObjectName("campo_busqueda")
        self.campo_busqueda.setPlaceholderText("🔍 Buscar por medidor, conexión, DNI o nombre...")
        self.campo_busqueda.setClearButtonEnabled(True)
        self.campo_busqueda.setMinimumWidth(320)
        self.campo_busqueda.textChanged.connect(self._al_cambiar_busqueda)
        fila_filtros.addWidget(self.campo_busqueda, stretch=2)

        # Filtros rápidos por estado
        self.btn_filtro_todos = self._crear_boton_filtro("Todos (0)", "todos")
        self.btn_filtro_faltan = self._crear_boton_filtro("⏳ Faltan (0)", "faltan")
        self.btn_filtro_observados = self._crear_boton_filtro("⚠️ Con observación (0)", "con_observacion")

        fila_filtros.addWidget(self.btn_filtro_todos)
        fila_filtros.addWidget(self.btn_filtro_faltan)
        fila_filtros.addWidget(self.btn_filtro_observados)
        fila_filtros.addStretch(1)

        layout_principal.addLayout(fila_filtros)

        # 6. Tabla de lecturas
        self.modelo_base = ModeloLecturas()
        self.proxy_model = ProxyLecturas(self)
        self.proxy_model.setSourceModel(self.modelo_base)

        self.tabla = QTableView()
        self.tabla.setObjectName("tabla_lecturas")
        self.tabla.setModel(self.proxy_model)
        self.tabla.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setSortingEnabled(True)
        self.tabla.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(40)
        self.tabla.setWordWrap(False)
        self.tabla.doubleClicked.connect(self._al_doble_clic_fila)

        # Ajuste de cabeceras
        header = self.tabla.horizontalHeader()
        for column in (0, 1, 3, 4, 5, 6, 7, 8):
            header.setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(10, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(9, 125)
        header.resizeSection(10, 145)

        layout_principal.addWidget(self.tabla, stretch=1)

        # 7. Barra de estado inferior y botones contextuales
        fila_acciones = QHBoxLayout()
        self.lbl_conteo_registros = QLabel("Mostrando 0 registros")
        self.lbl_conteo_registros.setObjectName("conteo_registros_lecturas")
        fila_acciones.addWidget(self.lbl_conteo_registros)

        fila_acciones.addStretch(1)

        self.btn_accion_editar = QPushButton("✏️ Corregir lectura")
        self.btn_accion_editar.setProperty("class", "boton boton_primario")
        self.btn_accion_editar.setEnabled(False)
        self.btn_accion_editar.clicked.connect(self._editar_seleccionado)
        fila_acciones.addWidget(self.btn_accion_editar)

        layout_principal.addLayout(fila_acciones)

        # Conectar selección de tabla
        self.tabla.selectionModel().selectionChanged.connect(self._al_cambiar_seleccion)

        # Activar filtro "todos"
        self._seleccionar_filtro_estado("todos")

    def _crear_boton_filtro(self, texto: str, clave: str) -> QPushButton:
        btn = QPushButton(texto)
        btn.setProperty("class", "filtro_btn")
        btn.setProperty("clave", clave)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda checked=False, c=clave: self._seleccionar_filtro_estado(c))
        return btn

    def cargar_datos_asincrono(self, forzar: bool = False) -> None:
        """Carga en segundo plano la configuración y los documentos del mes activo."""
        self.indicador_carga.iniciar("Cargando lecturas...")
        self.btn_actualizar.setEnabled(False)

        def tarea() -> Any:
            cfg = self.servicio.cargar_config()
            mes_actual = cfg.get("mes_actual") or {}
            periodo = mes_actual.get("periodo")
            mes_dict = {}
            if periodo:
                mes_dict = self.servicio.cargar_mes(periodo)
            return cfg, periodo, mes_dict

        worker = Worker(tarea)
        worker.signals.resultado.connect(self._al_recibir_datos)
        worker.signals.error.connect(self._al_fallar_carga)
        worker.signals.finalizado.connect(self._al_finalizar_carga)
        self.thread_pool.start(worker)

    def actualizar_datos(self) -> None:
        """Actualiza la pantalla desde el padrón local, sube a Firebase o descarga de lectores móviles."""
        if getattr(self.servicio, "es_local_first", False):
            from ui.componentes.dialogo_actualizar import DialogoActualizarBaseDatos
            dlg = DialogoActualizarBaseDatos(self, servicio=self.servicio)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

            ventana = self.window()

            if dlg.resultado_accion == DialogoActualizarBaseDatos.ACCION_LOCAL:
                if hasattr(ventana, "mostrar_progreso"):
                    ventana.mostrar_progreso(50, "Recargando padrón local...")
                self.cargar_datos_asincrono(forzar=True)
                if hasattr(ventana, "ocultar_progreso"):
                    ventana.ocultar_progreso("¡Padrón local recargado!")
                return

            elif dlg.resultado_accion == DialogoActualizarBaseDatos.ACCION_SUBIR_FIREBASE:
                self.indicador_carga.iniciar("Enviando mes a lectores...")
                self.btn_actualizar.setEnabled(False)

                def progreso_callback(pct, txt):
                    if hasattr(ventana, "mostrar_progreso"):
                        ventana.mostrar_progreso(pct, txt)

                def tarea_subir():
                    return self.servicio.enviar_mes_a_lectores(callback_progreso=progreso_callback)

                def al_terminar_subida(res):
                    if hasattr(ventana, "ocultar_progreso"):
                        ventana.ocultar_progreso("¡Mes enviado a los lectores!")
                    self.cargar_datos_asincrono(forzar=True)
                    QMessageBox.information(
                        self,
                        "Envío a Lectores Completado",
                        f"¡Mes {res.get('periodo', '')} enviado exitosamente a Firebase!\n\n"
                        f"• {res.get('usuarios_subidos', 0)} documentos de usuario subidos en lote.\n"
                        f"• {res.get('sobrantes_borrados', 0)} documentos obsoletos/sobrantes eliminados.\n"
                        f"• ⏱️ Tiempo total de sincronización: {res.get('tiempo_segundos', 0)} s.",
                    )

                worker = Worker(tarea_subir)
                worker.signals.resultado.connect(al_terminar_subida)
                worker.signals.error.connect(self._al_fallar_carga)
                self.thread_pool.start(worker)
                return

            elif dlg.resultado_accion == DialogoActualizarBaseDatos.ACCION_DESCARGAR_FIREBASE:
                self.indicador_carga.iniciar("Descargando lecturas de lectores...")
                self.btn_actualizar.setEnabled(False)

                def progreso_callback(pct, txt):
                    if hasattr(ventana, "mostrar_progreso"):
                        ventana.mostrar_progreso(pct, txt)

                def tarea_sync():
                    return self.servicio.traer_lecturas_de_lectores(callback_progreso=progreso_callback)

                def al_terminar_descarga(res):
                    if hasattr(ventana, "ocultar_progreso"):
                        ventana.ocultar_progreso("¡Lecturas descargadas!")
                    self.cargar_datos_asincrono(forzar=True)

                    conflictos = res.get("conflictos_admin") or []
                    info_extra = ""
                    if conflictos:
                        info_extra = (
                            f"\n\n⚠️ Se detectaron {len(conflictos)} conflicto(s) con lecturas de ADMIN:\n"
                            + "\n".join(f"  • {c['nombre']} (Medidor {c['nro_medidor']}): ADMIN={c['lectura_admin']} vs Lector={c['lectura_cloud']} (se mantuvo ADMIN)" for c in conflictos[:5])
                        )
                    QMessageBox.information(
                        self,
                        "Descarga de Lecturas Completada",
                        f"¡Descarga finalizada con éxito!\n\n"
                        f"• {res.get('actualizados', 0)} lectura(s) actualizada(s) en Excel.\n"
                        f"• ⏱️ Tiempo total de descarga: {res.get('tiempo_segundos', 0)} s."
                        f"{info_extra}",
                    )

                worker = Worker(tarea_sync)
                worker.signals.resultado.connect(al_terminar_descarga)
                worker.signals.error.connect(self._al_fallar_carga)
                self.thread_pool.start(worker)
                return

        self.servicio.limpiar_cache(limpiar_config=True)
        self.cargar_datos_asincrono(forzar=True)

    def _al_recibir_datos(self, resultado: Any) -> None:
        cfg, periodo, mes_dict = resultado
        self.config_actual = cfg or {}
        self.periodo_actual = periodo

        mes_act = self.config_actual.get("mes_actual") or {}
        self.estado_mes = (mes_act.get("estado") or "ABIERTO").upper()

        if not periodo or not mes_dict:
            # No hay mes activo o está vacío
            self._establecer_estado_banner("sin_mes")
            self.lbl_info_mes.setText("⚠️ <b>No hay un mes activo</b>. Haz clic en 'Abrir mes nuevo' para iniciar.")
            self.lbl_avance_total.setText("")
            self.btn_estado_mes.setEnabled(False)
            puede_abrir, motivo, _ = self.servicio.verificar_puede_abrir_mes()
            self.btn_abrir_mes.setEnabled(puede_abrir)
            self.btn_abrir_mes.setToolTip("" if puede_abrir else motivo)
            self.lista_items_completa = []
            self.modelo_base.actualizar_datos([])
            self._construir_pestanas_sectores([])
            self._actualizar_contadores()
            return

        # Hay mes activo
        emision = mes_act.get("fecha_emision") or "—"
        venc = mes_act.get("fecha_vencimiento") or "—"
        self._establecer_estado_banner("activo")
        self.lbl_info_mes.setText(
            f"Periodo: <b>{periodo}</b> &nbsp;·&nbsp; Estado: <b>{self.estado_mes}</b> &nbsp;·&nbsp; "
            f"Emisión: {emision} &nbsp;·&nbsp; Vencimiento: {venc}"
        )
        puede_abrir, motivo, _ = self.servicio.verificar_puede_abrir_mes()
        self.btn_abrir_mes.setEnabled(puede_abrir)
        self.btn_abrir_mes.setToolTip("" if puede_abrir else motivo)

        # Botón de estado del mes
        if self.estado_mes == "ABIERTO":
            self.btn_estado_mes.setText("🔒 Cerrar lecturas")
            self.btn_estado_mes.setEnabled(True)
        elif self.estado_mes == "CERRADO":
            self.btn_estado_mes.setText("🔓 Reabrir lecturas")
            self.btn_estado_mes.setEnabled(True)
        else:
            self.btn_estado_mes.setText("Mes facturado")
            self.btn_estado_mes.setEnabled(False)

        # Aplanar medidores a filas individuales para la tabla
        filas = []
        for uid, doc in mes_dict.items():
            meds = doc.get("medidores") or []
            for m in meds:
                filas.append(
                    {
                        "id_usuario": uid,
                        "nro_conexion": doc.get("nro_conexion", ""),
                        "nombre": doc.get("nombre", ""),
                        "sector": doc.get("sector", ""),
                        "direccion": doc.get("direccion", ""),
                        "codigo_categoria": doc.get("codigo_categoria", "A"),
                        "historial_m3": doc.get("historial_m3", []),
                        "nro_medidor": m.get("nro_medidor", ""),
                        "lectura_anterior": m.get("lectura_anterior"),
                        "lectura_actual": m.get("lectura_actual"),
                        "fecha_anterior": m.get("fecha_anterior"),
                        "fecha_lectura": m.get("fecha_lectura"),
                        "estado_lectura": m.get("estado_lectura", "PENDIENTE"),
                        "novedad": m.get("novedad", ""),
                        "nota": m.get("nota", ""),
                        "registrado_por": m.get("registrado_por"),
                        "es_pendiente": codigos.es_id_pendiente(uid),
                    }
                )

        # Ordenar por conexión numéricamente
        def clave_con(x):
            c = str(x.get("nro_conexion") or "")
            return int(c) if c.isdigit() else 999999

        filas.sort(key=clave_con)
        self.lista_items_completa = filas

        self.modelo_base.actualizar_datos(filas)
        self._construir_pestanas_sectores(filas)
        self._actualizar_contadores()
        self._actualizar_conteo_visibles()

    def _establecer_estado_banner(self, estado: str) -> None:
        for widget in (self.banner_mes, self.lbl_info_mes):
            widget.setProperty("estado", estado)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()

    def _al_fallar_carga(self, err_msg: str) -> None:
        self.alerta_flash.set_mensaje(f"Error al cargar lecturas: {err_msg}", "peligro")
        mostrar_dialogo_error(self, "Error al cargar lecturas", err_msg)

    def _al_finalizar_carga(self) -> None:
        self.indicador_carga.detener()
        self.btn_actualizar.setEnabled(True)

    def _construir_pestanas_sectores(self, filas: List[Dict[str, Any]]) -> None:
        """Crea botones de pestaña por cada sector con contadores (leídos/total)."""
        while self.layout_sectores.count():
            item = self.layout_sectores.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        sectores_cfg = self.config_actual.get("sectores") or [
            "BARRIO DE CHAUPI", "BARRIO DE PACHAYZA", "BARRIO DE LUCMANI",
            "HUAQUILLO", "CHAUPICERCA", "AYACUCHO"
        ]

        # Botón "Todos"
        total_m = len(filas)
        leidos_m = sum(1 for f in filas if f.get("estado_lectura") == "LEIDO")
        btn_todos = QPushButton(f"Todos los sectores ({leidos_m}/{total_m})")
        btn_todos.setProperty("class", "filtro_btn filtro_btn_activo")
        btn_todos.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_todos.clicked.connect(lambda: self._seleccionar_sector("todos", btn_todos))
        self.layout_sectores.addWidget(btn_todos)
        self.btn_sector_activo = btn_todos

        for s in sectores_cfg:
            tot_s = sum(1 for f in filas if str(f.get("sector")).upper() == s.upper())
            lei_s = sum(1 for f in filas if str(f.get("sector")).upper() == s.upper() and f.get("estado_lectura") == "LEIDO")
            btn_s = QPushButton(f"{s} ({lei_s}/{tot_s})")
            btn_s.setProperty("class", "filtro_btn")
            btn_s.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_s.clicked.connect(lambda checked=False, sec=s, b=btn_s: self._seleccionar_sector(sec, b))
            self.layout_sectores.addWidget(btn_s)

        self.layout_sectores.addStretch(1)

        # Actualizar banner de avance
        pct = (leidos_m / total_m * 100) if total_m > 0 else 0
        self.lbl_avance_total.setText(f"Avance general: {leidos_m} de {total_m} ({pct:.1f}%)")

    def _seleccionar_sector(self, sector: str, btn: QPushButton) -> None:
        for i in range(self.layout_sectores.count()):
            w = self.layout_sectores.itemAt(i).widget()
            if isinstance(w, QPushButton):
                w.setProperty("class", "filtro_btn")
                w.style().unpolish(w)
                w.style().polish(w)

        btn.setProperty("class", "filtro_btn filtro_btn_activo")
        btn.style().unpolish(btn)
        btn.style().polish(btn)

        self.proxy_model.set_filtro_sector(sector)
        self._actualizar_conteo_visibles()

    def _seleccionar_filtro_estado(self, clave: str) -> None:
        botones = [
            ("todos", self.btn_filtro_todos),
            ("faltan", self.btn_filtro_faltan),
            ("con_observacion", self.btn_filtro_observados),
        ]
        for c, btn in botones:
            if c == clave:
                btn.setProperty("class", "filtro_btn filtro_btn_activo")
            else:
                btn.setProperty("class", "filtro_btn")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        self.proxy_model.set_filtro_estado(clave)
        self._actualizar_conteo_visibles()

    def _actualizar_contadores(self) -> None:
        total = len(self.lista_items_completa)
        faltan = sum(
            1 for f in self.lista_items_completa
            if str(f.get("estado_lectura") or "PENDIENTE").upper() != "LEIDO"
        )
        obs = sum(
            1 for f in self.lista_items_completa
            if (f.get("novedad") and f.get("novedad") != "NORMAL") or f.get("nota")
        )

        self.btn_filtro_todos.setText(f"Todos ({total})")
        self.btn_filtro_faltan.setText(f"⏳ Faltan ({faltan})")
        self.btn_filtro_observados.setText(f"⚠️ Con observación ({obs})")

    def _al_cambiar_busqueda(self, texto: str) -> None:
        self.timer_busqueda.start()

    def _ejecutar_busqueda(self) -> None:
        q = self.campo_busqueda.text().strip()
        if not q:
            self.proxy_model.set_ids_permitidos(None)
        else:
            # codigos.buscar sobre lista_items_completa
            encontrados = codigos.buscar(q, self.lista_items_completa)
            ids_set = {str(item.get("id_usuario")) for item in encontrados}
            self.proxy_model.set_ids_permitidos(ids_set)
        self._actualizar_conteo_visibles()

    def _actualizar_conteo_visibles(self) -> None:
        visibles = self.proxy_model.rowCount()
        total = len(self.lista_items_completa)
        self.lbl_conteo_registros.setText(f"Mostrando {visibles} de {total} medidores")

    def _al_cambiar_seleccion(self) -> None:
        hay_sel = len(self.tabla.selectionModel().selectedRows()) > 0
        self.btn_accion_editar.setEnabled(hay_sel)

    def _al_doble_clic_fila(self, index) -> None:
        self._editar_seleccionado()

    def _editar_seleccionado(self) -> None:
        filas = self.tabla.selectionModel().selectedRows()
        if not filas:
            return

        idx = filas[0]
        source_idx = self.proxy_model.mapToSource(idx)
        item = self.modelo_base.obtener_item(source_idx.row())
        if not item or not self.periodo_actual:
            return

        diag = DialogoLectura(
            servicio=self.servicio,
            periodo=self.periodo_actual,
            item=item,
            config=self.config_actual,
            parent=self,
        )
        if diag.exec() == QMessageBox.DialogCode.Accepted:
            self.actualizar_datos()

    def _alternar_estado_lecturas(self) -> None:
        if not self.periodo_actual:
            return

        if self.estado_mes == "ABIERTO":
            # Verificar cuántos quedan pendientes
            faltan = sum(1 for f in self.lista_items_completa if f.get("estado_lectura") != "LEIDO")
            msg = (
                f"¿Deseas cerrar el periodo de lecturas para {self.periodo_actual}?\n\n"
                f"• Medidores sin lectura completa: {faltan}\n\n"
                "Al cerrar, la app móvil dejará de aceptar lecturas."
            )
            resp = QMessageBox.question(
                self,
                "Cerrar lecturas",
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if resp == QMessageBox.StandardButton.Yes:
                self.indicador_carga.iniciar("Cerrando lecturas...")
                self.thread_pool.start(Worker(lambda: self.servicio.cerrar_lecturas(self.periodo_actual)))
                QTimer.singleShot(1000, self.actualizar_datos)

        elif self.estado_mes == "CERRADO":
            resp = QMessageBox.question(
                self,
                "Reabrir lecturas",
                f"¿Deseas reabrir las lecturas para {self.periodo_actual}?\n\n"
                "La app móvil volverá a recibir registros.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if resp == QMessageBox.StandardButton.Yes:
                self.indicador_carga.iniciar("Reabriendo lecturas...")
                self.thread_pool.start(Worker(lambda: self.servicio.reabrir_lecturas(self.periodo_actual)))
                QTimer.singleShot(1000, self.actualizar_datos)

    def _abrir_modal_mes(self) -> None:
        diag = DialogoAbrirMes(self.servicio, self)
        if diag.exec() == QMessageBox.DialogCode.Accepted:
            self.actualizar_datos()
