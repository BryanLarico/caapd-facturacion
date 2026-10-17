"""
ui/paginas/usuarios_dialogos.py — Diálogos modales para gestión de usuarios.

Incluye:
- DialogoUsuario: Crear y editar usuario con gestión dinámica de medidores.
- DialogoCorregirDni: Reasignar DNI real a personas con ID provisional.
- DialogoDetalleUsuario: Vista detallada de la ficha de un abonado.
"""
import re
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
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import codigos
from servicios.datos import ServicioDatos
from ui.hilos import mostrar_dialogo_aviso, mostrar_dialogo_error


def es_formato_id_valido(val: str) -> bool:
    """Valida si el ID ingresado tiene formato admisible (DNI 7/8 dígitos, SD-xxx, o sufijo -1)."""
    s = str(val).strip()
    if s.isdigit() and len(s) in (7, 8):
        return True
    if s.startswith("SD-") and len(s) >= 4:
        return True
    if "-" in s:
        partes = s.split("-", 1)
        if partes[0].isdigit() and len(partes[0]) in (7, 8) and partes[1].isdigit():
            return True
        if partes[0] == "SD" and partes[1].isdigit():
            return True
    return False


def normalizar_id_completo(val: str) -> str:
    """Normaliza un DNI o identificador, respetando sufijos correlativos si existen."""
    s = str(val).strip()
    if s.isdigit() and len(s) in (7, 8):
        return codigos.normalizar_dni(s)
    if "-" in s:
        partes = s.split("-", 1)
        if partes[0].isdigit() and len(partes[0]) in (7, 8) and partes[1].isdigit():
            return f"{codigos.normalizar_dni(partes[0])}-{partes[1]}"
    return s


def obtener_siguiente_dni_sugerido(servicio: ServicioDatos, dni_base: str) -> str:
    """Calcula el siguiente identificador correlativo con sufijo '-1', '-2', etc.

    Por ejemplo, si se ingresó '30771072' y ya existe, sugiere '30771072-1'.
    Si '30771072-1' también existe, sugiere '30771072-2', y así sucesivamente.
    """
    base = re.sub(r"-\d+$", "", str(dni_base).strip())
    if base.isdigit() and len(base) in (7, 8):
        base = codigos.normalizar_dni(base)
    correlativo = 1
    while True:
        candidato = f"{base}-{correlativo}"
        if servicio.obtener_usuario(candidato) is None:
            return candidato
        correlativo += 1


