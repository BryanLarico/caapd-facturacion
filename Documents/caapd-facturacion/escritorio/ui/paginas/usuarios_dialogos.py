"""
ui/paginas/usuarios_dialogos.py — Diálogos modales para gestión de usuarios.

Incluye:
- DialogoUsuario: Crear y editar usuario con gestión dinámica de medidores.
- DialogoCorregirDni: Reasignar DNI real a personas con ID provisional.
- DialogoDetalleUsuario: Vista detallada de la ficha de un abonado.
"""
from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import codigos
from servicios.datos import ServicioDatos
from ui.hilos import mostrar_dialogo_aviso, mostrar_dialogo_error


class DialogoUsuario(QDialog):
    """Diálogo modal para agregar o editar un usuario del padrón."""

    def __init__(
        self,
        servicio_datos: ServicioDatos,
        config: Dict[str, Any],
        usuario: Optional[Dict[str, Any]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.servicio = servicio_datos
        self.config = config
        self.usuario = usuario
        self.es_edicion = usuario is not None
        self.id_original = str(self.usuario.get("id_usuario") or self.usuario.get(
            "_id") or "") if self.es_edicion else ""

        self.medidores_lista: List[str] = []

        self.setWindowTitle(
            "Editar Usuario" if self.es_edicion else "Nuevo Usuario")
        self.resize(540, 560)
        self.setModal(True)

        self._construir_ui()
        self._cargar_datos_iniciales()

    def _construir_ui(self) -> None:
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(24, 20, 24, 20)
        layout_principal.setSpacing(14)

        # Encabezado del diálogo
        titulo_txt = f"✏️ Editar Usuario: {self.usuario.get('nombre', '')}" if self.es_edicion else "➕ Registrar Nuevo Usuario"
        lbl_titulo = QLabel(titulo_txt)
        lbl_titulo.setObjectName("dialogo_titulo")
        layout_principal.addWidget(lbl_titulo)

        # Formulario
        # 1. DNI / ID
        layout_id = QVBoxLayout()
        layout_id.setSpacing(4)
        lbl_id = QLabel("DNI / Documento de Identidad:")
        lbl_id.setStyleSheet("font-weight: 500;")
        layout_id.addWidget(lbl_id)

        self.campo_id = QLineEdit()
        self.campo_id.setPlaceholderText("8 dígitos (ej. 30771072) o SD-xxx")
        self.campo_id.setMaxLength(12)
        layout_id.addWidget(self.campo_id)

        if not self.es_edicion:
            self.chk_sin_dni = QCheckBox(
                "Persona sin DNI (asignar ID provisional correlativo)")
            self.chk_sin_dni.setStyleSheet(
                "color: #1e293b; font-size: 13px; font-weight: 500;")
            self.chk_sin_dni.toggled.connect(self._toggle_sin_dni)
            layout_id.addWidget(self.chk_sin_dni)

        layout_principal.addLayout(layout_id)

        # 2. Conexión y Nombre
        fila_con = QHBoxLayout()
        col_con = QVBoxLayout()
        col_con.setSpacing(4)
        lbl_con = QLabel("N° de Conexión:")
        lbl_con.setStyleSheet("font-weight: 500;")
        col_con.addWidget(lbl_con)

        self.campo_conexion = QLineEdit()
        self.campo_conexion.setPlaceholderText("6 dígitos (ej. 000796)")
        self.campo_conexion.setMaxLength(6)
        col_con.addWidget(self.campo_conexion)
        fila_con.addLayout(col_con, stretch=1)

        layout_principal.addLayout(fila_con)

        col_nombre = QVBoxLayout()
        col_nombre.setSpacing(4)
        lbl_nom = QLabel("Apellidos y Nombres Completos:")
        lbl_nom.setStyleSheet("font-weight: 500;")
        col_nombre.addWidget(lbl_nom)

        self.campo_nombre = QLineEdit()
        self.campo_nombre.setPlaceholderText(
            "Ej. CONDORI MAMANI, CARLOS ALBERTO")
        col_nombre.addWidget(self.campo_nombre)
        layout_principal.addLayout(col_nombre)

        # 3. Sector y Categoría
        fila_sec_cat = QHBoxLayout()
        col_sec = QVBoxLayout()
        col_sec.setSpacing(4)
        lbl_sec = QLabel("Sector / Barrio:")
        lbl_sec.setStyleSheet("font-weight: 500;")
        col_sec.addWidget(lbl_sec)

        self.combo_sector = QComboBox()
        self.combo_sector.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents)
        sec_view = QListView()
        sec_view.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.combo_sector.setView(sec_view)
        sectores = self.config.get("sectores") or [
            "BARRIO DE CHAUPI", "BARRIO DE PACHAYZA", "BARRIO DE LUCMANI",
            "HUAQUILLO", "CHAUPICERCA", "AYACUCHO"
        ]
        self.combo_sector.addItems(sectores)
        col_sec.addWidget(self.combo_sector)
        fila_sec_cat.addLayout(col_sec, stretch=1)

        col_cat = QVBoxLayout()
        col_cat.setSpacing(4)
        lbl_cat = QLabel("Categoría:")
        lbl_cat.setStyleSheet("font-weight: 500;")
        col_cat.addWidget(lbl_cat)

        self.combo_categoria = QComboBox()
        self.combo_categoria.setMinimumWidth(180)
        self.combo_categoria.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents)
        cat_view = QListView()
        cat_view.setTextElideMode(Qt.TextElideMode.ElideNone)
        cat_view.setMinimumWidth(260)
        self.combo_categoria.setView(cat_view)

        nombres_defecto = {
            "A": "Doméstico / General",
            "B": "Comercial",
            "C": "Estatal / Social",
        }
        categorias_raw = self.config.get("categorias") or {}
        categorias = dict(categorias_raw) if isinstance(
            categorias_raw, dict) else {}

        # Garantizar que las 3 categorías estándar siempre existan con nombre
        for cod, nom_def in nombres_defecto.items():
            if cod not in categorias or not isinstance(categorias[cod], dict):
                categorias[cod] = {"nombre": nom_def}
            elif not categorias[cod].get("nombre"):
                categorias[cod]["nombre"] = nom_def

        for cod, datos in sorted(categorias.items()):
            nom = datos.get("nombre") if isinstance(
                datos, dict) else str(datos)
            if not nom:
                nom = nombres_defecto.get(cod, f"Categoría {cod}")
            self.combo_categoria.addItem(f"{cod} — {nom}", cod)

        col_cat.addWidget(self.combo_categoria)
        fila_sec_cat.addLayout(col_cat, stretch=1)

        layout_principal.addLayout(fila_sec_cat)

        # 4. Dirección
        col_dir = QVBoxLayout()
        col_dir.setSpacing(4)
        lbl_dir = QLabel("Dirección / Referencia:")
        lbl_dir.setStyleSheet("font-weight: 500;")
        col_dir.addWidget(lbl_dir)

        self.campo_direccion = QLineEdit()
        self.campo_direccion.setPlaceholderText("Ej. CALLE 05 DE AGOSTO S/N")
        col_dir.addWidget(self.campo_direccion)
        layout_principal.addLayout(col_dir)

        # 5. Medidores
        col_med = QVBoxLayout()
        col_med.setSpacing(6)
        lbl_med = QLabel("Medidores de Agua Asignados:")
        lbl_med.setStyleSheet("font-weight: 500;")
        col_med.addWidget(lbl_med)

        fila_add_med = QHBoxLayout()
        self.campo_nuevo_medidor = QLineEdit()
        self.campo_nuevo_medidor.setPlaceholderText(
            "N° de medidor (ej. 22392996)")
        self.campo_nuevo_medidor.returnPressed.connect(self._agregar_medidor)
        fila_add_med.addWidget(self.campo_nuevo_medidor, stretch=1)

        btn_add_med = QPushButton("➕ Añadir")
        btn_add_med.setProperty("class", "boton boton_secundario")
        btn_add_med.clicked.connect(self._agregar_medidor)
        fila_add_med.addWidget(btn_add_med)
        col_med.addLayout(fila_add_med)

        # Contenedor de chips de medidores
        self.contenedor_chips = QWidget()
        self.layout_chips = QHBoxLayout(self.contenedor_chips)
        self.layout_chips.setContentsMargins(0, 4, 0, 4)
        self.layout_chips.setSpacing(8)
        col_med.addWidget(self.contenedor_chips)

        layout_principal.addLayout(col_med)

        layout_principal.addStretch(1)

        # Botones de pie
        fila_botones = QHBoxLayout()
        fila_botones.addStretch(1)

        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setProperty("class", "boton boton_secundario")
        btn_cancelar.clicked.connect(self.reject)
        fila_botones.addWidget(btn_cancelar)

        btn_guardar = QPushButton("💾 Guardar Usuario")
        btn_guardar.setProperty("class", "boton boton_primario")
        btn_guardar.clicked.connect(self._guardar)
        fila_botones.addWidget(btn_guardar)

        layout_principal.addLayout(fila_botones)

    def _cargar_datos_iniciales(self) -> None:
        if self.es_edicion and self.usuario:
            self.campo_id.setText(str(self.usuario.get(
                "id_usuario") or self.usuario.get("_id") or ""))
            self.campo_conexion.setText(
                str(self.usuario.get("nro_conexion") or ""))
            self.campo_nombre.setText(str(self.usuario.get("nombre") or ""))
            self.campo_direccion.setText(
                str(self.usuario.get("direccion") or ""))

            # Sector
            sec = str(self.usuario.get("sector") or "")
            idx_sec = self.combo_sector.findText(sec)
            if idx_sec >= 0:
                self.combo_sector.setCurrentIndex(idx_sec)

            # Categoría
            cat = str(self.usuario.get("codigo_categoria") or "A")
            for i in range(self.combo_categoria.count()):
                if self.combo_categoria.itemData(i) == cat:
                    self.combo_categoria.setCurrentIndex(i)
                    break

            # Medidores
            meds = self.usuario.get("medidores") or []
            for m in meds:
                val = m if isinstance(m, str) else m.get("nro_medidor", "")
                if val and val not in self.medidores_lista:
                    self.medidores_lista.append(val)
            self._renderizar_chips_medidores()

        else:
            # Nuevo: sugerir conexión siguiente libre
            sug_con = self.servicio.obtener_siguiente_conexion_libre()
            self.campo_conexion.setText(sug_con)
            self._renderizar_chips_medidores()

    def _toggle_sin_dni(self, marcado: bool) -> None:
        if marcado:
            sug_sd = self.servicio.obtener_siguiente_id_sd()
            self.campo_id.setText(sug_sd)
            self.campo_id.setReadOnly(True)
        else:
            self.campo_id.setText("")
            self.campo_id.setReadOnly(False)

    def _agregar_medidor(self) -> None:
        txt = self.campo_nuevo_medidor.text().strip()
        if not txt:
            return
        med_norm = codigos.normalizar_medidor(txt)
        if med_norm not in self.medidores_lista:
            self.medidores_lista.append(med_norm)
            self._renderizar_chips_medidores()
        self.campo_nuevo_medidor.clear()
        self.campo_nuevo_medidor.setFocus()

    def _quitar_medidor(self, medidor: str) -> None:
        if medidor in self.medidores_lista:
            self.medidores_lista.remove(medidor)
            self._renderizar_chips_medidores()

    def _renderizar_chips_medidores(self) -> None:
        # Limpiar chips anteriores
        while self.layout_chips.count():
            item = self.layout_chips.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if not self.medidores_lista:
            lbl_vacio = QLabel("(Sin medidores asignados)")
            lbl_vacio.setStyleSheet(
                "color: #64748b; font-style: italic; font-size: 12px;")
            self.layout_chips.addWidget(lbl_vacio)
        else:
            for m in self.medidores_lista:
                chip = QFrame()
                chip.setProperty("class", "chip_medidor")
                l_chip = QHBoxLayout(chip)
                l_chip.setContentsMargins(6, 2, 6, 2)
                l_chip.setSpacing(6)

                lbl_m = QLabel(f"💧 {m}")
                lbl_m.setProperty("class", "chip_texto")
                l_chip.addWidget(lbl_m)

                btn_del = QPushButton("✕")
                btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_del.setStyleSheet(
                    "border: none; background: transparent; color: #dc2626; font-weight: bold;")
                btn_del.clicked.connect(
                    lambda ch=False, val=m: self._quitar_medidor(val))
                l_chip.addWidget(btn_del)

                self.layout_chips.addWidget(chip)

        self.layout_chips.addStretch(1)

    def _guardar(self) -> None:
        nuevo_id = self.campo_id.text().strip()
        nombre = self.campo_nombre.text().strip().upper()
        conexion = self.campo_conexion.text().strip()
        sector = self.combo_sector.currentText()
        cat_data = self.combo_categoria.currentData() or "A"
        direccion = self.campo_direccion.text().strip().upper()

        # Validaciones
        if not nombre:
            QMessageBox.warning(
                self, "Campo requerido", "Debe ingresar los apellidos y nombres completos.")
            self.campo_nombre.setFocus()
            return

        # 1. Determinar y validar ID
        id_final = ""
        if not self.es_edicion:
            sin_dni = getattr(self, "chk_sin_dni",
                              None) and self.chk_sin_dni.isChecked()
            if sin_dni or not nuevo_id:
                id_final = self.servicio.obtener_siguiente_id_sd()
            else:
                if nuevo_id.isdigit() and len(nuevo_id) in (7, 8):
                    id_final = codigos.normalizar_dni(nuevo_id)
                elif nuevo_id.startswith("SD-") or nuevo_id.isdigit():
                    id_final = nuevo_id
                else:
                    QMessageBox.warning(
                        self, "DNI inválido", "El DNI debe contener 7 u 8 dígitos, o tener formato SD-xxx.")
                    self.campo_id.setFocus()
                    return

            if self.servicio.obtener_usuario(id_final) is not None:
                QMessageBox.warning(
                    self, "ID ya registrado", f"Ya existe un usuario registrado con el DNI '{id_final}'."
                )
                self.campo_id.setFocus()
                return
        else:
            # Modo edición: si el usuario cambió el DNI / ID (ej. de SD-001 a DNI real)
            id_final = self.id_original
            if nuevo_id and nuevo_id != self.id_original:
                if nuevo_id.isdigit() and len(nuevo_id) in (7, 8):
                    norm_id = codigos.normalizar_dni(nuevo_id)
                elif nuevo_id.startswith("SD-") or nuevo_id.isdigit():
                    norm_id = nuevo_id
                else:
                    QMessageBox.warning(
                        self, "DNI inválido", "El nuevo DNI debe contener 7 u 8 dígitos, o tener formato SD-xxx.")
                    self.campo_id.setFocus()
                    return

                if self.servicio.obtener_usuario(norm_id) is not None:
                    QMessageBox.warning(
                        self, "ID ya registrado", f"Ya existe otro usuario registrado con el ID/DNI '{norm_id}'."
                    )
                    self.campo_id.setFocus()
                    return

                # Reasignar DNI en el padrón, mes y espejo Firebase
                try:
                    self.servicio.corregir_dni_usuario(
                        self.id_original, norm_id)
                    id_final = norm_id
                except Exception as e:
                    mostrar_dialogo_error(
                        self, "Error al cambiar DNI", f"No se pudo reasignar el DNI:\n{e}")
                    return

        # 2. Validar medidores únicos entre distintas personas
        valido, err_msg = self.servicio.validar_medidores_unicos(
            self.medidores_lista, id_usuario_actual=id_final
        )
        if not valido:
            QMessageBox.critical(self, "Medidor duplicado",
                                 err_msg or "Medidor ya asignado a otra persona.")
            return

        con_norm = codigos.normalizar_conexion(
            conexion) if conexion else self.servicio.obtener_siguiente_conexion_libre()
        activo_final = self.usuario.get(
            "activo", True) if self.es_edicion else True

        datos_guardar = {
            "nro_conexion": con_norm,
            "nombre": nombre,
            "sector": sector,
            "direccion": direccion,
            "codigo_categoria": cat_data,
            "activo": activo_final,
            "medidores": list(self.medidores_lista),
        }

        try:
            exito_sync = True
            err_sync = None
            if not self.es_edicion:
                res = self.servicio.guardar_usuario(
                    id_final, datos_guardar, agregar_al_mes=True)
            else:
                res = self.servicio.actualizar_usuario(id_final, datos_guardar)

            if isinstance(res, tuple):
                exito_sync, err_sync = res
            elif isinstance(res, dict):
                exito_sync = res.get("_sync_exito", True)
                err_sync = res.get("_sync_error")

            if not exito_sync and err_sync:
                mostrar_dialogo_aviso(
                    self,
                    "Aviso de sincronización",
                    "El usuario se guardó correctamente en el padrón local.\n\n"
                    "No se pudo enviar a Firebase ahora; se enviará con el próximo "
                    "'Enviar mes a los lectores'.\n\n"
                    "Pulse 'Mostrar detalles...' para ver el motivo técnico.",
                    detalle=err_sync,
                )
            self.accept()
        except Exception as e:
            mostrar_dialogo_error(self, "Error al guardar",
                                  f"No se pudo guardar el usuario:\n{e}")


