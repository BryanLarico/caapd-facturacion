"""
ui/paginas/lectores.py — Pantalla de gestión de lectores móviles autorizados en Firebase Auth.

Permite:
- Listar los usuarios registrados en Firebase Authentication.
- Crear nuevas cuentas de lectores con correo, contraseña y nombre.
- Modificar el nombre o reestablecer contraseñas de lectores.
- Activar o desactivar lectores (sin borrar su historial ni sus lecturas previas).
- Eliminar cuentas obsoletas con diálogo de confirmación.
- Cero bloqueo de interfaz (todas las operaciones corren en segundo plano con Worker).
"""
from __future__ import annotations
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

from servicios.datos import ServicioDatos
from ui.componentes.alerta import AlertaWidget
from ui.componentes.dialogo_confirmar import pedir_confirmacion
from ui.componentes.indicador_carga import IndicadorCarga
from ui.hilos import Worker, mostrar_dialogo_error
from ui.paginas.lectores_dialogos import DialogoLector
from ui.paginas.lectores_modelo import ModeloLectores, ProxyLectores


class PaginaLectores(QWidget):
    """Pantalla completa de administración de lectores móviles."""

    def __init__(self, servicio_datos: ServicioDatos, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.servicio = servicio_datos
        self.thread_pool = QThreadPool.globalInstance()

        self.lista_lectores_completa: List[Dict[str, Any]] = []
        self._carga_en_curso = False

        # Temporizador para debounce del buscador
        self.timer_busqueda = QTimer(self)
        self.timer_busqueda.setSingleShot(True)
        self.timer_busqueda.setInterval(150)
        self.timer_busqueda.timeout.connect(self._ejecutar_busqueda)

        self._filtro_activo = "todos"

        self._construir_ui()

    def _construir_ui(self) -> None:
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(28, 24, 28, 20)
        layout_principal.setSpacing(16)

        # 1. Barra de Encabezado
        fila_encabezado = QHBoxLayout()
        col_titulos = QVBoxLayout()
        col_titulos.setSpacing(4)

        lbl_titulo = QLabel("📱 Lectores Móviles")
        lbl_titulo.setObjectName("encabezado_titulo")
        col_titulos.addWidget(lbl_titulo)

        lbl_subtitulo = QLabel(
            "Gestión de accesos y cuentas para la aplicación móvil Android de toma de lecturas"
        )
        lbl_subtitulo.setObjectName("encabezado_subtitulo")
        col_titulos.addWidget(lbl_subtitulo)

        fila_encabezado.addLayout(col_titulos)
        fila_encabezado.addStretch(1)

        self.btn_nuevo = QPushButton("➕ Nuevo Lector")
        self.btn_nuevo.setProperty("class", "boton boton_primario")
        self.btn_nuevo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_nuevo.clicked.connect(self.abrir_modal_nuevo)
        fila_encabezado.addWidget(self.btn_nuevo)

        self.btn_actualizar = QPushButton("🔄 Actualizar")
        self.btn_actualizar.setProperty("class", "boton boton_secundario")
        self.btn_actualizar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_actualizar.setToolTip("Recargar lista de lectores desde Firebase Auth")
        self.btn_actualizar.clicked.connect(lambda: self.cargar_datos_asincrono(forzar=True))
        fila_encabezado.addWidget(self.btn_actualizar)

        layout_principal.addLayout(fila_encabezado)

        # 2. Alerta flash
        self.alerta_flash = AlertaWidget(mensaje="", tipo="info", cerrable=True)
        self.alerta_flash.hide()
        layout_principal.addWidget(self.alerta_flash)

        # 3. Tarjeta de Filtros y Búsqueda
        tarjeta_filtros = QFrame()
        tarjeta_filtros.setProperty("class", "tarjeta")
        l_filtros = QVBoxLayout(tarjeta_filtros)
        l_filtros.setContentsMargins(16, 14, 16, 14)
        l_filtros.setSpacing(12)

        # Buscador
        fila_busqueda = QHBoxLayout()
        fila_busqueda.setSpacing(8)

        self.campo_busqueda = QLineEdit()
        self.campo_busqueda.setObjectName("campo_busqueda")
        self.campo_busqueda.setPlaceholderText("Buscar lector por correo, nombre o UID...")
        self.campo_busqueda.textChanged.connect(self._al_cambiar_texto_busqueda)
        fila_busqueda.addWidget(self.campo_busqueda, stretch=1)

        self.btn_limpiar_busqueda = QPushButton("✖ Limpiar")
        self.btn_limpiar_busqueda.setProperty("class", "boton boton_secundario")
        self.btn_limpiar_busqueda.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_limpiar_busqueda.clicked.connect(self.limpiar_busqueda)
        self.btn_limpiar_busqueda.hide()
        fila_busqueda.addWidget(self.btn_limpiar_busqueda)

        l_filtros.addLayout(fila_busqueda)

        # Filtros de estado
        fila_botones_filtro = QHBoxLayout()
        fila_botones_filtro.setSpacing(8)

        self.btn_filtro_todos = self._crear_boton_filtro("Todos (0)", "todos")
        self.btn_filtro_activos = self._crear_boton_filtro("Activos (0)", "activos")
        self.btn_filtro_deshabilitados = self._crear_boton_filtro("Deshabilitados (0)", "deshabilitados")

        fila_botones_filtro.addWidget(self.btn_filtro_todos)
        fila_botones_filtro.addWidget(self.btn_filtro_activos)
        fila_botones_filtro.addWidget(self.btn_filtro_deshabilitados)
        fila_botones_filtro.addStretch(1)

        self.lbl_conteo_registros = QLabel("Mostrando 0 de 0 lectores")
        self.lbl_conteo_registros.setStyleSheet("color: #64748b; font-size: 13px;")
        fila_botones_filtro.addWidget(self.lbl_conteo_registros)

        l_filtros.addLayout(fila_botones_filtro)
        layout_principal.addWidget(tarjeta_filtros)

        # 4. Tabla de Lectores
        self.tabla = QTableView()
        self.tabla.setObjectName("tabla_lectores")
        self.tabla.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setSortingEnabled(True)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.horizontalHeader().setStretchLastSection(False)
        self.tabla.horizontalHeader().setHighlightSections(False)
        self.tabla.doubleClicked.connect(self._al_doble_clic_fila)

        # Modelos
        self.modelo_base = ModeloLectores([])
        self.proxy_model = ProxyLectores()
        self.proxy_model.setSourceModel(self.modelo_base)
        self.tabla.setModel(self.proxy_model)

        self.tabla.selectionModel().selectionChanged.connect(self._al_cambiar_seleccion)

        # Anchos de columna
        h_header = self.tabla.horizontalHeader()
        h_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        h_header.resizeSection(0, 260)  # Correo
        h_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        h_header.resizeSection(1, 230)  # Nombre
        h_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        h_header.resizeSection(2, 120)  # Estado
        h_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        h_header.resizeSection(3, 140)  # Último acceso
        h_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)  # UID

        layout_principal.addWidget(self.tabla, stretch=1)

        # 5. Barra Inferior de Acciones Contextuales
        fila_inferior = QHBoxLayout()
        fila_inferior.setSpacing(10)

        self.btn_accion_editar = QPushButton("✏️ Editar Lector")
        self.btn_accion_editar.setProperty("class", "boton boton_secundario")
        self.btn_accion_editar.setEnabled(False)
        self.btn_accion_editar.clicked.connect(self._accion_editar)
        fila_inferior.addWidget(self.btn_accion_editar)

        self.btn_accion_cambiar_estado = QPushButton("⏸️ Desactivar")
        self.btn_accion_cambiar_estado.setProperty("class", "boton boton_secundario")
        self.btn_accion_cambiar_estado.setEnabled(False)
        self.btn_accion_cambiar_estado.clicked.connect(self._accion_cambiar_estado)
        fila_inferior.addWidget(self.btn_accion_cambiar_estado)

        # Indicador de carga integrado inline en la misma barra inferior
        self.indicador_carga = IndicadorCarga()
        self.indicador_carga.hide()
        fila_inferior.addWidget(self.indicador_carga)

        fila_inferior.addStretch(1)

        self.btn_accion_eliminar = QPushButton("🗑️ Eliminar Lector")
        self.btn_accion_eliminar.setProperty("class", "boton boton_peligro")
        self.btn_accion_eliminar.setEnabled(False)
        self.btn_accion_eliminar.clicked.connect(self._accion_eliminar)
        fila_inferior.addWidget(self.btn_accion_eliminar)

        layout_principal.addLayout(fila_inferior)

        # Establecer filtro inicial
        self._seleccionar_filtro("todos")

    def _crear_boton_filtro(self, texto: str, clave: str) -> QPushButton:
        btn = QPushButton(texto)
        btn.setProperty("class", "filtro_btn")
        btn.setProperty("clave", clave)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda checked=False, c=clave: self._seleccionar_filtro(c))
        return btn

    def cargar_datos_asincrono(self, forzar: bool = False) -> None:
        """Carga lectores desde Firebase Auth cuando se abre o actualiza esta página."""
        if self._carga_en_curso:
            return

        self._carga_en_curso = True
        self.indicador_carga.iniciar("Cargando lectores autorizados...")
        self.btn_actualizar.setEnabled(False)

        def tarea() -> Any:
            return self.servicio.listar_lectores()

        worker = Worker(tarea)
        worker.signals.resultado.connect(self._al_recibir_datos)
        worker.signals.error.connect(self._al_fallar_carga)
        worker.signals.finalizado.connect(self._al_finalizar_carga)
        self.thread_pool.start(worker)

    def _al_recibir_datos(self, resultado: Any) -> None:
        lectores = list(resultado or [])
        self.lista_lectores_completa = [
            lector for lector in lectores if self._tiene_correo(lector)
        ]
        omitidos = len(lectores) - len(self.lista_lectores_completa)
        if omitidos:
            self.alerta_flash.set_mensaje(
                f"Se ocultaron {omitidos} registros sin correo válido. "
                "No se modificaron ni eliminaron esos datos.",
                "aviso",
            )
        else:
            self.alerta_flash.hide()

        self.modelo_base.actualizar_datos(self.lista_lectores_completa)
        self._actualizar_contadores_y_etiqueta()
        self._al_cambiar_seleccion()

    @staticmethod
    def _tiene_correo(lector: Any) -> bool:
        if isinstance(lector, str):
            correo = lector.strip()
        elif isinstance(lector, dict):
            correo = str(lector.get("email") or "").strip()
        else:
            return False

        if correo.count("@") != 1 or any(caracter.isspace() for caracter in correo):
            return False
        usuario, dominio = correo.split("@")
        return bool(usuario and dominio)

    def _al_fallar_carga(self, err: str) -> None:
        self.alerta_flash.set_mensaje(f"Error al cargar lectores: {err}", "peligro")
        mostrar_dialogo_error(self, "Error al cargar lectores", str(err))

    def _al_finalizar_carga(self) -> None:
        self._carga_en_curso = False
        self.indicador_carga.detener()
        self.btn_actualizar.setEnabled(True)

    def _al_cambiar_texto_busqueda(self, texto: str) -> None:
        self.btn_limpiar_busqueda.setVisible(bool(texto))
        self.timer_busqueda.start()

    def _ejecutar_busqueda(self) -> None:
        texto = self.campo_busqueda.text()
        self.proxy_model.set_texto_filtro(texto)
        self._actualizar_etiqueta_conteo()

    def limpiar_busqueda(self) -> None:
        self.campo_busqueda.clear()
        self.btn_limpiar_busqueda.hide()
        self.proxy_model.set_texto_filtro("")
        self._actualizar_etiqueta_conteo()

    def _seleccionar_filtro(self, clave: str) -> None:
        self._filtro_activo = clave
        botones = [
            self.btn_filtro_todos,
            self.btn_filtro_activos,
            self.btn_filtro_deshabilitados,
        ]
        for b in botones:
            activo = b.property("clave") == clave
            b.setProperty("activo", "true" if activo else "false")
            b.style().unpolish(b)
            b.style().polish(b)

        self.proxy_model.set_filtro_estado(clave)
        self._actualizar_etiqueta_conteo()

    def _actualizar_contadores_y_etiqueta(self) -> None:
        total = len(self.lista_lectores_completa)
        deshabilitados = sum(1 for l in self.lista_lectores_completa if l.get("disabled"))
        activos = total - deshabilitados

        self.btn_filtro_todos.setText(f"Todos ({total})")
        self.btn_filtro_activos.setText(f"Activos ({activos})")
        self.btn_filtro_deshabilitados.setText(f"Deshabilitados ({deshabilitados})")

        self._actualizar_etiqueta_conteo()

    def _actualizar_etiqueta_conteo(self) -> None:
        visibles = self.proxy_model.rowCount()
        total = len(self.lista_lectores_completa)
        self.lbl_conteo_registros.setText(f"Mostrando {visibles} de {total} lectores")

    def _al_cambiar_seleccion(self) -> None:
        indexes = self.tabla.selectionModel().selectedRows()
        hay_seleccion = len(indexes) > 0

        self.btn_accion_editar.setEnabled(hay_seleccion)
        self.btn_accion_cambiar_estado.setEnabled(hay_seleccion)
        self.btn_accion_eliminar.setEnabled(hay_seleccion)

        if hay_seleccion:
            lector = self._obtener_lector_seleccionado()
            if lector:
                esta_deshabilitado = bool(lector.get("disabled", False))
                self.btn_accion_cambiar_estado.setText("▶️ Activar" if esta_deshabilitado else "⏸️ Desactivar")
        else:
            self.btn_accion_cambiar_estado.setText("⏸️ Desactivar")

    def _obtener_lector_seleccionado(self) -> Optional[Dict[str, Any]]:
        indexes = self.tabla.selectionModel().selectedRows()
        if not indexes:
            return None
        proxy_idx = indexes[0]
        source_idx = self.proxy_model.mapToSource(proxy_idx)
        return self.modelo_base.obtener_lector(source_idx.row())

    def _al_doble_clic_fila(self, index) -> None:
        lector = self._obtener_lector_seleccionado()
        if lector:
            self._abrir_modal_editar(lector)

    def abrir_modal_nuevo(self) -> None:
        diag = DialogoLector(self.servicio, lector=None, parent=self)
        if diag.exec() == QMessageBox.DialogCode.Accepted:
            self.alerta_flash.set_mensaje("Lector creado exitosamente en Firebase Auth.", "exito")
            self.cargar_datos_asincrono(forzar=True)

    def _abrir_modal_editar(self, lector: Dict[str, Any]) -> None:
        diag = DialogoLector(self.servicio, lector=lector, parent=self)
        if diag.exec() == QMessageBox.DialogCode.Accepted:
            self.alerta_flash.set_mensaje(
                f"Datos del lector '{lector.get('email')}' actualizados correctamente.", "exito"
            )
            self.cargar_datos_asincrono(forzar=True)

    def _accion_editar(self) -> None:
        l = self._obtener_lector_seleccionado()
        if l:
            self._abrir_modal_editar(l)

    def _accion_cambiar_estado(self) -> None:
        l = self._obtener_lector_seleccionado()
        if not l:
            return
        uid = l.get("uid", "")
        email = l.get("email", "")
        estado_actual = bool(l.get("disabled", False))
        nuevo_disabled = not estado_actual

        # 1. Actualización optimista inmediata en memoria (0 ms, sin bloqueos)
        l["disabled"] = nuevo_disabled
        self.modelo_base.actualizar_lector_en_fila(uid, {"disabled": nuevo_disabled})
        self._actualizar_contadores_y_etiqueta()
        self._al_cambiar_seleccion()

        estado_txt = "desactivada" if nuevo_disabled else "activada"
        self.alerta_flash.set_mensaje(
            f"Cuenta de '{email}' {estado_txt} correctamente.", "exito"
        )

        # 2. Sincronización en segundo plano con Firebase Auth
        def tarea() -> Any:
            return self.servicio.actualizar_lector(uid=uid, disabled=nuevo_disabled)

        def al_terminar(res) -> None:
            # Sincronización completada silenciosa y exitosa
            pass

        def al_error(err: str) -> None:
            # Revertir el estado optimista ante cualquier fallo de conexión
            l["disabled"] = estado_actual
            self.modelo_base.actualizar_lector_en_fila(uid, {"disabled": estado_actual})
            self._actualizar_contadores_y_etiqueta()
            self._al_cambiar_seleccion()
            self.alerta_flash.set_mensaje(
                f"No se pudo sincronizar el cambio con Firebase: {err}", "peligro"
            )
            mostrar_dialogo_error(
                self,
                "Error de Sincronización",
                f"No se pudo {'desactivar' if nuevo_disabled else 'activar'} la cuenta en Firebase:\n\n{err}",
            )

        worker = Worker(tarea)
        worker.signals.resultado.connect(al_terminar)
        worker.signals.error.connect(al_error)
        self.thread_pool.start(worker)

    def _accion_eliminar(self) -> None:
        l = self._obtener_lector_seleccionado()
        if not l:
            return
        uid = l.get("uid", "")
        email = l.get("email", "")

        confirmado = pedir_confirmacion(
            parent=self,
            titulo="Eliminar Cuenta de Lector",
            mensaje_principal="¿Está seguro de ELIMINAR permanentemente a este lector?",
            detalle=f"Cuenta: {email}\n\nEsta acción borrará la cuenta en Firebase Authentication de forma definitiva. No se puede deshacer.",
            texto_confirmar="Eliminar Cuenta",
            texto_cancelar="Cancelar",
            es_peligro=True,
        )
        if not confirmado:
            return

        # 1. Actualización optimista inmediata en interfaz (0 ms)
        lector_respaldo = dict(l)
        self.lista_lectores_completa = [x for x in self.lista_lectores_completa if x.get("uid") != uid]
        self.modelo_base.eliminar_lector_por_uid(uid)
        self._actualizar_contadores_y_etiqueta()
        self._al_cambiar_seleccion()
        self.alerta_flash.set_mensaje(f"Cuenta '{email}' eliminada.", "info")

        # 2. Eliminación en segundo plano en Firebase Auth
        def tarea() -> Any:
            self.servicio.eliminar_lector(uid)
            return True

        def al_terminar(_) -> None:
            pass

        def al_error(err: str) -> None:
            # Revertir si falló en Firebase
            self.lista_lectores_completa.append(lector_respaldo)
            self.modelo_base.actualizar_datos(self.lista_lectores_completa)
            self._actualizar_contadores_y_etiqueta()
            self._al_cambiar_seleccion()
            self.alerta_flash.set_mensaje(f"Error al eliminar en Firebase: {err}", "peligro")
            mostrar_dialogo_error(self, "Error al eliminar lector", str(err))

        worker = Worker(tarea)
        worker.signals.resultado.connect(al_terminar)
        worker.signals.error.connect(al_error)
        self.thread_pool.start(worker)
