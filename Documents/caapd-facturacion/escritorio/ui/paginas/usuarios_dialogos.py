"""
ui/paginas/usuarios_dialogos.py — Diálogos modales para gestión de usuarios.

Incluye:
- DialogoUsuario: Crear y editar usuario con gestión dinámica de medidores.
- DialogoCorregirDni: Reasignar DNI real a personas con ID provisional.
- DialogoDetalleUsuario: Vista detallada de la ficha de un abonado.
"""
import logging
import re
from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt, QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QButtonGroup,
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
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui import iconos

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

        lbl_titulo = QLabel(
            f"El DNI <b>'{self.dni}'</b> ya se encuentra registrado.")
        lbl_titulo.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #b45309;")
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
        self.btn_aceptar.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_aceptar.setMinimumHeight(38)
        self.btn_aceptar.clicked.connect(self._on_aceptar)

        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setProperty("class", "boton boton_secundario")
        self.btn_cancelar.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_cancelar.setMinimumHeight(38)
        self.btn_cancelar.clicked.connect(self._on_cancelar)

        self.btn_sugerido = QPushButton(f"Guardar {self.dni_sugerido}")
        self.btn_sugerido.setProperty("class", "boton boton_primario")
        self.btn_sugerido.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
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
        lbl_titulo.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #b45309;")
        lbl_titulo.setWordWrap(True)
        col_texto.addWidget(lbl_titulo)

        lbl_detalle = QLabel(self.mensaje_detalle)
        lbl_detalle.setStyleSheet(
            "background-color: #fef2f2; border: 1px solid #fecaca; border-radius: 6px; padding: 8px; font-size: 12px; color: #991b1b;"
        )
        lbl_detalle.setWordWrap(True)
        col_texto.addWidget(lbl_detalle)

        lbl_pregunta = QLabel(
            "¿Seguro que deseas registrar este medidor? Podría tratarse de un error de tipeo.")
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
        self.btn_aceptar.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_aceptar.setMinimumHeight(38)
        self.btn_aceptar.clicked.connect(self._on_aceptar)

        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setProperty("class", "boton boton_secundario")
        self.btn_cancelar.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_cancelar.setMinimumHeight(38)
        self.btn_cancelar.clicked.connect(self.reject)

        fila_botones.addWidget(self.btn_aceptar, stretch=1)
        fila_botones.addWidget(self.btn_cancelar, stretch=1)

        layout_principal.addLayout(fila_botones)

    def _on_aceptar(self) -> None:
        self.confirmado = True
        self.accept()