class DialogoCorregirDni(QDialog):
    """Diálogo modal para reemplazar un ID provisional por el DNI definitivo de 8 dígitos."""

    def __init__(
        self,
        servicio_datos: ServicioDatos,
        usuario: Dict[str, Any],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.servicio = servicio_datos
        self.usuario = usuario

        self.setWindowTitle("Corregir Documento de Identidad")
        self.resize(460, 280)
        self.setModal(True)

        self._construir_ui()

    def _construir_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)

        lbl_titulo = QLabel("🆔 Corregir Documento de Identidad")
        lbl_titulo.setObjectName("dialogo_titulo")
        layout.addWidget(lbl_titulo)

        # Panel de aviso informativo
        alerta_frame = QFrame()
        alerta_frame.setStyleSheet(
            "background-color: #fef3c7; border-left: 4px solid #d97706; border-radius: 6px; padding: 10px;")
        l_alerta = QVBoxLayout(alerta_frame)
        l_alerta.setSpacing(4)

        nom = self.usuario.get("nombre", "")
        uid = self.usuario.get("id_usuario") or self.usuario.get("_id", "")
        l_alerta.addWidget(QLabel(f"Usuario: <strong>{nom}</strong>"))
        l_alerta.addWidget(QLabel(
            f"ID Provisional Actual: <code style='color: #b45309; font-weight: bold;'>{uid}</code>"))
        layout.addWidget(alerta_frame)

        # Campo para ingresar nuevo DNI
        lbl_inst = QLabel("Nuevo DNI Real (8 dígitos):")
        lbl_inst.setStyleSheet("font-weight: 500;")
        layout.addWidget(lbl_inst)

        self.campo_nuevo_dni = QLineEdit()
        self.campo_nuevo_dni.setPlaceholderText("Ej. 30771072")
        self.campo_nuevo_dni.setMaxLength(8)
        layout.addWidget(self.campo_nuevo_dni)

        lbl_nota = QLabel(
            "Esta acción transferirá sus medidores e historial en todas las colecciones de meses.")
        lbl_nota.setStyleSheet("color: #64748b; font-size: 11px;")
        lbl_nota.setWordWrap(True)
        layout.addWidget(lbl_nota)

        layout.addStretch(1)

        fila_botones = QHBoxLayout()
        fila_botones.addStretch(1)

        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setProperty("class", "boton boton_secundario")
        btn_cancelar.clicked.connect(self.reject)
        fila_botones.addWidget(btn_cancelar)

        btn_confirmar = QPushButton("✅ Confirmar y Renombrar DNI")
        btn_confirmar.setProperty("class", "boton boton_aviso")
        btn_confirmar.clicked.connect(self._confirmar)
        fila_botones.addWidget(btn_confirmar)

        layout.addLayout(fila_botones)

    def _confirmar(self) -> None:
        dni_nuevo_raw = self.campo_nuevo_dni.text().strip()
        if not dni_nuevo_raw.isdigit() or len(dni_nuevo_raw) not in (7, 8):
            QMessageBox.warning(self, "DNI Inválido",
                                "El DNI debe contener 7 u 8 dígitos numéricos.")
            self.campo_nuevo_dni.setFocus()
            return

        dni_nuevo = codigos.normalizar_dni(dni_nuevo_raw)
        id_viejo = str(self.usuario.get("id_usuario")
                       or self.usuario.get("_id", ""))

        try:
            res = self.servicio.corregir_dni_usuario(id_viejo, dni_nuevo)
            meses_act = res.get("meses_actualizados", [])
            txt_meses = f"\nColecciones de meses actualizadas: {len(meses_act)}" if meses_act else ""
            QMessageBox.information(
                self,
                "DNI Corregido",
                f"El identificador se actualizó correctamente a '{dni_nuevo}'.{txt_meses}",
            )
            self.accept()
        except ValueError as ve:
            QMessageBox.warning(self, "No permitido", str(ve))
        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"Ocurrió un error al renombrar el ID:\n{e}")
