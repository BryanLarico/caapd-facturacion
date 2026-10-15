"""
ui/paginas/usuarios.py — Pantalla de Padrón de Usuarios para CAAPD Ispacas.

Réplica nativa y optimizada del padrón web:
- Tabla virtual sin paginación capaz de mostrar 800+ usuarios fluidamente.
- Búsqueda inteligente con debounce de 150 ms (codigos.buscar).
- Filtros rápidos por estado con contadores en tiempo real.
- Modales para nuevo usuario, edición y corrección de DNIs provisionales.
- Cero bloqueo de interfaz (operaciones en hilos de trabajo).
"""
from typing import Any, Dict, List, Optional
from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtWidgets import (
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
from ui.paginas.usuarios_dialogos import DialogoCorregirDni, DialogoUsuario
from ui.paginas.usuarios_modelo import ModeloUsuarios, ProxyUsuarios


class PaginaUsuarios(QWidget):
    """Pantalla completa de administración del padrón de usuarios."""

    def __init__(self, servicio_datos: ServicioDatos, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.servicio = servicio_datos
        self.thread_pool = QThreadPool.globalInstance()

        self.lista_usuarios_completa: List[Dict[str, Any]] = []
        self.config_actual: Dict[str, Any] = {}

        # Timer para el debounce de búsqueda (150 ms)
        self.timer_busqueda = QTimer(self)
        self.timer_busqueda.setSingleShot(True)
        self.timer_busqueda.setInterval(150)
        self.timer_busqueda.timeout.connect(self._ejecutar_busqueda)

        self._construir_ui()

    def _construir_ui(self) -> None:
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(28, 20, 28, 20)
        layout_principal.setSpacing(16)

        # 1. Encabezado de la página
        fila_encabezado = QHBoxLayout()
        col_titulos = QVBoxLayout()
        col_titulos.setSpacing(4)

        lbl_titulo = QLabel("Padrón de Usuarios")
        lbl_titulo.setObjectName("encabezado_titulo")
        col_titulos.addWidget(lbl_titulo)

        lbl_subtitulo = QLabel(
            "Gestión completa del padrón, medidores y corrección de documentos de identidad"
        )
        lbl_subtitulo.setObjectName("encabezado_subtitulo")
        col_titulos.addWidget(lbl_subtitulo)
        fila_encabezado.addLayout(col_titulos, stretch=1)

        # Indicador de carga
        self.indicador_carga = IndicadorCarga()
        fila_encabezado.addWidget(self.indicador_carga)

        # Botones de cabecera
        self.btn_nuevo = QPushButton("➕ Nuevo Usuario")
        self.btn_nuevo.setProperty("class", "boton boton_primario")
        self.btn_nuevo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_nuevo.clicked.connect(self.abrir_modal_nuevo)
        fila_encabezado.addWidget(self.btn_nuevo)

        self.btn_importar_excel = QPushButton("📥 Importar Excel")
        self.btn_importar_excel.setProperty("class", "boton boton_secundario")
        self.btn_importar_excel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_importar_excel.setToolTip("Cargar lecturas o usuarios desde un archivo Excel")
        self.btn_importar_excel.clicked.connect(self.abrir_modal_importar_excel)
        fila_encabezado.addWidget(self.btn_importar_excel)

        self.btn_actualizar = QPushButton("🔄 Actualizar")
        self.btn_actualizar.setProperty("class", "boton boton_secundario")
        self.btn_actualizar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_actualizar.setToolTip("Recargar padrón completo desde Firestore")
        self.btn_actualizar.clicked.connect(self.actualizar_padron)
        fila_encabezado.addWidget(self.btn_actualizar)

        layout_principal.addLayout(fila_encabezado)

        # 2. Alerta flash
        self.alerta_flash = AlertaWidget(mensaje="", tipo="info", cerrable=True)
        self.alerta_flash.hide()
        layout_principal.addWidget(self.alerta_flash)

        # 3. Tarjeta de Búsqueda y Filtros
        tarjeta_filtros = QFrame()
        tarjeta_filtros.setProperty("class", "tarjeta")
        l_filtros = QVBoxLayout(tarjeta_filtros)
        l_filtros.setContentsMargins(16, 14, 16, 14)
        l_filtros.setSpacing(12)

        # Buscador inteligente
        fila_busqueda = QHBoxLayout()
        fila_busqueda.setSpacing(8)

        self.campo_busqueda = QLineEdit()
        self.campo_busqueda.setObjectName("campo_busqueda")
        self.campo_busqueda.setPlaceholderText(
            "Buscar por medidor (ej. 3386), conexión (796), DNI o apellidos y nombres..."
        )
        self.campo_busqueda.textChanged.connect(self._al_cambiar_texto_busqueda)
        fila_busqueda.addWidget(self.campo_busqueda, stretch=1)

        self.btn_limpiar_busqueda = QPushButton("✖ Limpiar")
        self.btn_limpiar_busqueda.setProperty("class", "boton boton_secundario")
        self.btn_limpiar_busqueda.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_limpiar_busqueda.clicked.connect(self.limpiar_busqueda)
        self.btn_limpiar_busqueda.hide()
        fila_busqueda.addWidget(self.btn_limpiar_busqueda)

        l_filtros.addLayout(fila_busqueda)

        # Botones de Filtro (Pestañas de estado) y Contador
        fila_botones_filtro = QHBoxLayout()
        fila_botones_filtro.setSpacing(8)

        self.btn_filtro_todos = self._crear_boton_filtro("Todos (0)", "todos")
        self.btn_filtro_activos = self._crear_boton_filtro("Activos (0)", "activos")
        self.btn_filtro_inactivos = self._crear_boton_filtro("Inactivos (0)", "inactivos")
        self.btn_filtro_pendientes = self._crear_boton_filtro("⚠️ Pendientes de DNI (0)", "pendientes")

        fila_botones_filtro.addWidget(self.btn_filtro_todos)
        fila_botones_filtro.addWidget(self.btn_filtro_activos)
        fila_botones_filtro.addWidget(self.btn_filtro_inactivos)
        fila_botones_filtro.addWidget(self.btn_filtro_pendientes)
        fila_botones_filtro.addStretch(1)

        self.lbl_conteo_registros = QLabel("Mostrando 0 de 0 registros")
        self.lbl_conteo_registros.setStyleSheet("color: #64748b; font-size: 13px;")
        fila_botones_filtro.addWidget(self.lbl_conteo_registros)

        l_filtros.addLayout(fila_botones_filtro)
        layout_principal.addWidget(tarjeta_filtros)

        # 4. Tabla virtual de usuarios (QTableView)
        self.tabla = QTableView()
        self.tabla.setObjectName("tabla_usuarios")
        self.tabla.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setSortingEnabled(True)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.horizontalHeader().setStretchLastSection(False)
        self.tabla.horizontalHeader().setHighlightSections(False)
        self.tabla.doubleClicked.connect(self._al_doble_clic_fila)

        # Modelos
        self.modelo_base = ModeloUsuarios([])
        self.proxy_model = ProxyUsuarios()
        self.proxy_model.setSourceModel(self.modelo_base)
        self.tabla.setModel(self.proxy_model)

        self.tabla.selectionModel().selectionChanged.connect(self._al_cambiar_seleccion)

        # Ajuste inicial de anchos de columna
        h_header = self.tabla.horizontalHeader()
        h_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        h_header.resizeSection(0, 85)   # Conexión
        h_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        h_header.resizeSection(1, 115)  # DNI
        h_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        h_header.resizeSection(2, 230)  # Apellidos y Nombres (reducido ~40%)
        h_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        h_header.resizeSection(3, 140)  # Sector
        h_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        h_header.resizeSection(4, 150)  # Dirección
        h_header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)  # Medidores (toma todo el espacio libre para no cortarse)
        h_header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        h_header.resizeSection(6, 60)   # Cat.
        h_header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        h_header.resizeSection(7, 85)   # Estado

        layout_principal.addWidget(self.tabla, stretch=1)

        # 5. Barra de acciones sobre la selección
        fila_acciones = QHBoxLayout()
        fila_acciones.setSpacing(8)

        self.btn_accion_editar = QPushButton("✏️ Editar Usuario")
        self.btn_accion_editar.setProperty("class", "boton boton_secundario")
        self.btn_accion_editar.setEnabled(False)
        self.btn_accion_editar.clicked.connect(self._accion_editar)
        fila_acciones.addWidget(self.btn_accion_editar)

        self.btn_accion_corregir = QPushButton("🆔 Corregir DNI")
        self.btn_accion_corregir.setProperty("class", "boton boton_aviso")
        self.btn_accion_corregir.setEnabled(False)
        self.btn_accion_corregir.clicked.connect(self._accion_corregir_dni)
        fila_acciones.addWidget(self.btn_accion_corregir)

        self.btn_accion_estado = QPushButton("⏸️ Cambiar Estado")
        self.btn_accion_estado.setProperty("class", "boton boton_secundario")
        self.btn_accion_estado.setEnabled(False)
        self.btn_accion_estado.clicked.connect(self._accion_cambiar_estado)
        fila_acciones.addWidget(self.btn_accion_estado)

        fila_acciones.addStretch(1)
        layout_principal.addLayout(fila_acciones)

        # Activar filtro "todos" por defecto
        self._seleccionar_filtro("todos")

    def _crear_boton_filtro(self, texto: str, clave: str) -> QPushButton:
        btn = QPushButton(texto)
        btn.setProperty("class", "filtro_btn")
        btn.setProperty("clave", clave)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda checked=False, c=clave: self._seleccionar_filtro(c))
        return btn

    def cargar_datos_asincrono(self, forzar: bool = False) -> None:
        """Carga usuarios y configuración en segundo plano."""
        self.indicador_carga.iniciar("Cargando padrón...")
        self.btn_actualizar.setEnabled(False)

        def tarea() -> Any:
            cfg = self.servicio.cargar_config()
            users = self.servicio.cargar_usuarios(forzar=forzar)
            return cfg, users

        worker = Worker(tarea)
        worker.signals.resultado.connect(self._al_recibir_datos)
        worker.signals.error.connect(self._al_fallar_carga)
        worker.signals.finalizado.connect(self._al_finalizar_carga)
        self.thread_pool.start(worker)

    def actualizar_padron(self) -> None:
        """Fuerza la recarga limpiando caché."""
        self.servicio.limpiar_cache(limpiar_config=False)
        self.cargar_datos_asincrono(forzar=True)

    def _al_recibir_datos(self, resultado: Any) -> None:
        cfg, users_dict = resultado
        self.config_actual = cfg or {}

        # Procesar lista de usuarios enriquecida
        lista = []
        for uid, u in users_dict.items():
            doc = dict(u)
            doc["_id"] = uid
            doc["id_usuario"] = uid
            doc["es_pendiente"] = codigos.es_id_pendiente(uid)
            lista.append(doc)

        # Orden inicial por número de conexión
        def clave_con(x):
            c = str(x.get("nro_conexion") or "")
            return int(c) if c.isdigit() else 999999

        lista.sort(key=clave_con)
        self.lista_usuarios_completa = lista

        self.modelo_base.actualizar_datos(lista)
        self._actualizar_contadores()
        self._actualizar_conteo_visibles()

    def _al_fallar_carga(self, err_msg: str) -> None:
        self.alerta_flash.set_mensaje(f"Error al cargar usuarios: {err_msg}", "peligro")
        mostrar_dialogo_error(self, "Error al cargar padrón", err_msg)

    def _al_finalizar_carga(self) -> None:
        self.indicador_carga.detener()
        self.btn_actualizar.setEnabled(True)

    def _actualizar_contadores(self) -> None:
        total = len(self.lista_usuarios_completa)
        activos = sum(1 for u in self.lista_usuarios_completa if u.get("activo", True))
        inactivos = total - activos
        pendientes = sum(1 for u in self.lista_usuarios_completa if u.get("es_pendiente"))

        self.btn_filtro_todos.setText(f"Todos ({total})")
        self.btn_filtro_activos.setText(f"Activos ({activos})")
        self.btn_filtro_inactivos.setText(f"Inactivos ({inactivos})")
        self.btn_filtro_pendientes.setText(f"⚠️ Pendientes de DNI ({pendientes})")

        if pendientes > 0:
            self.btn_filtro_pendientes.setProperty("class", "filtro_btn filtro_btn_aviso")
        else:
            self.btn_filtro_pendientes.setProperty("class", "filtro_btn")
        self.btn_filtro_pendientes.style().unpolish(self.btn_filtro_pendientes)
        self.btn_filtro_pendientes.style().polish(self.btn_filtro_pendientes)

    def _seleccionar_filtro(self, clave: str) -> None:
        botones = [
            ("todos", self.btn_filtro_todos),
            ("activos", self.btn_filtro_activos),
            ("inactivos", self.btn_filtro_inactivos),
            ("pendientes", self.btn_filtro_pendientes),
        ]
        for c, btn in botones:
            activo_val = "true" if c == clave else "false"
            btn.setProperty("activo", activo_val)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        self.proxy_model.set_filtro_estado(clave)
        self._actualizar_conteo_visibles()

    def _al_cambiar_texto_busqueda(self, texto: str) -> None:
        self.btn_limpiar_busqueda.setVisible(bool(texto))
        # Reiniciar debounce de 150 ms
        self.timer_busqueda.start()

    def _ejecutar_busqueda(self) -> None:
        q = self.campo_busqueda.text().strip()
        if not q:
            self.proxy_model.set_ids_busqueda(None)
        else:
            # Búsqueda inteligente con codigos.buscar
            encontrados = codigos.buscar(q, self.lista_usuarios_completa)
            ids_set = {str(u.get("id_usuario") or u.get("_id") or "") for u in encontrados}
            self.proxy_model.set_ids_busqueda(ids_set)

        self._actualizar_conteo_visibles()

    def limpiar_busqueda(self) -> None:
        self.campo_busqueda.clear()
        self.proxy_model.set_ids_busqueda(None)
        self._actualizar_conteo_visibles()
        self.campo_busqueda.setFocus()

    def _actualizar_conteo_visibles(self) -> None:
        visibles = self.proxy_model.rowCount()
        total = len(self.lista_usuarios_completa)
        self.lbl_conteo_registros.setText(f"Mostrando {visibles} de {total} registros")

    def _al_cambiar_seleccion(self) -> None:
        seleccion = self.tabla.selectionModel().selectedRows()
        hay_sel = len(seleccion) > 0
        self.btn_accion_editar.setEnabled(hay_sel)

        if hay_sel:
            proxy_idx = seleccion[0]
            source_row = self.proxy_model.mapToSource(proxy_idx).row()
            u = self.modelo_base.obtener_usuario(source_row)
            if u:
                es_pend = bool(u.get("es_pendiente"))
                self.btn_accion_corregir.setEnabled(es_pend)
                es_act = bool(u.get("activo", True))
                self.btn_accion_estado.setEnabled(True)
                self.btn_accion_estado.setText("⏸️ Desactivar" if es_act else "▶️ Activar")
                return

        self.btn_accion_corregir.setEnabled(False)
        self.btn_accion_estado.setEnabled(False)

    def _obtener_usuario_seleccionado(self) -> Optional[Dict[str, Any]]:
        seleccion = self.tabla.selectionModel().selectedRows()
        if not seleccion:
            return None
        proxy_idx = seleccion[0]
        source_row = self.proxy_model.mapToSource(proxy_idx).row()
        return self.modelo_base.obtener_usuario(source_row)

    def _al_doble_clic_fila(self, proxy_index) -> None:
        source_row = self.proxy_model.mapToSource(proxy_index).row()
        u = self.modelo_base.obtener_usuario(source_row)
        if u:
            self._abrir_modal_editar(u)

    def abrir_modal_nuevo(self) -> None:
        dialogo = DialogoUsuario(
            servicio_datos=self.servicio,
            config=self.config_actual,
            usuario=None,
            parent=self,
        )
        if dialogo.exec() == DialogoUsuario.DialogCode.Accepted:
            self.alerta_flash.set_mensaje("Usuario registrado exitosamente en el padrón.", "exito")
            self.cargar_datos_asincrono(forzar=True)

    def _abrir_modal_editar(self, usuario: Dict[str, Any]) -> None:
        dialogo = DialogoUsuario(
            servicio_datos=self.servicio,
            config=self.config_actual,
            usuario=usuario,
            parent=self,
        )
        if dialogo.exec() == DialogoUsuario.DialogCode.Accepted:
            self.alerta_flash.set_mensaje(
                f"Usuario '{usuario.get('nombre')}' actualizado correctamente.", "exito"
            )
            self.cargar_datos_asincrono(forzar=True)

    def _accion_editar(self) -> None:
        u = self._obtener_usuario_seleccionado()
        if u:
            self._abrir_modal_editar(u)

    def _accion_corregir_dni(self) -> None:
        u = self._obtener_usuario_seleccionado()
        if not u:
            return
        dialogo = DialogoCorregirDni(
            servicio_datos=self.servicio,
            usuario=u,
            parent=self,
        )
        if dialogo.exec() == DialogoCorregirDni.DialogCode.Accepted:
            self.alerta_flash.set_mensaje(
                f"DNI de '{u.get('nombre')}' corregido exitosamente.", "exito"
            )
            self.cargar_datos_asincrono(forzar=True)

    def _accion_cambiar_estado(self) -> None:
        u = self._obtener_usuario_seleccionado()
        if not u:
            return
        id_usuario = str(u.get("id_usuario") or u.get("_id", ""))
        nombre = u.get("nombre", "")
        estado_actual = bool(u.get("activo", True))
        nuevo_estado = not estado_actual

        accion_str = "desactivar" if estado_actual else "activar"
        resp = QMessageBox.question(
            self,
            f"Confirmar {accion_str}",
            f"¿Está seguro de que desea {accion_str} al abonado:\n\n{nombre} (ID: {id_usuario})?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if resp == QMessageBox.StandardButton.Yes:
            try:
                self.servicio.actualizar_usuario(id_usuario, {"activo": nuevo_estado})
                estado_txt = "activado" if nuevo_estado else "desactivado"
                self.alerta_flash.set_mensaje(
                    f"Abonado '{nombre}' {estado_txt} correctamente.", "info"
                )
                self.cargar_datos_asincrono(forzar=True)
            except Exception as e:
                mostrar_dialogo_error(self, "Error al cambiar estado", str(e))

    def abrir_modal_importar_excel(self) -> None:
        from ui.paginas.importar_mes_dialogo import DialogoImportarMesExcel
        diag = DialogoImportarMesExcel(self.servicio, self)
        if diag.exec() == QMessageBox.DialogCode.Accepted:
            self.cargar_datos_asincrono(forzar=True)