class DialogoConfirmacionDniDuplicado(QDialog):
    """Diálogo modal responsive para advertir sobre DNI duplicado y ofrecer alternativas."""

    ACCION_ACEPTAR = "aceptar"
    ACCION_CANCELAR = "cancelar"
    ACCION_SUGERIDO = "sugerido"

    def __init__(
        self,
        dni: str,
        dni_sugerido: str,
        usuario_existente: Optional[Dict[str, Any]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.dni = dni
        self.dni_sugerido = dni_sugerido
        self.usuario_existente = usuario_existente or {}
        self.accion_elegida = self.ACCION_CANCELAR

        self.setWindowTitle("DNI ya registrado")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.resize(520, 260)
        self._construir_ui()

    def _construir_ui(self) -> None:
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(22, 20, 22, 20)
        layout_principal.setSpacing(16)

        fila_contenido = QHBoxLayout()
        fila_contenido.setSpacing(16)
        fila_contenido.setAlignment(Qt.AlignmentFlag.AlignTop)

        lbl_icono = QLabel("⚠️")
        lbl_icono.setStyleSheet("font-size: 38px;")
        lbl_icono.setAlignment(Qt.AlignmentFlag.AlignTop)
        fila_contenido.addWidget(lbl_icono)

        col_texto = QVBoxLayout()
        col_texto.setSpacing(8)

        lbl_titulo = QLabel(f"El DNI <b>'{self.dni}'</b> ya se encuentra registrado.")
        lbl_titulo.setStyleSheet("font-size: 14px; font-weight: bold; color: #b45309;")
        lbl_titulo.setWordWrap(True)
        col_texto.addWidget(lbl_titulo)

        if self.usuario_existente:
            nom = self.usuario_existente.get("nombre", "No especificado")
            con = self.usuario_existente.get("nro_conexion", "-")
            sec = self.usuario_existente.get("sector", "-")
            lbl_titular = QLabel(
                f"Titular actual: <b>{nom}</b><br>"
                f"N° Conexión: <b>{con}</b> &nbsp;|&nbsp; Sector: <b>{sec}</b>"
            )
            lbl_titular.setStyleSheet(
                "background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px; font-size: 12px; color: #334155;"
            )
            lbl_titular.setWordWrap(True)
            col_texto.addWidget(lbl_titular)

        lbl_pregunta = QLabel(
            "¿Seguro que deseas guardar con este DNI? Podría tratarse de un error de tipeo.<br>"
            f"Si es una conexión adicional para el mismo titular, te recomendamos guardarlo como <b>{self.dni_sugerido}</b>."
        )
        lbl_pregunta.setStyleSheet("font-size: 12px; color: #475569;")
        lbl_pregunta.setWordWrap(True)
        col_texto.addWidget(lbl_pregunta)

        fila_contenido.addLayout(col_texto, stretch=1)
        layout_principal.addLayout(fila_contenido)

        layout_principal.addSpacing(6)

        # Botones de acción con EXACTAMENTE el mismo tamaño
        fila_botones = QHBoxLayout()
        fila_botones.setSpacing(10)

        self.btn_aceptar = QPushButton("Aceptar")
        self.btn_aceptar.setProperty("class", "boton boton_secundario")
        self.btn_aceptar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_aceptar.setMinimumHeight(38)
        self.btn_aceptar.clicked.connect(self._on_aceptar)

        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setProperty("class", "boton boton_secundario")
        self.btn_cancelar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_cancelar.setMinimumHeight(38)
        self.btn_cancelar.clicked.connect(self._on_cancelar)

        self.btn_sugerido = QPushButton(f"Guardar {self.dni_sugerido}")
        self.btn_sugerido.setProperty("class", "boton boton_primario")
        self.btn_sugerido.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_sugerido.setMinimumHeight(38)
        self.btn_sugerido.clicked.connect(self._on_sugerido)

        fila_botones.addWidget(self.btn_aceptar, stretch=1)
        fila_botones.addWidget(self.btn_cancelar, stretch=1)
        fila_botones.addWidget(self.btn_sugerido, stretch=1)

        layout_principal.addLayout(fila_botones)

    def _on_aceptar(self) -> None:
        self.accion_elegida = self.ACCION_ACEPTAR
        self.accept()

    def _on_cancelar(self) -> None:
        self.accion_elegida = self.ACCION_CANCELAR
        self.reject()

    def _on_sugerido(self) -> None:
        self.accion_elegida = self.ACCION_SUGERIDO
        self.accept()


class DialogoConfirmacionMedidorDuplicado(QDialog):
    """Diálogo modal responsive para advertir sobre medidor duplicado."""

    def __init__(
        self,
        mensaje_detalle: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.mensaje_detalle = mensaje_detalle
        self.confirmado = False

        self.setWindowTitle("Medidor ya registrado")
        self.setModal(True)
        self.setMinimumWidth(480)
        self.resize(500, 220)
        self._construir_ui()

    def _construir_ui(self) -> None:
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(22, 20, 22, 20)
        layout_principal.setSpacing(16)

        fila_contenido = QHBoxLayout()
        fila_contenido.setSpacing(16)
        fila_contenido.setAlignment(Qt.AlignmentFlag.AlignTop)

        lbl_icono = QLabel("⚠️")
        lbl_icono.setStyleSheet("font-size: 38px;")
        lbl_icono.setAlignment(Qt.AlignmentFlag.AlignTop)
        fila_contenido.addWidget(lbl_icono)

        col_texto = QVBoxLayout()
        col_texto.setSpacing(8)

        lbl_titulo = QLabel("Medidor ya registrado en el sistema")
        lbl_titulo.setStyleSheet("font-size: 14px; font-weight: bold; color: #b45309;")
        lbl_titulo.setWordWrap(True)
        col_texto.addWidget(lbl_titulo)

        lbl_detalle = QLabel(self.mensaje_detalle)
        lbl_detalle.setStyleSheet(
            "background-color: #fef2f2; border: 1px solid #fecaca; border-radius: 6px; padding: 8px; font-size: 12px; color: #991b1b;"
        )
        lbl_detalle.setWordWrap(True)
        col_texto.addWidget(lbl_detalle)

        lbl_pregunta = QLabel("¿Seguro que deseas registrar este medidor? Podría tratarse de un error de tipeo.")
        lbl_pregunta.setStyleSheet("font-size: 12px; color: #475569;")
        lbl_pregunta.setWordWrap(True)
        col_texto.addWidget(lbl_pregunta)

        fila_contenido.addLayout(col_texto, stretch=1)
        layout_principal.addLayout(fila_contenido)

        layout_principal.addSpacing(6)

        # Botones Aceptar y Cancelar del mismo tamaño
        fila_botones = QHBoxLayout()
        fila_botones.setSpacing(10)

        self.btn_aceptar = QPushButton("Aceptar")
        self.btn_aceptar.setProperty("class", "boton boton_secundario")
        self.btn_aceptar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_aceptar.setMinimumHeight(38)
        self.btn_aceptar.clicked.connect(self._on_aceptar)

        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setProperty("class", "boton boton_secundario")
        self.btn_cancelar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_cancelar.setMinimumHeight(38)
        self.btn_cancelar.clicked.connect(self.reject)

        fila_botones.addWidget(self.btn_aceptar, stretch=1)
        fila_botones.addWidget(self.btn_cancelar, stretch=1)

        layout_principal.addLayout(fila_botones)

    def _on_aceptar(self) -> None:
        self.confirmado = True
        self.accept()


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
        self.resize(540, 600)
        self.setMinimumSize(480, 500)
        self.setModal(True)

        self._construir_ui()
        self._cargar_datos_iniciales()

    def _construir_ui(self) -> None:
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(20, 16, 20, 16)
        layout_principal.setSpacing(12)

        # Encabezado del diálogo (fijo)
        titulo_txt = f"✏️ Editar Usuario: {self.usuario.get('nombre', '')}" if self.es_edicion else "➕ Registrar Nuevo Usuario"
        lbl_titulo = QLabel(titulo_txt)
        lbl_titulo.setObjectName("dialogo_titulo")
        lbl_titulo.setWordWrap(True)
        layout_principal.addWidget(lbl_titulo)

        # Contenedor desplazable para que sea 100% responsive en cualquier pantalla
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        scroll_widget = QWidget()
        layout_form = QVBoxLayout(scroll_widget)
        layout_form.setContentsMargins(4, 4, 8, 4)
        layout_form.setSpacing(12)

        # 1. DNI / ID
        col_id = QVBoxLayout()
        col_id.setSpacing(4)
        lbl_id = QLabel("DNI / Documento de Identidad:")
        lbl_id.setStyleSheet("font-weight: 500;")
        col_id.addWidget(lbl_id)

        self.campo_id = QLineEdit()
        self.campo_id.setPlaceholderText("8 dígitos (ej. 30771072) o SD-xxx")
        self.campo_id.setMaxLength(15)
        col_id.addWidget(self.campo_id)

        if not self.es_edicion:
            self.chk_sin_dni = QCheckBox(
                "Persona sin DNI (asignar ID provisional correlativo)")
            self.chk_sin_dni.setStyleSheet(
                "color: #1e293b; font-size: 13px; font-weight: 500;")
            self.chk_sin_dni.toggled.connect(self._toggle_sin_dni)
            col_id.addWidget(self.chk_sin_dni)

        # Etiqueta de aviso en rojo en vivo para DNI duplicado
        self.lbl_error_dni = QLabel("⚠️ DNI ya registrado")
        self.lbl_error_dni.setStyleSheet(
            "color: #dc2626; font-size: 12px; font-weight: 600; padding-top: 2px;"
        )
        self.lbl_error_dni.setVisible(False)
        col_id.addWidget(self.lbl_error_dni)

        layout_form.addLayout(col_id)
        layout_form.addSpacing(6)

        # 2. Conexión
        col_con = QVBoxLayout()
        col_con.setSpacing(4)
        lbl_con = QLabel("N° de Conexión:")
        lbl_con.setStyleSheet("font-weight: 500;")
        col_con.addWidget(lbl_con)

        self.campo_conexion = QLineEdit()
        self.campo_conexion.setPlaceholderText("6 dígitos (ej. 000796)")
        self.campo_conexion.setMaxLength(6)
        col_con.addWidget(self.campo_conexion)

        layout_form.addLayout(col_con)
        layout_form.addSpacing(6)

        # 3. Apellidos y Nombres
        col_nombre = QVBoxLayout()
        col_nombre.setSpacing(4)
        lbl_nom = QLabel("Apellidos y Nombres Completos:")
        lbl_nom.setStyleSheet("font-weight: 500;")
        col_nombre.addWidget(lbl_nom)

        self.campo_nombre = QLineEdit()
        self.campo_nombre.setPlaceholderText(
            "Ej. CONDORI MAMANI, CARLOS ALBERTO")
        col_nombre.addWidget(self.campo_nombre)

        layout_form.addLayout(col_nombre)
        layout_form.addSpacing(6)

        # 4. Sector y Categoría
        fila_sec_cat = QHBoxLayout()
        fila_sec_cat.setSpacing(12)

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

        layout_form.addLayout(fila_sec_cat)
        layout_form.addSpacing(6)

        # 5. Dirección
        col_dir = QVBoxLayout()
        col_dir.setSpacing(4)
        lbl_dir = QLabel("Dirección / Referencia:")
        lbl_dir.setStyleSheet("font-weight: 500;")
        col_dir.addWidget(lbl_dir)

        self.campo_direccion = QLineEdit()
        self.campo_direccion.setPlaceholderText("Ej. CALLE 05 DE AGOSTO S/N")
        col_dir.addWidget(self.campo_direccion)

        layout_form.addLayout(col_dir)
        layout_form.addSpacing(6)

        # 6. Medidores
        col_med = QVBoxLayout()
        col_med.setSpacing(6)
        lbl_med = QLabel("Medidores de Agua Asignados:")
        lbl_med.setStyleSheet("font-weight: 500;")
        col_med.addWidget(lbl_med)

        fila_add_med = QHBoxLayout()
        fila_add_med.setSpacing(8)
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

        # Etiqueta de aviso en rojo en vivo para Medidor duplicado
        self.lbl_error_medidor = QLabel("⚠️ Medidor ya registrado")
        self.lbl_error_medidor.setStyleSheet(
            "color: #dc2626; font-size: 12px; font-weight: 600; padding-top: 2px;"
        )
        self.lbl_error_medidor.setVisible(False)
        col_med.addWidget(self.lbl_error_medidor)

        # Contenedor de chips de medidores
        self.contenedor_chips = QWidget()
        self.layout_chips = QHBoxLayout(self.contenedor_chips)
        self.layout_chips.setContentsMargins(0, 4, 0, 4)
        self.layout_chips.setSpacing(8)
        col_med.addWidget(self.contenedor_chips)

        layout_form.addLayout(col_med)
        layout_form.addSpacing(6)

        layout_form.addStretch(1)

        scroll_area.setWidget(scroll_widget)
        layout_principal.addWidget(scroll_area, stretch=1)

        # Botones de pie (fijos)
        fila_botones = QHBoxLayout()
        fila_botones.addStretch(1)

        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setProperty("class", "boton boton_secundario")
        btn_cancelar.setMinimumHeight(38)
        btn_cancelar.clicked.connect(self.reject)
        fila_botones.addWidget(btn_cancelar)

        btn_guardar = QPushButton("💾 Guardar Usuario")
        btn_guardar.setProperty("class", "boton boton_primario")
        btn_guardar.setMinimumHeight(38)
        btn_guardar.clicked.connect(self._guardar)
        fila_botones.addWidget(btn_guardar)

        layout_principal.addLayout(fila_botones)

        # Conectar validaciones en vivo
        self.campo_id.textChanged.connect(self._validar_dni_en_vivo)
        self.campo_nuevo_medidor.textChanged.connect(self._validar_medidor_en_vivo)

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
        self._validar_dni_en_vivo()

    def _validar_dni_en_vivo(self, texto: str = "") -> None:
        txt = self.campo_id.text().strip()
        if not txt:
            self.lbl_error_dni.setText("")
            self.lbl_error_dni.setVisible(False)
            return

        # En modo edición, si coincide con el original, no advertir
        if self.es_edicion:
            norm_txt = normalizar_id_completo(txt)
            if txt == self.id_original or norm_txt == self.id_original:
                self.lbl_error_dni.setText("")
                self.lbl_error_dni.setVisible(False)
                return

        dni_buscar = normalizar_id_completo(txt)
        usr = self.servicio.obtener_usuario(dni_buscar) or self.servicio.obtener_usuario(txt)
        if usr:
            nombre = usr.get("nombre", "")
            txt_extra = f": {nombre}" if nombre else ""
            self.lbl_error_dni.setText(f"⚠️ DNI registrado{txt_extra}")
            self.lbl_error_dni.setVisible(True)
        else:
            self.lbl_error_dni.setText("")
            self.lbl_error_dni.setVisible(False)

    def _validar_medidor_en_vivo(self, texto: str = "") -> None:
        txt = self.campo_nuevo_medidor.text().strip()
        if not txt:
            self.lbl_error_medidor.setText("")
            self.lbl_error_medidor.setVisible(False)
            return

        med_norm = codigos.normalizar_medidor(txt)
        if med_norm in self.medidores_lista:
            self.lbl_error_medidor.setText("⚠️ Medidor ya agregado")
            self.lbl_error_medidor.setVisible(True)
            return

        valido, _ = self.servicio.validar_medidores_unicos(
            [med_norm],
            id_usuario_actual=self.id_original if self.es_edicion else None,
        )
        if not valido:
            self.lbl_error_medidor.setText("⚠️ Medidor registrado")
            self.lbl_error_medidor.setVisible(True)
        else:
            self.lbl_error_medidor.setText("")
            self.lbl_error_medidor.setVisible(False)

    def _agregar_medidor(self) -> None:
        txt = self.campo_nuevo_medidor.text().strip()
        if not txt:
            return
        med_norm = codigos.normalizar_medidor(txt)
        if med_norm not in self.medidores_lista:
            self.medidores_lista.append(med_norm)
            self._renderizar_chips_medidores()
        self.campo_nuevo_medidor.clear()
        self.lbl_error_medidor.setText("")
        self.lbl_error_medidor.setVisible(False)
        self.campo_nuevo_medidor.setFocus()

    def _quitar_medidor(self, medidor: str) -> None:
        if medidor in self.medidores_lista:
            self.medidores_lista.remove(medidor)
            self._renderizar_chips_medidores()
            self._validar_medidor_en_vivo()

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
                if not es_formato_id_valido(nuevo_id):
                    QMessageBox.warning(
                        self, "DNI inválido", "El DNI debe contener 7 u 8 dígitos, o tener formato SD-xxx o sufijo correlativo.")
                    self.campo_id.setFocus()
                    return
                id_final = normalizar_id_completo(nuevo_id)

            usr_existente = self.servicio.obtener_usuario(id_final)
            if usr_existente is not None:
                dni_sugerido = obtener_siguiente_dni_sugerido(self.servicio, id_final)
                dlg = DialogoConfirmacionDniDuplicado(
                    dni=id_final,
                    dni_sugerido=dni_sugerido,
                    usuario_existente=usr_existente,
                    parent=self,
                )
                dlg.exec()
                if dlg.accion_elegida == DialogoConfirmacionDniDuplicado.ACCION_CANCELAR:
                    self.campo_id.setFocus()
                    self.campo_id.selectAll()
                    return
                elif dlg.accion_elegida == DialogoConfirmacionDniDuplicado.ACCION_SUGERIDO:
                    id_final = dni_sugerido
                    self.campo_id.setText(dni_sugerido)
                # Si eligió ACCION_ACEPTAR: continúa con id_final
        else:
            # Modo edición: si el usuario cambió el DNI / ID (ej. de SD-001 a DNI real)
            id_final = self.id_original
            if nuevo_id and nuevo_id != self.id_original:
                if not es_formato_id_valido(nuevo_id):
                    QMessageBox.warning(
                        self, "DNI inválido", "El nuevo DNI debe contener 7 u 8 dígitos, o tener formato SD-xxx o sufijo correlativo.")
                    self.campo_id.setFocus()
                    return
                norm_id = normalizar_id_completo(nuevo_id)

                usr_existente = self.servicio.obtener_usuario(norm_id)
                if usr_existente is not None:
                    dni_sugerido = obtener_siguiente_dni_sugerido(self.servicio, norm_id)
                    dlg = DialogoConfirmacionDniDuplicado(
                        dni=norm_id,
                        dni_sugerido=dni_sugerido,
                        usuario_existente=usr_existente,
                        parent=self,
                    )
                    dlg.exec()
                    if dlg.accion_elegida == DialogoConfirmacionDniDuplicado.ACCION_CANCELAR:
                        self.campo_id.setFocus()
                        self.campo_id.selectAll()
                        return
                    elif dlg.accion_elegida == DialogoConfirmacionDniDuplicado.ACCION_SUGERIDO:
                        norm_id = dni_sugerido
                        self.campo_id.setText(dni_sugerido)

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
            dlg_med = DialogoConfirmacionMedidorDuplicado(
                mensaje_detalle=err_msg or "Medidor ya asignado a otra persona.",
                parent=self,
            )
            dlg_med.exec()
            if not dlg_med.confirmado:
                self.campo_nuevo_medidor.setFocus()
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