class DialogoMotivoCambioMedidor(QDialog):
    """Diálogo modal para consultar el motivo tras modificar el número de medidor."""

    MOTIVO_CORRECCION = "CORRECCION"
    MOTIVO_REINSTALACION = "REINSTALACION"

    def __init__(
        self,
        medidor_anterior: str,
        medidor_nuevo: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.medidor_anterior = medidor_anterior
        self.medidor_nuevo = medidor_nuevo
        self.motivo_elegido: Optional[str] = self.MOTIVO_CORRECCION

        self.setWindowTitle("Modificación de Medidor")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.resize(540, 320)
        self._construir_ui()

    def _construir_ui(self) -> None:
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(24, 20, 24, 20)
        layout_principal.setSpacing(16)

        # Encabezado
        fila_header = QHBoxLayout()
        fila_header.setSpacing(14)
        fila_header.setAlignment(Qt.AlignmentFlag.AlignTop)

        lbl_ico = QLabel("🔄")
        lbl_ico.setStyleSheet("font-size: 32px;")
        fila_header.addWidget(lbl_ico)

        col_tit = QVBoxLayout()
        col_tit.setSpacing(4)
        lbl_tit = QLabel("Se ha modificado el número de medidor")
        lbl_tit.setStyleSheet("font-size: 15px; font-weight: 700; color: #0f172a;")
        col_tit.addWidget(lbl_tit)

        lbl_desc = QLabel(
            f"Medidor anterior: <b>{self.medidor_anterior or '(Ninguno)'}</b> &nbsp;➔&nbsp; "
            f"Nuevo medidor: <b>{self.medidor_nuevo}</b>"
        )
        lbl_desc.setStyleSheet("font-size: 12px; color: #475569;")
        col_tit.addWidget(lbl_desc)

        fila_header.addLayout(col_tit, stretch=1)
        layout_principal.addLayout(fila_header)

        # Pregunta
        lbl_preg = QLabel("¿Cuál es el motivo del cambio?")
        lbl_preg.setStyleSheet("font-size: 13px; font-weight: 600; color: #1e293b; margin-top: 4px;")
        layout_principal.addWidget(lbl_preg)

        # Grupo de opciones con radio buttons
        self.grupo_opciones = QButtonGroup(self)

        # Opción 1: Corrección
        cont_op1 = QFrame()
        cont_op1.setStyleSheet(
            "QFrame { background-color: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; padding: 10px; }"
        )
        lay_op1 = QVBoxLayout(cont_op1)
        lay_op1.setContentsMargins(8, 6, 8, 6)
        lay_op1.setSpacing(4)

        self.radio_op1 = QRadioButton("1. Corrección de número: Era el mismo medidor pero estaba mal digitado.")
        self.radio_op1.setStyleSheet("font-size: 13px; font-weight: 600; color: #0f172a;")
        self.radio_op1.setChecked(True)
        self.grupo_opciones.addButton(self.radio_op1, 1)
        lay_op1.addWidget(self.radio_op1)

        lbl_desc_op1 = QLabel("(Mantiene la Lectura Anterior y la Lectura Actual intactas).")
        lbl_desc_op1.setStyleSheet("font-size: 12px; color: #64748b; margin-left: 24px;")
        lay_op1.addWidget(lbl_desc_op1)

        layout_principal.addWidget(cont_op1)

        # Opción 2: Reinstalación / Medidor Nuevo
        cont_op2 = QFrame()
        cont_op2.setStyleSheet(
            "QFrame { background-color: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; padding: 10px; }"
        )
        lay_op2 = QVBoxLayout(cont_op2)
        lay_op2.setContentsMargins(8, 6, 8, 6)
        lay_op2.setSpacing(4)

        self.radio_op2 = QRadioButton("2. Reinstalación / Medidor Nuevo: Se instaló un nuevo aparato físico.")
        self.radio_op2.setStyleSheet("font-size: 13px; font-weight: 600; color: #0f172a;")
        self.grupo_opciones.addButton(self.radio_op2, 2)
        lay_op2.addWidget(self.radio_op2)

        lbl_desc_op2 = QLabel("(Reinicia la Lectura Anterior en 0 y la Lectura Actual en 0 para que empiece su nuevo ciclo).")
        lbl_desc_op2.setStyleSheet("font-size: 12px; color: #64748b; margin-left: 24px;")
        lay_op2.addWidget(lbl_desc_op2)

        layout_principal.addWidget(cont_op2)

        layout_principal.addSpacing(6)

        # Botones
        fila_botones = QHBoxLayout()
        fila_botones.setSpacing(10)
        fila_botones.addStretch(1)

        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setProperty("class", "boton boton_secundario")
        self.btn_cancelar.setMinimumHeight(38)
        self.btn_cancelar.setMinimumWidth(100)
        self.btn_cancelar.clicked.connect(self.reject)
        fila_botones.addWidget(self.btn_cancelar)

        self.btn_continuar = QPushButton("Continuar")
        self.btn_continuar.setProperty("class", "boton boton_primario")
        self.btn_continuar.setMinimumHeight(38)
        self.btn_continuar.setMinimumWidth(120)
        self.btn_continuar.clicked.connect(self._on_continuar)
        fila_botones.addWidget(self.btn_continuar)

        layout_principal.addLayout(fila_botones)

    def _on_continuar(self) -> None:
        if self.radio_op2.isChecked():
            self.motivo_elegido = self.MOTIVO_REINSTALACION
        else:
            self.motivo_elegido = self.MOTIVO_CORRECCION
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
        self.id_original = ""
        if self.es_edicion and self.usuario:
            self.id_original = str(
                self.usuario.get("id_usuario")
                or self.usuario.get("_id")
                or self.usuario.get("dni")
                or self.usuario.get("id")
                or ""
            )
            if not self.id_original and hasattr(self.servicio, "usuarios"):
                for k, v in getattr(self.servicio, "usuarios", {}).items():
                    if v is self.usuario or (isinstance(v, dict) and v.get("nro_conexion") and v.get("nro_conexion") == self.usuario.get("nro_conexion")):
                        self.id_original = str(k)
                        break

        self.medidores_lista: List[str] = []
        self.medidor_original: str = ""
        self._motivo_cambio_medidor: Optional[str] = None
        self._ultimo_medidor_preguntado: Optional[str] = None
        self._lec_anterior_original: int = 0
        self._lec_actual_original: Optional[int] = None
        self.lec_anterior_val: int = 0
        self.lec_actual_val: Optional[int] = None
        self.campo_lectura_anterior: Optional[QLineEdit] = None
        self.campo_lectura_actual: Optional[QLineEdit] = None
        if self.es_edicion:
            self._cargar_lecturas_existentes()

        # Campos que el usuario ya "toco": solo a esos se les muestra el error
        # en rojo mientras escribe. Al pulsar Guardar se muestran todos.
        self._tocados: set = set()
        self._intento_guardar = False

        self.setWindowTitle(
            "Editar Usuario" if self.es_edicion else "Nuevo Usuario")
        self.setModal(True)

        self._construir_ui()
        self._cargar_datos_iniciales()
        self._ajustar_tamano_a_pantalla()

    def _cargar_lecturas_existentes(self) -> None:
        """Carga las lecturas anterior y actual del medidor si existen en el mes o usuario."""
        self.lec_anterior_val = 0
        self.lec_actual_val = None
        if not self.es_edicion:
            return

        id_u = self.id_original
        doc_mes = None
        mes_dict = getattr(self.servicio, "mes", None)
        if isinstance(mes_dict, dict):
            doc_mes = mes_dict.get(id_u)

        doc_fuente = doc_mes or self.usuario or {}
        meds = doc_fuente.get("medidores") or []
        med_obj = None
        for m in meds:
            if isinstance(m, dict):
                med_obj = m
                break

        if med_obj:
            ant = med_obj.get("lectura_anterior")
            act = med_obj.get("lectura_actual")
            try:
                self.lec_anterior_val = int(ant) if ant is not None and str(ant).strip() != "" else 0
            except (ValueError, TypeError):
                self.lec_anterior_val = 0
            try:
                self.lec_actual_val = int(act) if act is not None and str(act).strip() != "" else None
            except (ValueError, TypeError):
                self.lec_actual_val = None

    def _ajustar_tamano_a_pantalla(self) -> None:
        """
        Dimensiona el diálogo en proporción a la pantalla donde está la ventana
        principal (no en píxeles fijos) y garantiza que nunca sea más angosto
        que lo que su contenido necesita (en PCs con fuente/escalado de Windows
        grande los campos se recortaban por la derecha).
        """
        ventana = self.parentWidget().window() if self.parentWidget() else None
        pantalla = (ventana.screen()
                    if ventana is not None else None) or self.screen()
        if pantalla is None:
            self.resize(680, 720)
            return
        area = pantalla.availableGeometry()

        # Ancho que exige el contenido (formulario + barra de scroll + márgenes)
        contenido = getattr(self, "_scroll_widget", None)
        ancho_contenido = 0
        if contenido is not None:
            margenes = self.layout().contentsMargins() if self.layout() else None
            extra = (margenes.left() + margenes.right()) if margenes else 40
            ancho_contenido = contenido.minimumSizeHint().width() + extra + 24

        # Ancho: ~42% de la pantalla, entre 620 y 960 px, y nunca menor al contenido
        ancho = int(area.width() * 0.42)
        ancho = max(620, ancho_contenido, min(ancho, 960))
        # Alto: ~82% de la pantalla, entre 560 y 900 px
        alto = int(area.height() * 0.82)
        alto = max(560, min(alto, 900))
        # Nunca más grande que la pantalla disponible
        ancho = min(ancho, area.width() - 40)
        alto = min(alto, area.height() - 40)

        self.setMinimumSize(
            min(max(560, ancho_contenido), ancho), min(500, alto))
        self.resize(ancho, alto)
        self._centrado_pendiente = True

    def showEvent(self, event) -> None:  # noqa: N802
        """Al mostrarse por primera vez, se centra sobre la ventana principal."""
        super().showEvent(event)
        if not getattr(self, "_centrado_pendiente", False):
            return
        self._centrado_pendiente = False
        ventana = self.parentWidget().window() if self.parentWidget() else None
        pantalla = (ventana.screen()
                    if ventana is not None else None) or self.screen()
        if pantalla is None:
            return
        area = pantalla.availableGeometry()
        referencia = ventana.frameGeometry() if (
            ventana is not None and ventana.isVisible()) else area
        ancho, alto = self.frameGeometry().width(), self.frameGeometry().height()
        x = referencia.center().x() - ancho // 2
        y = referencia.center().y() - alto // 2
        x = max(area.left(), min(x, area.right() - ancho))
        y = max(area.top(), min(y, area.bottom() - alto))
        self.move(x, y)

    def _construir_ui(self) -> None:
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(20, 16, 20, 16)
        layout_principal.setSpacing(12)

        # Encabezado del diálogo
        titulo_txt = f"Editar Usuario: {self.usuario.get('nombre', '')}" if self.es_edicion else "Registrar Nuevo Usuario"
        lbl_titulo = QLabel(titulo_txt)
        lbl_titulo.setObjectName("dialogo_titulo")
        lbl_titulo.setWordWrap(True)
        layout_principal.addWidget(lbl_titulo)

        # Contenedor desplazable para que sea 100% responsive en cualquier pantalla
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }")

        scroll_widget = QWidget()
        self._scroll_widget = scroll_widget
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
        self.campo_id.setPlaceholderText(
            "8 dígitos (ej. 30771072), con sufijo (30771072-1) o SD-xxx")
        self.campo_id.setMaxLength(15)
        col_id.addWidget(self.campo_id)
        self.msg_id = self._crear_mensaje_campo()
        col_id.addWidget(self.msg_id)

        if not self.es_edicion:
            self.chk_sin_dni = QCheckBox(
                "Persona sin DNI (asignar ID provisional correlativo)")
            self.chk_sin_dni.setStyleSheet(
                "color: #1e293b; font-size: 13px; font-weight: 500;")
            self.chk_sin_dni.toggled.connect(self._toggle_sin_dni)
            col_id.addWidget(self.chk_sin_dni)

        # Etiqueta de aviso en vivo para DNI (info o advertencia)
        self.lbl_error_dni = QLabel("")
        self.lbl_error_dni.setWordWrap(True)
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
        self.lbl_error_conexion = QLabel("")
        self.lbl_error_conexion.setStyleSheet(
            "color: #dc2626; font-size: 12px; font-weight: 600; padding-top: 2px;"
        )
        self.lbl_error_conexion.setVisible(False)
        col_con.addWidget(self.lbl_error_conexion)
        self.msg_conexion = self._crear_mensaje_campo()
        col_con.addWidget(self.msg_conexion)

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
        # Solo letras (incluye tildes y Ñ), espacios y signos propios de nombres (, . ' -)
        self.campo_nombre.setValidator(QRegularExpressionValidator(
            QRegularExpression(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ ,.'\-]*"), self.campo_nombre))
        self.campo_nombre.setMaxLength(120)
        self.campo_nombre.textEdited.connect(
            lambda t: self.campo_nombre.setText(t.upper()) if t != t.upper() else None)
        col_nombre.addWidget(self.campo_nombre)
        self.msg_nombre = self._crear_mensaje_campo()
        col_nombre.addWidget(self.msg_nombre)

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
        # Puede encogerse con el diálogo; el desplegable (view) muestra el texto completo
        self.combo_sector.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_sector.setMinimumContentsLength(12)
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
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_categoria.setMinimumContentsLength(12)
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
        self.msg_direccion = self._crear_mensaje_campo()
        col_dir.addWidget(self.msg_direccion)

        layout_form.addLayout(col_dir)
        layout_form.addSpacing(6)

        # 6. Medidor de Agua (un solo medidor por conexión)
        col_med = QVBoxLayout()
        col_med.setSpacing(4)
        lbl_med = QLabel("N° de Medidor:")
        lbl_med.setStyleSheet("font-weight: 500;")
        col_med.addWidget(lbl_med)

        self.campo_medidor = QLineEdit()
        self.campo_medidor.setPlaceholderText("Ej. 22392996")
        self.campo_medidor.setValidator(QRegularExpressionValidator(
            QRegularExpression(r"\d{0,12}"), self.campo_medidor))
        self.campo_medidor.setMaxLength(12)
        col_med.addWidget(self.campo_medidor)

        # Alias de compatibilidad por si código externo/tests usan campo_nuevo_medidor
        self.campo_nuevo_medidor = self.campo_medidor

        # Etiqueta de aviso en rojo en vivo para Medidor duplicado
        self.lbl_error_medidor = QLabel("")
        self.lbl_error_medidor.setStyleSheet(
            "color: #dc2626; font-size: 12px; font-weight: 600; padding-top: 2px;"
        )
        self.lbl_error_medidor.setVisible(False)
        col_med.addWidget(self.lbl_error_medidor)
        self.msg_medidores = self._crear_mensaje_campo()
        col_med.addWidget(self.msg_medidores)

        layout_form.addLayout(col_med)
        layout_form.addSpacing(6)

        # 7. Lecturas (Lectura Anterior y Lectura Actual)
        if self.es_edicion:
            fila_lec = QHBoxLayout()
            fila_lec.setSpacing(12)

            col_ant = QVBoxLayout()
            col_ant.setSpacing(4)
            lbl_ant = QLabel("Lectura Anterior:")
            lbl_ant.setStyleSheet("font-weight: 500;")
            col_ant.addWidget(lbl_ant)

            self.campo_lectura_anterior = QLineEdit()
            self.campo_lectura_anterior.setReadOnly(True)
            self.campo_lectura_anterior.setStyleSheet(
                "background-color: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; font-weight: 500;"
            )
            col_ant.addWidget(self.campo_lectura_anterior)
            fila_lec.addLayout(col_ant, stretch=1)

            col_act = QVBoxLayout()
            col_act.setSpacing(4)
            lbl_act = QLabel("Lectura Actual:")
            lbl_act.setStyleSheet("font-weight: 500;")
            col_act.addWidget(lbl_act)

            self.campo_lectura_actual = QLineEdit()
            self.campo_lectura_actual.setValidator(QRegularExpressionValidator(
                QRegularExpression(r"\d{0,9}"), self.campo_lectura_actual))
            self.campo_lectura_actual.setMaxLength(9)
            col_act.addWidget(self.campo_lectura_actual)
            fila_lec.addLayout(col_act, stretch=1)

            layout_form.addLayout(fila_lec)
        else:
            col_act = QVBoxLayout()
            col_act.setSpacing(4)
            lbl_act = QLabel("Lectura Actual:")
            lbl_act.setStyleSheet("font-weight: 500;")
            col_act.addWidget(lbl_act)

            self.campo_lectura_actual = QLineEdit()
            self.campo_lectura_actual.setText("0")
            self.campo_lectura_actual.setPlaceholderText("0")
            self.campo_lectura_actual.setValidator(QRegularExpressionValidator(
                QRegularExpression(r"\d{0,9}"), self.campo_lectura_actual))
            self.campo_lectura_actual.setMaxLength(9)
            col_act.addWidget(self.campo_lectura_actual)
            layout_form.addLayout(col_act)

        # Etiqueta de aviso en rojo en vivo para Lectura
        self.lbl_error_lectura = QLabel("")
        self.lbl_error_lectura.setStyleSheet(
            "color: #dc2626; font-size: 12px; font-weight: 600; padding-top: 2px;"
        )
        self.lbl_error_lectura.setVisible(False)
        self.lbl_error_lectura.setWordWrap(True)
        layout_form.addWidget(self.lbl_error_lectura)
        self.msg_lectura = self._crear_mensaje_campo()
        layout_form.addWidget(self.msg_lectura)
        layout_form.addSpacing(6)

        layout_form.addStretch(1)

        scroll_area.setWidget(scroll_widget)
        layout_principal.addWidget(scroll_area, stretch=1)

        # Resumen de lo que falta para poder guardar (gris; rojo tras intentar guardar).
        # Va en su propia fila, con altura fija para 2 líneas, y reserva el espacio
        # aunque esté oculto: el diálogo no cambia de tamaño al aparecer/desaparecer.
        self.lbl_resumen = QLabel("")
        self.lbl_resumen.setProperty("class", "campo_mensaje")
        self.lbl_resumen.setWordWrap(True)
        self.lbl_resumen.setFixedHeight(36)
        self.lbl_resumen.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        politica_resumen = self.lbl_resumen.sizePolicy()
        politica_resumen.setRetainSizeWhenHidden(True)
        self.lbl_resumen.setSizePolicy(politica_resumen)
        self.lbl_resumen.hide()
        layout_principal.addWidget(self.lbl_resumen)

        # Botones de pie (fijos)
        fila_botones = QHBoxLayout()
        fila_botones.setSpacing(10)
        fila_botones.addStretch(1)

        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setProperty("class", "boton boton_secundario")
        btn_cancelar.setMinimumHeight(38)
        btn_cancelar.clicked.connect(self.reject)
        fila_botones.addWidget(btn_cancelar)

        self.btn_guardar = QPushButton("Guardar Usuario")
        iconos.aplicar(self.btn_guardar, "device-floppy", "blanco")
        self.btn_guardar.setProperty("class", "boton boton_primario")
        self.btn_guardar.setMinimumHeight(38)
        self.btn_guardar.clicked.connect(self._guardar)
        fila_botones.addWidget(self.btn_guardar)

        layout_principal.addLayout(fila_botones)

        # Validacion en vivo: cada cambio recalcula errores y el estado de Guardar
        self.campo_id.textEdited.connect(
            lambda _t: self._marcar_tocado("dni"))
        self.campo_id.textChanged.connect(
            lambda _t: self._validar_formulario())
        self.campo_conexion.textEdited.connect(
            lambda _t: self._marcar_tocado("conexion"))
        self.campo_conexion.textChanged.connect(
            lambda _t: self._validar_formulario())
        self.campo_nombre.textEdited.connect(
            lambda _t: self._marcar_tocado("nombre"))
        self.campo_nombre.textChanged.connect(
            lambda _t: self._validar_formulario())
        self.campo_direccion.textEdited.connect(
            lambda _t: self._marcar_tocado("direccion"))
        self.campo_direccion.textChanged.connect(
            lambda _t: self._validar_formulario())
        self.campo_medidor.textEdited.connect(
            lambda _t: self._marcar_tocado("medidores"))
        self.campo_medidor.textChanged.connect(
            lambda _t: self._validar_formulario())
        self.campo_medidor.editingFinished.connect(
            self._al_terminar_editar_medidor)

        # Al salir de un campo tambien cuenta como "tocado" (aunque no haya escrito)
        for campo, clave in (
            (self.campo_id, "dni"),
            (self.campo_conexion, "conexion"),
            (self.campo_nombre, "nombre"),
            (self.campo_direccion, "direccion"),
            (self.campo_lectura_actual, "lectura"),
        ):
            campo.editingFinished.connect(
                lambda c=clave: self._marcar_tocado(c))

        # Conectar validaciones en vivo para DNI, conexión, medidor y lectura
        self.campo_id.textChanged.connect(self._validar_dni_en_vivo)
        self.campo_conexion.textChanged.connect(self._validar_conexion_en_vivo)
        self.campo_medidor.textChanged.connect(self._validar_medidor_en_vivo)
        self.campo_lectura_actual.textEdited.connect(
            lambda _t: self._marcar_tocado("lectura"))
        self.campo_lectura_actual.textChanged.connect(
            lambda _t: self._validar_formulario())
        self.campo_lectura_actual.textChanged.connect(self._validar_lectura_en_vivo)

    def _cargar_datos_iniciales(self) -> None:
        if self.es_edicion and self.usuario:
            self.campo_id.setText(str(self.id_original or self.usuario.get(
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

            # Medidor único
            meds = self.usuario.get("medidores") or []
            if meds:
                val = meds[0] if isinstance(meds[0], str) else meds[0].get("nro_medidor", "")
                med_str = str(val).strip()
                self.campo_medidor.setText(med_str)
                self.medidores_lista = [med_str]
                self.medidor_original = codigos.normalizar_medidor(med_str) if med_str else ""
            else:
                self.medidores_lista = []
                self.medidor_original = ""

            self._lec_anterior_original = self.lec_anterior_val
            self._lec_actual_original = self.lec_actual_val

            # Lecturas
            if self.campo_lectura_anterior is not None:
                self.campo_lectura_anterior.setText(str(self.lec_anterior_val))
            if self.campo_lectura_actual is not None:
                if self.lec_actual_val is not None:
                    self.campo_lectura_actual.setText(str(self.lec_actual_val))
                else:
                    self.campo_lectura_actual.clear()

        else:
            # Nuevo: sugerir conexión siguiente libre
            sug_con = self.servicio.obtener_siguiente_conexion_libre()
            self.campo_conexion.setText(sug_con)
            self.medidores_lista = []
            if self.campo_lectura_actual is not None:
                self.campo_lectura_actual.setText("0")

        # Estado inicial del boton Guardar (sin marcar nada en rojo todavia)
        self._validar_formulario()

    def _toggle_sin_dni(self, marcado: bool) -> None:
        if marcado:
            sug_sd = self.servicio.obtener_siguiente_id_sd()
            self.campo_id.setText(sug_sd)
            self.campo_id.setReadOnly(True)
        else:
            self.campo_id.setText("")
            self.campo_id.setReadOnly(False)
        self._validar_dni_en_vivo()
        self._marcar_tocado("dni")

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
        dni_base = txt.split("-")[0] if "-" in txt else txt
        dni_base_norm = codigos.normalizar_dni(dni_base) if (dni_base.isdigit() and len(dni_base) in (7, 8)) else dni_base

        usr = (
            self.servicio.obtener_usuario(dni_buscar)
            or self.servicio.obtener_usuario(txt)
            or self.servicio.obtener_usuario(dni_base_norm)
            or self.servicio.obtener_usuario(dni_base)
        )
        if usr:
            nombre = usr.get("nombre", "")
            self.lbl_error_dni.setText(
                f"ℹ️ El DNI corresponde a <b>{nombre}</b>, estarías creando una nueva conexión y un nuevo medidor."
            )
            self.lbl_error_dni.setStyleSheet(
                "color: #0369a1; background-color: #f0f9ff; border: 1px solid #bae6fd; "
                "border-radius: 6px; padding: 6px 10px; font-size: 12px; font-weight: 500;"
            )
            self.lbl_error_dni.setVisible(True)

            # Autocompletar el nombre si está vacío o si coincidía con el anterior autocompletado
            if not self.campo_nombre.text().strip() or getattr(self, "_nombre_autocompletado", None) == self.campo_nombre.text().strip():
                self.campo_nombre.setText(nombre)
                self._nombre_autocompletado = nombre
                self._marcar_tocado("nombre")
        else:
            self.lbl_error_dni.setText("")
            self.lbl_error_dni.setVisible(False)
            if getattr(self, "_nombre_autocompletado", None) == self.campo_nombre.text().strip():
                self.campo_nombre.clear()
                self._nombre_autocompletado = None

    def _validar_conexion_en_vivo(self, texto: str = "") -> None:
        txt = self.campo_conexion.text().strip()
        if not txt:
            self.lbl_error_conexion.setText("")
            self.lbl_error_conexion.setVisible(False)
            return

        if not txt.isdigit():
            self.lbl_error_conexion.setText("⚠️ La conexión solo admite números.")
            self.lbl_error_conexion.setVisible(True)
            return

        con_norm = codigos.normalizar_conexion(txt)
        valido, err_msg = self.servicio.validar_conexion_unica(
            con_norm,
            id_usuario_actual=self.id_original if self.es_edicion else None,
        )
        if not valido:
            self.lbl_error_conexion.setText(f"⚠️ {err_msg}")
            self.lbl_error_conexion.setVisible(True)
        else:
            self.lbl_error_conexion.setText("")
            self.lbl_error_conexion.setVisible(False)

    def _validar_medidor_en_vivo(self, texto: str = "") -> None:
        txt = self.campo_medidor.text().strip()
        if not txt:
            self.lbl_error_medidor.setText("")
            self.lbl_error_medidor.setVisible(False)
            self.medidores_lista = []
            return

        if not txt.isdigit():
            self.lbl_error_medidor.setText("⚠️ El número de medidor solo admite dígitos.")
            self.lbl_error_medidor.setVisible(True)
            self.medidores_lista = []
            return

        med_norm = codigos.normalizar_medidor(txt)
        self.medidores_lista = [med_norm]

        # Si en modo edición vuelve al medidor original, restaurar lecturas originales
        if self.es_edicion and self.medidor_original and med_norm == self.medidor_original:
            if getattr(self, "_motivo_cambio_medidor", None) is not None:
                self._motivo_cambio_medidor = None
                self._ultimo_medidor_preguntado = None
                self.lec_anterior_val = getattr(self, "_lec_anterior_original", 0)
                if self.campo_lectura_anterior is not None:
                    self.campo_lectura_anterior.setText(str(self.lec_anterior_val))
                if self.campo_lectura_actual is not None and getattr(self, "_lec_actual_original", None) is not None:
                    self.campo_lectura_actual.setText(str(self._lec_actual_original))

        valido, err_msg = self.servicio.validar_medidores_unicos(
            [med_norm],
            id_usuario_actual=self.id_original if self.es_edicion else None,
        )
        if not valido:
            self.lbl_error_medidor.setText(f"⚠️ {err_msg}")
            self.lbl_error_medidor.setVisible(True)
        else:
            self.lbl_error_medidor.setText("")
            self.lbl_error_medidor.setVisible(False)

    def _al_terminar_editar_medidor(self) -> None:
        self._marcar_tocado("medidores")
        if not self.es_edicion:
            return
        txt_med = self.campo_medidor.text().strip()
        if not txt_med or not txt_med.isdigit():
            return
        med_norm = codigos.normalizar_medidor(txt_med)
        if self.medidor_original and med_norm != self.medidor_original:
            if getattr(self, "_ultimo_medidor_preguntado", None) != med_norm:
                self._verificar_motivo_cambio_medidor()

    def _verificar_motivo_cambio_medidor(self) -> bool:
        """Si en edición se cambió el medidor, pregunta si es corrección o reinstalación.
        Devuelve True si se confirmó (o no cambió), False si el usuario canceló."""
        if not self.es_edicion:
            return True

        txt_med = self.campo_medidor.text().strip()
        if not txt_med or not txt_med.isdigit():
            return True

        med_norm = codigos.normalizar_medidor(txt_med)
        if not self.medidor_original or med_norm == self.medidor_original:
            self._motivo_cambio_medidor = None
            self._ultimo_medidor_preguntado = None
            return True

        if getattr(self, "_ultimo_medidor_preguntado", None) == med_norm and self._motivo_cambio_medidor:
            return True

        dlg = DialogoMotivoCambioMedidor(
            medidor_anterior=self.medidor_original,
            medidor_nuevo=med_norm,
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            # Cancelar: restaurar el número de medidor original
            self.campo_medidor.setText(self.medidor_original)
            self._motivo_cambio_medidor = None
            self._ultimo_medidor_preguntado = None
            self._validar_medidor_en_vivo()
            self._validar_formulario()
            return False

        self._motivo_cambio_medidor = dlg.motivo_elegido
        self._ultimo_medidor_preguntado = med_norm

        if self._motivo_cambio_medidor == DialogoMotivoCambioMedidor.MOTIVO_REINSTALACION:
            # Reiniciar lectura anterior en 0 y lectura actual en 0
            self.lec_anterior_val = 0
            if self.campo_lectura_anterior is not None:
                self.campo_lectura_anterior.setText("0")
            if self.campo_lectura_actual is not None:
                self.campo_lectura_actual.setText("0")
        else:
            # Corrección: mantener las lecturas originales
            self.lec_anterior_val = getattr(self, "_lec_anterior_original", 0)
            if self.campo_lectura_anterior is not None:
                self.campo_lectura_anterior.setText(str(self.lec_anterior_val))
            if self.campo_lectura_actual is not None and getattr(self, "_lec_actual_original", None) is not None:
                self.campo_lectura_actual.setText(str(self._lec_actual_original))

        self._validar_lectura_en_vivo()
        self._validar_formulario()
        return True

    def _validar_lectura_en_vivo(self, texto: str = "") -> None:
        if not getattr(self, "campo_lectura_actual", None):
            return
        txt = self.campo_lectura_actual.text().strip()
        if not txt:
            if not self.es_edicion:
                self.lbl_error_lectura.setText("⚠️ Ingresa la lectura actual (por defecto 0).")
                self.lbl_error_lectura.setVisible(True)
            elif self.lec_actual_val is not None:
                self.lbl_error_lectura.setText("⚠️ Ingresa la lectura actual.")
                self.lbl_error_lectura.setVisible(True)
            else:
                self.lbl_error_lectura.setText("")
                self.lbl_error_lectura.setVisible(False)
            return

        if not txt.isdigit():
            self.lbl_error_lectura.setText("⚠️ La lectura actual solo admite números enteros.")
            self.lbl_error_lectura.setVisible(True)
            return

        val = int(txt)
        limite_anterior = getattr(self, "lec_anterior_val", 0) or 0
        if self.es_edicion and val < limite_anterior:
            self.lbl_error_lectura.setText(
                f"⚠️ La lectura actual ({val}) no puede ser menor a la lectura anterior ({limite_anterior})."
            )
            self.lbl_error_lectura.setVisible(True)
        else:
            self.lbl_error_lectura.setText("")
            self.lbl_error_lectura.setVisible(False)

    def _agregar_medidor(self) -> None:
        txt = self.campo_medidor.text().strip()
        if txt:
            self.medidores_lista = [codigos.normalizar_medidor(txt)]
        else:
            self.medidores_lista = []
        self._validar_medidor_en_vivo()
        self._validar_formulario()

    def _quitar_medidor(self, medidor: str = "") -> None:
        self.campo_medidor.clear()
        self.medidores_lista = []
        self._validar_medidor_en_vivo()
        self._validar_formulario()

    def _renderizar_chips_medidores(self) -> None:
        pass

    # -------------------------------------------------------------------
    # Validacion en vivo y feedback visual
    # -------------------------------------------------------------------
    CAMPOS_OBLIGATORIOS = ("dni", "nombre", "direccion", "medidores", "lectura")
    NOMBRES_CAMPO = {
        "dni": "DNI",
        "conexion": "N° de conexión",
        "nombre": "apellidos y nombres",
        "direccion": "dirección",
        "medidores": "número de medidor",
        "lectura": "lectura actual",
    }

    def _crear_mensaje_campo(self) -> QLabel:
        """Etiqueta pequeña bajo un campo para mostrar el error/aviso del campo.

            Reserva su espacio aunque esté oculta y no usa word-wrap: así el diálogo
            no cambia de altura con cada tecla (evita el aviso QWindowsWindow::setGeometry).
            """
        lbl = QLabel("")
        lbl.setProperty("class", "campo_mensaje")
        lbl.setProperty("nivel", "error")
        lbl.setWordWrap(False)
        lbl.setFixedHeight(18)
        politica = lbl.sizePolicy()
        politica.setRetainSizeWhenHidden(True)
        lbl.setSizePolicy(politica)
        lbl.hide()
        return lbl

    @staticmethod
    def _repintar(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _marcar_tocado(self, clave: str) -> None:
        if clave not in self._tocados:
            self._tocados.add(clave)
        self._validar_formulario()

    # DNI de 7-8 digitos, opcionalmente con sufijo para una misma persona con
    # varias conexiones: 76469789, 76469789-1, 76469789-A. Tambien SD-xxx.
    _PATRON_DNI = re.compile(r"^(\d{7,8})(?:-([A-Za-z0-9]{1,2}))?$")

    def _normalizar_id_ingresado(self, texto: str) -> Optional[str]:
        """Devuelve el ID normalizado o None si el formato no es valido.

        '7646978'      -> '07646978'
        '76469789-1'   -> '76469789-1'
        '76469789-a'   -> '76469789-A'
        'SD-012'       -> 'SD-012'
        """
        texto = texto.strip().upper()
        m = self._PATRON_DNI.match(texto)
        if m:
            base = codigos.normalizar_dni(m.group(1))
            sufijo = m.group(2)
            return f"{base}-{sufijo}" if sufijo else base
        if texto.startswith("SD-") and len(texto) > 3:
            return texto
        return None

    def _sugerir_sufijo_libre(self, id_norm: str) -> Optional[str]:
        """Si el DNI ya existe, propone el siguiente ID con sufijo libre (-1, -2, ...)."""
        base = id_norm.split("-")[0]
        if not base.isdigit():
            return None
        for n in range(1, 10):
            candidato = f"{base}-{n}"
            try:
                if self.servicio.obtener_usuario(candidato) is None:
                    return candidato
            except Exception:
                return None
        return None

    def _calcular_errores(self) -> Dict[str, tuple]:
        """
        Devuelve {clave_campo: (mensaje, nivel)} con los problemas actuales.
        nivel: 'error' bloquea el guardado; 'aviso' solo informa.
        """
        errores: Dict[str, tuple] = {}

        # DNI / ID
        texto_id = self.campo_id.text().strip()
        sin_dni = bool(getattr(self, "chk_sin_dni", None)
                       and self.chk_sin_dni.isChecked())
        if not sin_dni:
            if not texto_id:
                errores["dni"] = (
                    "Ingresa el DNI (8 dígitos) o marca «Persona sin DNI».", "error")
            else:
                id_norm = self._normalizar_id_ingresado(texto_id)
                if id_norm is None:
                    errores["dni"] = (
                        "El DNI debe tener 8 dígitos (o formato SD-xxx).", "error")

        # Conexión (si se escribe debe ser numérica y no estar repetida)
        texto_con = self.campo_conexion.text().strip()
        if texto_con:
            if not texto_con.isdigit():
                errores["conexion"] = (
                    "La conexión solo admite números (6 dígitos).", "error")
            else:
                con_norm = codigos.normalizar_conexion(texto_con)
                valido_con, err_con = self.servicio.validar_conexion_unica(
                    con_norm, id_usuario_actual=self.id_original if self.es_edicion else None
                )
                if not valido_con:
                    errores["conexion"] = (err_con or "Esta conexión ya está asignada.", "error")

        # Nombre
        texto_nombre = self.campo_nombre.text().strip()
        if not texto_nombre:
            errores["nombre"] = (
                "Ingresa los apellidos y nombres completos.", "error")
        elif re.search(r"\d", texto_nombre):
            errores["nombre"] = (
                "El nombre solo admite letras; no puede contener números.", "error")
        elif not re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ ,.'\-]+", texto_nombre):
            errores["nombre"] = (
                "El nombre solo admite letras, espacios, coma, punto y guion.", "error")
        elif len(re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", texto_nombre)) < 3:
            errores["nombre"] = (
                "Ingresa los apellidos y nombres completos (mínimo 3 letras).", "error")
        elif len(texto_nombre.split()) < 2:
            errores["nombre"] = (
                "Ingresa al menos apellido y nombre (ej. CONDORI MAMANI, CARLOS).", "error")

        # Direccion
        if not self.campo_direccion.text().strip():
            errores["direccion"] = (
                "Ingresa la dirección o una referencia.", "error")

        # Medidor (único por conexión y obligatorio)
        txt_med = self.campo_medidor.text().strip()
        if not txt_med:
            errores["medidores"] = (
                "Ingresa el número de medidor asignado a esta conexión.", "error")
        elif not txt_med.isdigit():
            errores["medidores"] = (
                "El número de medidor solo admite dígitos (ej. 22392996).", "error")
        else:
            med_norm = codigos.normalizar_medidor(txt_med)
            valido_med, err_med = self.servicio.validar_medidores_unicos(
                [med_norm], id_usuario_actual=self.id_original if self.es_edicion else None
            )
            if not valido_med:
                errores["medidores"] = (
                    err_med or f"El medidor {med_norm} ya está asignado.", "error")

        # Lectura actual
        txt_lec = self.campo_lectura_actual.text().strip() if getattr(self, "campo_lectura_actual", None) else ""
        if not self.es_edicion:
            if not txt_lec:
                errores["lectura"] = (
                    "Ingresa la lectura actual (por defecto 0).", "error")
            elif not txt_lec.isdigit():
                errores["lectura"] = (
                    "La lectura actual solo admite números enteros.", "error")
        else:
            if not txt_lec:
                if self.lec_actual_val is not None:
                    errores["lectura"] = (
                        "Ingresa la lectura actual.", "error")
            elif not txt_lec.isdigit():
                errores["lectura"] = (
                    "La lectura actual solo admite números enteros.", "error")
            else:
                val_lec = int(txt_lec)
                limite_ant = getattr(self, "lec_anterior_val", 0) or 0
                if val_lec < limite_ant:
                    errores["lectura"] = (
                        f"La lectura actual ({val_lec}) no puede ser menor a la lectura anterior ({limite_ant}).",
                        "error",
                    )

        return errores

    def _mostrar_estado_campo(self, campo: Optional[QWidget], lbl: QLabel,
                              mensaje: Optional[str], nivel: str = "error") -> None:
        es_error = mensaje is not None and nivel == "error"
        if campo is not None:
            if (campo.property("invalido") or "false") != ("true" if es_error else "false"):
                campo.setProperty("invalido", "true" if es_error else "false")
                self._repintar(campo)
        if mensaje:
            lbl.setText(mensaje)
            lbl.setProperty("nivel", "error" if nivel == "error" else "aviso")
            self._repintar(lbl)
            lbl.show()
        else:
            lbl.hide()

    def _validar_formulario(self, mostrar_todo: bool = False) -> bool:
        """Recalcula errores, pinta los campos y habilita/deshabilita Guardar."""
        if not hasattr(self, "btn_guardar"):
            return True  # la UI aun no termino de construirse
        errores = self._calcular_errores()
        mostrar_todo = mostrar_todo or self._intento_guardar

        mapa = {
            "dni": (self.campo_id, self.msg_id),
            "conexion": (self.campo_conexion, self.msg_conexion),
            "nombre": (self.campo_nombre, self.msg_nombre),
            "direccion": (self.campo_direccion, self.msg_direccion),
            "medidores": (self.campo_medidor, self.msg_medidores),
        }
        if getattr(self, "campo_lectura_actual", None) and getattr(self, "msg_lectura", None):
            mapa["lectura"] = (self.campo_lectura_actual, self.msg_lectura)

        for clave, (campo, lbl) in mapa.items():
            msg, nivel = errores.get(clave, (None, "error"))
            visible = msg is not None and (
                mostrar_todo or clave in self._tocados or nivel == "aviso_bloqueante")
            self._mostrar_estado_campo(
                campo, lbl, msg if visible else None,
                "error" if nivel == "error" else "aviso")

        hay_bloqueo = bool(errores)
        self.btn_guardar.setEnabled(not hay_bloqueo)

        if hay_bloqueo:
            faltan = [self.NOMBRES_CAMPO[c]
                      for c in ("dni", "nombre", "direccion", "medidores", "conexion", "lectura") if c in errores]
            self.lbl_resumen.setText(
                "Para guardar falta: " + ", ".join(faltan) + ".")
            self.lbl_resumen.setProperty(
                "nivel", "error" if mostrar_todo else "info")
            self._repintar(self.lbl_resumen)
            self.lbl_resumen.show()
            self.btn_guardar.setToolTip(
                "Completa los campos marcados para poder guardar.")
        else:
            self.lbl_resumen.hide()
            self.btn_guardar.setToolTip("")
        return not hay_bloqueo

    def _enfocar_primer_error(self) -> None:
        errores = self._calcular_errores()
        orden = [
            ("dni", self.campo_id),
            ("conexion", self.campo_conexion),
            ("nombre", self.campo_nombre),
            ("direccion", self.campo_direccion),
            ("medidores", self.campo_medidor),
        ]
        if getattr(self, "campo_lectura_actual", None):
            orden.append(("lectura", self.campo_lectura_actual))
        for clave, campo in orden:
            if clave in errores and campo is not None:
                campo.setFocus()
                return

    def _guardar(self) -> None:
        # Validacion visual primero: marca en rojo todo lo que falte
        self._intento_guardar = True
        errores = self._calcular_errores()
        if errores:
            self._validar_formulario(mostrar_todo=True)
            self._enfocar_primer_error()
            return

        nuevo_id = self.campo_id.text().strip()
        nombre = self.campo_nombre.text().strip().upper()
        conexion = self.campo_conexion.text().strip()
        sector = self.combo_sector.currentText()
        cat_data = self.combo_categoria.currentData() or "A"
        direccion = self.campo_direccion.text().strip().upper()
        med_texto = self.campo_medidor.text().strip()

        # Validaciones
        if not nombre:
            QMessageBox.warning(
                self, "Campo requerido", "Debe ingresar los apellidos y nombres completos.")
            self.campo_nombre.setFocus()
            return

        if not med_texto:
            QMessageBox.warning(
                self, "Medidor requerido", "Debe ingresar el número de medidor.")
            self.campo_medidor.setFocus()
            return

        med_norm = codigos.normalizar_medidor(med_texto)

        # 1. Determinar y validar ID
        id_final = ""
        if not self.es_edicion:
            sin_dni = getattr(self, "chk_sin_dni",
                              None) and self.chk_sin_dni.isChecked()
            if sin_dni or not nuevo_id:
                id_final = self.servicio.obtener_siguiente_id_sd()
            else:
                if not (es_formato_id_valido(nuevo_id) or (self._normalizar_id_ingresado(nuevo_id) is not None)):
                    QMessageBox.warning(
                        self, "DNI inválido",
                        "El DNI debe contener 7 u 8 dígitos o tener formato SD-xxx.")
                    self.campo_id.setFocus()
                    return
                id_final = normalizar_id_completo(nuevo_id)

            usr_existente = self.servicio.obtener_usuario(id_final)
            if usr_existente is not None:
                # Si ya existe este DNI en el padrón, se asigna el correlativo siguiente (ej. 30769540-1)
                # para registrar la nueva conexión sin sobreescribir la existente.
                id_final = obtener_siguiente_dni_sugerido(
                    self.servicio, id_final)
        else:
            # Modo edición: si el usuario cambió el DNI / ID (ej. de SD-001 a DNI real)
            id_final = self.id_original
            if nuevo_id and nuevo_id != self.id_original:
                if not (es_formato_id_valido(nuevo_id) or (self._normalizar_id_ingresado(nuevo_id) is not None)):
                    QMessageBox.warning(
                        self, "DNI inválido",
                        "El nuevo DNI debe contener 7 u 8 dígitos o tener formato SD-xxx.")
                    self.campo_id.setFocus()
                    return
                norm_id = normalizar_id_completo(nuevo_id)

                usr_existente = self.servicio.obtener_usuario(norm_id)
                if usr_existente is not None:
                    norm_id = obtener_siguiente_dni_sugerido(
                        self.servicio, norm_id)

                # Reasignar DNI en el padrón, mes y espejo Firebase
                try:
                    self.servicio.corregir_dni_usuario(
                        self.id_original, norm_id)
                    id_final = norm_id
                except Exception as e:
                    mostrar_dialogo_error(
                        self, "Error al cambiar DNI", f"No se pudo reasignar el DNI:\n{e}")
                    return

        # 2. Validar que la conexión sea única
        con_norm = codigos.normalizar_conexion(
            conexion) if conexion else self.servicio.obtener_siguiente_conexion_libre()
        valido_con, err_con = self.servicio.validar_conexion_unica(
            con_norm, id_usuario_actual=id_final if self.es_edicion else None
        )
        if not valido_con:
            QMessageBox.warning(
                self, "Conexión ya registrada",
                err_con or f"La conexión {con_norm} ya está asignada a otro abonado. Cada conexión debe ser única."
            )
            self.campo_conexion.setFocus()
            return

        # 3. Validar que el medidor sea único
        valido_med, err_med = self.servicio.validar_medidores_unicos(
            [med_norm], id_usuario_actual=id_final if self.es_edicion else None
        )
        if not valido_med:
            QMessageBox.warning(
                self, "Medidor ya registrado",
                f"{err_med}\n\nCada conexión tiene un único medidor y no se pueden registrar medidores duplicados."
            )
            self.campo_medidor.setFocus()
            return

        # Si se modificó el medidor en edición y aún no se definió el motivo, consultar ahora
        if self.es_edicion and self.medidor_original and med_norm != self.medidor_original:
            if getattr(self, "_motivo_cambio_medidor", None) is None:
                if not self._verificar_motivo_cambio_medidor():
                    return

        # 4. Validar lectura actual
        txt_lec = self.campo_lectura_actual.text().strip() if getattr(self, "campo_lectura_actual", None) else ""
        lec_act_val: Optional[int] = None
        if not self.es_edicion:
            if not txt_lec:
                QMessageBox.warning(
                    self, "Lectura requerida", "Debe ingresar la lectura actual (por defecto 0).")
                if self.campo_lectura_actual:
                    self.campo_lectura_actual.setFocus()
                return
            if not txt_lec.isdigit():
                QMessageBox.warning(
                    self, "Lectura inválida", "La lectura actual solo admite números enteros.")
                if self.campo_lectura_actual:
                    self.campo_lectura_actual.setFocus()
                return
            lec_act_val = int(txt_lec)
        else:
            if txt_lec:
                if not txt_lec.isdigit():
                    QMessageBox.warning(
                        self, "Lectura inválida", "La lectura actual solo admite números enteros.")
                    if self.campo_lectura_actual:
                        self.campo_lectura_actual.setFocus()
                    return
                lec_act_val = int(txt_lec)
                limite_ant = getattr(self, "lec_anterior_val", 0) or 0
                if lec_act_val < limite_ant:
                    QMessageBox.warning(
                        self, "Lectura actual inválida",
                        f"La lectura actual ({lec_act_val}) no puede ser menor a la lectura anterior ({limite_ant})."
                    )
                    if self.campo_lectura_actual:
                        self.campo_lectura_actual.setFocus()
                    return
            elif self.lec_actual_val is not None:
                QMessageBox.warning(
                    self, "Lectura requerida", "Debe ingresar la lectura actual.")
                if self.campo_lectura_actual:
                    self.campo_lectura_actual.setFocus()
                return

        activo_final = self.usuario.get(
            "activo", True) if self.es_edicion else True

        datos_guardar = {
            "nro_conexion": con_norm,
            "nombre": nombre,
            "sector": sector,
            "direccion": direccion,
            "codigo_categoria": cat_data,
            "activo": activo_final,
            "medidores": [med_norm],
        }

        try:
            exito_sync = True
            err_sync = None
            if not self.es_edicion:
                res = self.servicio.guardar_usuario(
                    id_final, datos_guardar, agregar_al_mes=True)
            else:
                res = self.servicio.actualizar_usuario(id_final, datos_guardar)

            # Registrar/actualizar lectura del medidor si el usuario está en el mes
            mes_actual = getattr(self.servicio, "mes", None)
            if hasattr(self.servicio, "guardar_lectura_medidor") and isinstance(mes_actual, dict) and id_final in mes_actual:
                try:
                    if not self.es_edicion:
                        self.servicio.guardar_lectura_medidor(
                            periodo="",
                            id_usuario=id_final,
                            nro_medidor=med_norm,
                            lectura_actual=lec_act_val if lec_act_val is not None else 0,
                            lectura_anterior=0,
                        )
                    elif lec_act_val is not None:
                        nov = (
                            "CAMBIO_MEDIDOR"
                            if getattr(self, "_motivo_cambio_medidor", None) == DialogoMotivoCambioMedidor.MOTIVO_REINSTALACION
                            else "NORMAL"
                        )
                        lec_ant_guardar = 0 if nov == "CAMBIO_MEDIDOR" else (getattr(self, "lec_anterior_val", 0) or 0)
                        self.servicio.guardar_lectura_medidor(
                            periodo="",
                            id_usuario=id_final,
                            nro_medidor=med_norm,
                            lectura_actual=lec_act_val,
                            lectura_anterior=lec_ant_guardar,
                            novedad=nov,
                        )
                except Exception as e_lec:
                    logging.getLogger(__name__).warning(
                        "No se pudo guardar la lectura del medidor: %s", e_lec
                    )

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


class DialogoEliminarUsuario(QDialog):
    """
    Confirmación reforzada para eliminar un usuario del padrón.

    El botón "Eliminar definitivamente" solo se habilita cuando la secretaria
    escribe la palabra BORRAR (en mayúsculas) en el campo de confirmación.
    """

    PALABRA_CLAVE = "BORRAR"

    def __init__(
        self,
        usuario: Dict[str, Any],
        tiene_movimientos_mes: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.usuario = usuario
        self.tiene_movimientos_mes = tiene_movimientos_mes
        self.confirmado = False

        self.setWindowTitle("Eliminar Usuario")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.resize(560, 360)
        self._construir_ui()

    def _construir_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        titulo = QLabel("Eliminar usuario del padrón")
        titulo.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #b91c1c;")
        layout.addWidget(titulo)

        nombre = str(self.usuario.get("nombre") or "")
        id_usuario = str(self.usuario.get("id_usuario")
                         or self.usuario.get("_id") or "")
        conexion = str(self.usuario.get("nro_conexion") or "")
        sector = str(self.usuario.get("sector") or "")

        tarjeta = QFrame()
        tarjeta.setStyleSheet(
            "QFrame { background-color: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; }"
            "QLabel { background: transparent; border: none; color: #1f2937; font-size: 13px; }")
        lay_t = QVBoxLayout(tarjeta)
        lay_t.setContentsMargins(14, 10, 14, 10)
        lay_t.setSpacing(4)
        lbl_nombre = QLabel(nombre or "(sin nombre)")
        lbl_nombre.setStyleSheet("font-weight: 700; font-size: 14px;")
        lay_t.addWidget(lbl_nombre)
        lay_t.addWidget(QLabel(f"DNI / ID: {id_usuario}    •    N° de conexión: {conexion or '—'}"))
        if sector:
            lay_t.addWidget(QLabel(f"Sector: {sector}"))
        layout.addWidget(tarjeta)

        aviso = (
            "Esta acción es <b>definitiva</b>: el usuario se quitará del padrón y del mes actual, "
            "y dejará de aparecer en la aplicación de los lectores. "
            "Los recibos de meses anteriores se conservan."
        )
        if self.tiene_movimientos_mes:
            aviso += (
                "<br><br><b style='color:#b91c1c;'>Atención:</b> este usuario ya tiene lecturas, "
                "recibo o pagos registrados en el mes actual; también se eliminarán de este mes."
            )
        lbl_aviso = QLabel(aviso)
        lbl_aviso.setWordWrap(True)
        lbl_aviso.setStyleSheet("color: #374151; font-size: 13px;")
        layout.addWidget(lbl_aviso)

        lbl_instr = QLabel(
            f"Para confirmar, escriba <b>{self.PALABRA_CLAVE}</b> en el cuadro:")
        lbl_instr.setStyleSheet("font-weight: 500; color: #111827;")
        layout.addWidget(lbl_instr)

        self.campo_confirmar = QLineEdit()
        self.campo_confirmar.setPlaceholderText(self.PALABRA_CLAVE)
        self.campo_confirmar.setMaxLength(len(self.PALABRA_CLAVE) + 2)
        self.campo_confirmar.textChanged.connect(self._al_escribir)
        layout.addWidget(self.campo_confirmar)

        layout.addStretch(1)

        fila = QHBoxLayout()
        fila.setSpacing(10)
        fila.addStretch(1)
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setProperty("class", "boton boton_secundario")
        self.btn_cancelar.setMinimumHeight(38)
        self.btn_cancelar.clicked.connect(self.reject)
        self.btn_cancelar.setDefault(True)
        fila.addWidget(self.btn_cancelar)

        self.btn_eliminar = QPushButton("Eliminar definitivamente")
        iconos.aplicar(self.btn_eliminar, "trash", "blanco")
        self.btn_eliminar.setProperty("class", "boton boton_peligro")
        self.btn_eliminar.setMinimumHeight(38)
        self.btn_eliminar.setEnabled(False)
        self.btn_eliminar.setToolTip(
            f"Escriba {self.PALABRA_CLAVE} para habilitar este botón")
        self.btn_eliminar.clicked.connect(self._on_eliminar)
        fila.addWidget(self.btn_eliminar)
        layout.addLayout(fila)

        self.campo_confirmar.setFocus()

    def _al_escribir(self, texto: str) -> None:
        ok = texto.strip().upper() == self.PALABRA_CLAVE
        self.btn_eliminar.setEnabled(ok)
        self.btn_eliminar.setToolTip(
            "" if ok else f"Escriba {self.PALABRA_CLAVE} para habilitar este botón")

    def _on_eliminar(self) -> None:
        if self.campo_confirmar.text().strip().upper() != self.PALABRA_CLAVE:
            return
        self.confirmado = True
        self.accept()


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

        lbl_titulo = QLabel("Corregir Documento de Identidad")
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

        btn_confirmar = QPushButton("Confirmar y Renombrar DNI")
        iconos.aplicar(btn_confirmar, "circle-check", "blanco")
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
