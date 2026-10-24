"""
ui/ventana_principal.py — Ventana principal de la aplicación de escritorio CAAPD Ispacas.

Integra la barra superior de navegación, el QStackedWidget con las 7 pantallas,
banners de modo contingencia y cola offline, y control de cierre seguro.
"""
import os
from typing import Any, Dict, Optional

from PySide6.QtCore import QEvent, QThread, QThreadPool, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import rutas
from servicios.datos import ServicioDatos
from ui import iconos
from ui.hilos import Worker, esperar_hilos, mostrar_dialogo_error
from PySide6.QtCore import QThread  # ya importas QThread; si no, agrégalo
from servicios import actualizador
from version import VERSION
from ui.paginas.cobros import PaginaCobros
from ui.paginas.configuracion import PaginaConfiguracion
from ui.paginas.inicio import PaginaInicio
from ui.paginas.lectores import PaginaLectores
from ui.paginas.lecturas import PaginaLecturas
from ui.paginas.usuarios import PaginaUsuarios


class _HiloBuscarActualizacion(QThread):
    encontrada = Signal(object)  # InfoActualizacion o None

    def run(self) -> None:
        self.encontrada.emit(actualizador.buscar_actualizacion())


class _HiloDescargar(QThread):
    progreso = Signal(int)
    terminado = Signal(object)   # Path del zip
    error = Signal(str)

    def __init__(self, info, parent=None):
        super().__init__(parent)
        self.info = info

    def run(self) -> None:
        try:
            ruta = actualizador.descargar_zip(self.info, self.progreso.emit)
            self.terminado.emit(ruta)
        except Exception as e:
            self.error.emit(str(e))


class VentanaPrincipal(QMainWindow):
    """Ventana principal que gestiona la navegación y el estado global."""

    PAGINAS = ["inicio", "usuarios", "lecturas",
               "lectores", "cobros", "configuracion"]

    # Señales internas para actualizar la barra de progreso de forma segura
    # cuando mostrar_progreso()/ocultar_progreso() se invocan desde un hilo Worker.
    _senal_progreso = Signal(int, str)
    _senal_ocultar_progreso = Signal(str)
    # Emitida (desde cualquier hilo) cada vez que se registra una operación Firestore
    _senal_ops_cambiaron = Signal()

    def __init__(
        self,
        servicio_datos: ServicioDatos,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.servicio = servicio_datos

        self.setWindowTitle("CAAPD Ispacas — Facturación")
        self.resize(1180, 780)
        self.setMinimumSize(960, 600)

        self.botones_nav: Dict[str, QPushButton] = {}
        self._verificando_archivos: bool = False
        self.sincronizando: bool = False

        self._construir_ui()

        # Las señales se procesan en el hilo de la interfaz (conexión en cola).
        self._senal_progreso.connect(
            self._mostrar_progreso_ui, Qt.ConnectionType.QueuedConnection)
        self._senal_ocultar_progreso.connect(
            self._ocultar_progreso_ui, Qt.ConnectionType.QueuedConnection)

        # Pie de página: se repinta al instante tras cada lectura/escritura a Firebase.
        # El contador diario avisa desde el hilo de trabajo; la señal (en cola)
        # lleva la actualización al hilo de la interfaz.
        from servicios import contador_ops
        self._senal_ops_cambiaron.connect(
            self._pintar_contadores_locales, Qt.ConnectionType.QueuedConnection)
        self._cb_ops = lambda _totales: self._senal_ops_cambiaron.emit()
        contador_ops.suscribir(self._cb_ops)

        # Número EXACTO de Google (Cloud Monitoring, no gasta cuota de Firestore).
        # Se consulta en segundo plano: al abrir (tras 5 s), cada 2 min y unos
        # segundos después de cada operación (las métricas de Google tardan
        # ~1-3 min en reflejarse). Nunca en los tests con servicio en memoria.
        self._metricas_nube = None
        self._consultando_metricas = False
        self._timer_metricas = QTimer(self)
        self._timer_metricas.setSingleShot(True)
        self._timer_metricas.timeout.connect(self._consultar_metricas_nube)
        self._timer_refresco_metricas = QTimer(self)
        self._timer_refresco_metricas.setInterval(120_000)
        self._timer_refresco_metricas.timeout.connect(
            lambda: self._programar_consulta_metricas(0))
        if not getattr(self.servicio, "es_memoria", False):
            self._senal_ops_cambiaron.connect(
                lambda: self._programar_consulta_metricas(45_000),
                Qt.ConnectionType.QueuedConnection)
            self._programar_consulta_metricas(1_500)   # al abrir, casi de inmediato
            self._timer_refresco_metricas.start()

        self.actualizar_barra_estado()

        # Temporizador para verificar cambios externos en los archivos Excel cada 15s
        self.timer_archivos = QTimer(self)
        self.timer_archivos.setInterval(15000)
        self.timer_archivos.timeout.connect(self._verificar_archivos_externos)
        self.timer_archivos.start()
        # Buscar actualización 3 s después de abrir (sin bloquear la UI)
        self._info_actualizacion = None
        QTimer.singleShot(3000, self._buscar_actualizacion)

    def _construir_ui(self) -> None:
        widget_central = QWidget()
        widget_central.setObjectName("widget_central")
        self.setCentralWidget(widget_central)

        layout_principal = QVBoxLayout(widget_central)
        layout_principal.setContentsMargins(0, 0, 0, 0)
        layout_principal.setSpacing(0)

        # 1. Barra Superior de Navegación
        nav_superior = self._crear_barra_superior()
        layout_principal.addWidget(nav_superior)

        # 2. Banner de Estado Contingencia
        self.banner_contingencia = self._crear_banner_contingencia()
        layout_principal.addWidget(self.banner_contingencia)
        if not getattr(self.servicio, "es_contingencia", False):
            self.banner_contingencia.hide()

        # 3. Contenedor de Páginas (QStackedWidget)
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setObjectName("stacked_paginas")

        # Instanciar las 6 páginas (sin Recibos)
        self.pagina_inicio = PaginaInicio(self.servicio)
        self.pagina_inicio.solicitar_navegacion.connect(self.navegar_a)
        self.pagina_inicio.datos_cargados.connect(self.actualizar_barra_estado)

        self.pagina_usuarios = PaginaUsuarios(self.servicio)
        self.pagina_lecturas = PaginaLecturas(self.servicio)
        self.pagina_lectores = PaginaLectores(self.servicio)
        self.pagina_cobros = PaginaCobros(self.servicio)
        self.pagina_configuracion = PaginaConfiguracion(self.servicio)

        self.stacked_widget.addWidget(self.pagina_inicio)        # 0
        self.stacked_widget.addWidget(self.pagina_usuarios)      # 1
        self.stacked_widget.addWidget(self.pagina_lecturas)      # 2
        self.stacked_widget.addWidget(self.pagina_lectores)      # 3
        self.stacked_widget.addWidget(self.pagina_cobros)        # 4
        self.stacked_widget.addWidget(self.pagina_configuracion)  # 5

        layout_principal.addWidget(self.stacked_widget, stretch=1)

        # 4. Pie de Página / Barra de Estado
        barra_estado = self._crear_barra_estado()
        layout_principal.addWidget(barra_estado)

        # Activar pantalla de inicio por defecto
        self.navegar_a("inicio")

    def _crear_banner_contingencia(self) -> QFrame:
        banner = QFrame()
        banner.setStyleSheet("""
            QFrame {
                background-color: #fef3c7;
                border-bottom: 1px solid #fde68a;
                padding: 6px 16px;
            }
        """)
        lay = QHBoxLayout(banner)
        lay.setContentsMargins(16, 4, 16, 4)
        lbl = QLabel(
            "<b>MODO CONTINGENCIA / RESPALDO:</b> Operando sin conexión al servidor desde el archivo Excel. Los cambios se guardarán localmente.")
        lbl.setStyleSheet("color: #92400e; font-size: 13px;")
        lay.addWidget(lbl)
        lay.addStretch(1)
        return banner

    def _crear_barra_superior(self) -> QFrame:
        nav = QFrame()
        nav.setObjectName("nav_superior")
        layout = QHBoxLayout(nav)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(16)

        # Logo: [gota] CAAPD Ispacas
        lbl_logo_icono = iconos.etiqueta("droplet", "#06b6d4", 22)
        layout.addWidget(lbl_logo_icono)
        lbl_logo = QLabel('<span style="color: #06b6d4;">CAAPD</span> Ispacas')
        lbl_logo.setObjectName("nav_logo")
        lbl_logo.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(lbl_logo)

        layout.addSpacing(12)

        # Lista de enlaces / botones (6 secciones)
        items_nav = [
            ("inicio", "Inicio", "home"),
            ("usuarios", "Usuarios", "user"),
            ("lecturas", "Lecturas", "chart-bar"),
            ("lectores", "Lectores", "device-mobile"),
            ("cobros", "Cobros", "coins"),
            ("configuracion", "Configuración", "settings"),
        ]

        for clave, texto, nombre_icono in items_nav:
            btn = QPushButton(texto)
            iconos.aplicar(btn, nombre_icono, "blanco", 18)
            btn.setObjectName(f"nav_{clave}")
            btn.setProperty("class", "nav_boton")
            btn.setProperty("activo", "false")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked=False,
                                c=clave: self.navegar_a(c))
            self.botones_nav[clave] = btn
            layout.addWidget(btn)

        layout.addStretch(1)
        return nav

    def _crear_barra_estado(self) -> QFrame:
        pie = QFrame()
        pie.setObjectName("barra_estado")
        layout = QHBoxLayout(pie)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(14)

        # Texto copyright
        lbl_copy = QLabel("CAAPD Ispacas © 2026")
        lbl_copy.setObjectName("pie_texto")
        layout.addWidget(lbl_copy)
        lbl_version = QLabel(f"v{VERSION}")
        lbl_version.setObjectName("pie_texto")
        layout.addWidget(lbl_version)

        self.btn_actualizar = QPushButton("Descargar actualización")
        self.btn_actualizar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_actualizar.setStyleSheet("""
            QPushButton {
                background-color: #fff7ed; color: #9a3412;
                font-size: 11px; font-weight: 700;
                padding: 3px 10px; border: 1px solid #fdba74; border-radius: 4px;
            }
            QPushButton:hover { background-color: #ffedd5; }
        """)
        self.btn_actualizar.clicked.connect(
            self._accion_descargar_actualizacion)
        self.btn_actualizar.hide()
        layout.addWidget(self.btn_actualizar)
        btn_abrir_bd = QPushButton("Base de datos")
        iconos.aplicar(btn_abrir_bd, "database", "exito", 14)
        btn_abrir_bd.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_abrir_bd.setStyleSheet("""
            QPushButton {
                background-color: #f0fdf4; color: #166534;
                font-size: 11px; font-weight: 600;
                padding: 3px 8px; border: 1px solid #bbf7d0; border-radius: 4px;
            }
            QPushButton:hover { background-color: #dcfce7; }
        """)
        btn_abrir_bd.clicked.connect(self._accion_abrir_carpeta_base_datos)
        layout.addWidget(btn_abrir_bd)

        # Barrita de progreso y estado
        self.lbl_estado_progreso = QLabel("")
        self.lbl_estado_progreso.setStyleSheet(
            "color: #0369a1; font-size: 11px; font-weight: 600;")
        self.lbl_estado_progreso.hide()
        layout.addWidget(self.lbl_estado_progreso)

        self.barra_progreso = QProgressBar()
        self.barra_progreso.setFixedHeight(12)
        self.barra_progreso.setFixedWidth(130)
        self.barra_progreso.setTextVisible(False)
        self.barra_progreso.setStyleSheet("""
            QProgressBar {
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                background-color: #f1f5f9;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #0284c7;
                border-radius: 5px;
            }
        """)
        self.barra_progreso.hide()
        layout.addWidget(self.barra_progreso)

        layout.addStretch(1)

        # Contadores de operaciones
        self.lbl_lecturas = QLabel("Lecturas: 0")
        self.lbl_lecturas.setObjectName("pie_chip")
        layout.addWidget(self.lbl_lecturas)

        self.lbl_escrituras = QLabel("Escrituras: 0")
        self.lbl_escrituras.setObjectName("pie_chip")
        layout.addWidget(self.lbl_escrituras)

        lbl_limite = QLabel("Límite diario: 50 000 lect. / 20 000 escrit.")
        lbl_limite.setObjectName("pie_texto")
        layout.addWidget(lbl_limite)

        return pie

    def navegar_a(self, clave_pagina: str) -> None:
        """Cambia la página actual y actualiza el estado de los botones de navegación."""
        if self.sincronizando:
            return

        abrir_asistente = False
        if clave_pagina == "recibos":
            clave_pagina = "cobros"
        elif clave_pagina.startswith("cobros"):
            if ":emitir" in clave_pagina:
                abrir_asistente = True
            clave_pagina = "cobros"

        if clave_pagina not in self.PAGINAS:
            return

        indice = self.PAGINAS.index(clave_pagina)
        self.stacked_widget.setCurrentIndex(indice)

        if clave_pagina == "usuarios" and not self.pagina_usuarios.lista_usuarios_completa:
            self.pagina_usuarios.cargar_datos_asincrono()
        elif clave_pagina == "lecturas" and not self.pagina_lecturas.lista_items_completa:
            self.pagina_lecturas.cargar_datos_asincrono()
        elif clave_pagina == "lectores" and not self.pagina_lectores.lista_lectores_completa:
            self.pagina_lectores.cargar_datos_asincrono()
        elif clave_pagina == "cobros":
            if not self.pagina_cobros.lista_items_completa:
                self.pagina_cobros.cargar_datos_asincrono()
            else:
                self.pagina_cobros._actualizar_menu_periodos()
            if abrir_asistente:
                QTimer.singleShot(
                    150, self.pagina_cobros.abrir_asistente_recibos)
        elif clave_pagina == "configuracion" and not getattr(self.pagina_configuracion, "config_cargada", False):
            self.pagina_configuracion.cargar_datos_asincrono()

        # Actualizar estilo de botones
        for c, btn in self.botones_nav.items():
            activo_val = "true" if c == clave_pagina else "false"
            btn.setProperty("activo", activo_val)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def actualizar_barra_estado(self) -> None:
        """Actualiza los contadores de sesión sin iniciar consultas de red."""
        self._pintar_contadores_locales()

    def _programar_consulta_metricas(self, retraso_ms: int) -> None:
        """Agenda (con rebote) una consulta a Cloud Monitoring en segundo plano."""
        if getattr(self.servicio, "es_memoria", False):
            return
        self._timer_metricas.start(max(0, int(retraso_ms)))

    def _consultar_metricas_nube(self) -> None:
        if self._consultando_metricas:
            return
        self._consultando_metricas = True
        from servicios.metricas_monitoring import consultar_metricas_hoy

        def al_terminar(res) -> None:
            self._consultando_metricas = False
            self._metricas_nube = res if isinstance(res, dict) else None
            self._pintar_contadores_locales()

        def al_error(_err: str) -> None:
            self._consultando_metricas = False

        worker = Worker(lambda: consultar_metricas_hoy(forzar=True))
        worker.signals.resultado.connect(al_terminar)
        worker.signals.error.connect(al_error)
        self._worker_metricas = worker
        QThreadPool.globalInstance().start(worker)

    @staticmethod
    def _fmt_miles(n: int) -> str:
        return f"{int(n):,}".replace(",", " ")

    def _pintar_contadores_locales(self) -> None:
        """
        Pie de página: operaciones Firestore de HOY.
        - Si Cloud Monitoring responde: total EXACTO del proyecto (igual que la
          consola de Firebase; incluye app móvil y consola).
        - Si no (sin permiso / sin internet): lo realizado desde esta PC.
        """
        local = self.servicio.get_ops()
        l_lect = int(local.get("lecturas", 0))
        l_escr = int(local.get("escrituras", 0))
        nube = self._metricas_nube if getattr(self, "_metricas_nube", None) else None

        sufijo = ""
        if nube and nube.get("disponible"):
            n_lect = int(nube.get("lecturas", 0))
            n_escr = int(nube.get("escrituras", 0))
            desde = nube.get("desde_pacifico") or "00:00 hora del Pacífico"
            elim = int(nube.get("eliminaciones", 0) or 0)
            tooltip = (
                "Total EXACTO de Google (Cloud Monitoring) para todo el proyecto: incluye esta PC, "
                f"la app móvil de los lectores y la consola.\nContado desde {desde}. "
                "Google tarda 1-3 minutos en reflejar las últimas operaciones.\n"
                f"Escrituras incluye {self._fmt_miles(elim)} eliminaciones (consumen la misma cuota).\n"
                f"Solo esta PC hoy: {self._fmt_miles(l_lect)} lecturas / {self._fmt_miles(l_escr)} escrituras."
            )
        else:
            n_lect, n_escr = l_lect, l_escr
            es_memoria = getattr(self.servicio, "es_memoria", False)
            consultando = getattr(self, "_consultando_metricas", False) or (
                nube is None and not es_memoria)
            if es_memoria:
                motivo = "no aplica (datos en memoria)"
            elif consultando:
                sufijo = " (esta PC, consultando a Google…)"
                motivo = "consultando…"
            else:
                sufijo = " (esta PC)"
                motivo = (nube or {}).get("error") or "sin respuesta"
            tooltip = (
                "Operaciones realizadas desde esta PC en el día de hoy (se reinicia a las 00:00 hora "
                "del Pacífico, igual que la cuota gratuita de Google).\n"
                "No incluye la app móvil ni la consola.\n"
                f"Total exacto de Google no disponible: {motivo}\n"
                "Detalle en logs\\metricas.log junto al programa."
            )

        self.lbl_lecturas.setText(f"Lecturas: {self._fmt_miles(n_lect)}{sufijo}")
        self.lbl_escrituras.setText(f"Escrituras: {self._fmt_miles(n_escr)}")
        self.lbl_lecturas.setToolTip(tooltip)
        self.lbl_escrituras.setToolTip(tooltip)

        # Color de aviso al acercarse al límite diario (80 %) o superarlo
        for lbl, usado, limite in (
            (self.lbl_lecturas, n_lect, 50_000),
            (self.lbl_escrituras, n_escr, 20_000),
        ):
            nivel = "peligro" if usado >= limite else (
                "aviso" if usado >= limite * 0.8 else "")
            if lbl.property("nivel") != nivel:
                lbl.setProperty("nivel", nivel)
                lbl.setStyleSheet(
                    "background-color: #dc2626; color: #ffffff;" if nivel == "peligro" else
                    "background-color: #f59e0b; color: #1f2937;" if nivel == "aviso" else ""
                )

    def set_sincronizando(self, activo: bool) -> None:
        """Pausa la vigilancia de archivos mientras el propio programa escribe los Excel."""
        self.sincronizando = bool(activo)
        if not activo and hasattr(self.servicio, "reconocer_cambios_externos"):
            # Los Excel acaban de ser escritos por el programa: no son cambios externos.
            self.servicio.reconocer_cambios_externos()

    def _verificar_archivos_externos(self) -> None:
        """Comprueba si algún archivo en 'Base de datos/' fue modificado externamente."""
        if self._verificando_archivos or self.sincronizando:
            return
        # Si hay un Worker activo (sincronización, recarga, PDF...) esperar al siguiente ciclo.
        if QThreadPool.globalInstance().activeThreadCount() > 0:
            return
        if not hasattr(self.servicio, "verificar_cambios_externos"):
            return

        hay_cambios, modificados = self.servicio.verificar_cambios_externos()
        if not hay_cambios:
            return

        self._verificando_archivos = True
        self.timer_archivos.stop()
        arch_str = ", ".join(modificados[:3])

        # Reconocer cambios inmediatamente para evitar cualquier reaparición en bucle
        if hasattr(self.servicio, "reconocer_cambios_externos"):
            self.servicio.reconocer_cambios_externos()

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setWindowTitle("Archivos Modificados Externamente")
        msg.setText(
            "<b>Se detectaron cambios en los archivos de 'Base de datos':</b>")
        msg.setInformativeText(
            f"Uno o más archivos fueron modificados externamente:\n\n"
            f"  • {arch_str}\n\n"
            f"¿Deseas recargar la base de datos en pantalla ahora?"
        )
        btn_si = msg.addButton("Sí", QMessageBox.ButtonRole.YesRole)
        msg.addButton("No", QMessageBox.ButtonRole.NoRole)
        msg.setDefaultButton(btn_si)
        msg.exec()

        if msg.clickedButton() == btn_si and hasattr(self.servicio, "cargar_desde_carpeta_base_datos"):
            # Recarga pesada (lee todos los Excel) -> en segundo plano, NUNCA en el hilo GUI.
            self.sincronizando = True
            self.mostrar_progreso(30, "Recargando base de datos...")
            worker = Worker(self.servicio.cargar_desde_carpeta_base_datos)
            worker.signals.resultado.connect(
                self._al_terminar_recarga_externa, Qt.ConnectionType.QueuedConnection)
            worker.signals.error.connect(
                self._al_fallar_recarga_externa, Qt.ConnectionType.QueuedConnection)
            QThreadPool.globalInstance().start(worker)
        else:
            self._verificando_archivos = False
            self.timer_archivos.start()

    @Slot(object)
    def _al_terminar_recarga_externa(self, _res: Any) -> None:
        self.set_sincronizando(False)
        self.ocultar_progreso("¡Base de datos recargada!")
        idx = self.stacked_widget.currentIndex()
        if 0 <= idx < len(self.PAGINAS):
            self.navegar_a(self.PAGINAS[idx])
        if idx == 0:
            self.pagina_inicio.cargar_datos_asincrono()
        self._verificando_archivos = False
        self.timer_archivos.start()

    @Slot(str)
    def _al_fallar_recarga_externa(self, err_msg: str) -> None:
        self.set_sincronizando(False)
        self.ocultar_progreso("")
        mostrar_dialogo_error(
            self, "Error al recargar la base de datos", err_msg)
        self._verificando_archivos = False
        self.timer_archivos.start()

    def _accion_abrir_carpeta_base_datos(self) -> None:
        p = rutas.ruta_base_de_datos()
        try:
            os.startfile(p)
        except Exception:
            pass

    def _en_hilo_gui(self) -> bool:
        """True si el código actual se ejecuta en el hilo principal de la interfaz."""
        return QThread.currentThread() is self.thread()

    def mostrar_progreso(self, porcentaje: int, texto: str = "") -> None:
        """Actualiza y muestra la barrita de progreso inferior (seguro desde cualquier hilo)."""
        if not self._en_hilo_gui():
            # Llamado desde un Worker: reenviar al hilo GUI mediante señal en cola.
            self._senal_progreso.emit(int(porcentaje), str(texto or ""))
            return
        self._mostrar_progreso_ui(porcentaje, texto)

    def _mostrar_progreso_ui(self, porcentaje: int, texto: str = "") -> None:
        """Actualiza los widgets. SOLO debe ejecutarse en el hilo GUI."""
        self.barra_progreso.setValue(int(porcentaje))
        self.barra_progreso.show()
        if texto:
            self.lbl_estado_progreso.setText(texto)
            self.lbl_estado_progreso.show()

    def ocultar_progreso(self, texto_final: str = "") -> None:
        """Oculta la barrita de progreso (seguro desde cualquier hilo)."""
        if not self._en_hilo_gui():
            self._senal_ocultar_progreso.emit(str(texto_final or ""))
            return
        self._ocultar_progreso_ui(texto_final)

    def _ocultar_progreso_ui(self, texto_final: str = "") -> None:
        """Oculta los widgets. SOLO debe ejecutarse en el hilo GUI."""
        if texto_final:
            self.lbl_estado_progreso.setText(texto_final)
            QTimer.singleShot(2500, self._limpiar_progreso)
        else:
            self._limpiar_progreso()

    def _limpiar_progreso(self) -> None:
        self.barra_progreso.hide()
        self.lbl_estado_progreso.hide()
        self.lbl_estado_progreso.setText("")

    def closeEvent(self, event: QCloseEvent) -> None:
        """Cierre seguro: detiene temporizadores y espera a los hilos de trabajo."""
        try:
            from servicios import contador_ops
            contador_ops.desuscribir(getattr(self, "_cb_ops", None))
        except Exception:
            pass
        for t in (getattr(self, "_timer_metricas", None), getattr(self, "_timer_refresco_metricas", None)):
            if t is not None:
                t.stop()
        if self.sincronizando:
            QMessageBox.information(
                self,
                "Sincronización en curso",
                "Espera a que termine la sincronización antes de cerrar la aplicación.",
            )
            event.ignore()
            return
        if not esperar_hilos(1000):
            QMessageBox.information(
                self,
                "Operación en curso",
                "La aplicación no se cerró porque todavía hay una tarea en segundo plano. "
                "Espera a que termine o falle y vuelve a cerrar el programa.",
            )
            event.ignore()
            return

        self._verificando_archivos = True
        self.sincronizando = True
        try:
            self.timer_archivos.stop()
        except Exception:
            pass
        event.accept()
        # main.py desactiva quitOnLastWindowClosed: el programa termina SOLO aquí,
        # cuando el usuario cierra la ventana principal y no hay Workers activos.
        app = QApplication.instance()
        if app is not None:
            QTimer.singleShot(0, app.quit)

    # ------------------------------------------------------------------
    # Auto-actualización
    # ------------------------------------------------------------------
    def _buscar_actualizacion(self) -> None:
        self._hilo_buscar = _HiloBuscarActualizacion(self)
        self._hilo_buscar.encontrada.connect(self._al_encontrar_actualizacion)
        self._hilo_buscar.start()

    @Slot(object)
    def _al_encontrar_actualizacion(self, info) -> None:
        if info is None:
            return
        self._info_actualizacion = info
        self.btn_actualizar.setText(f"Descargar actualización v{info.version}")
        self.btn_actualizar.show()

    def _accion_descargar_actualizacion(self) -> None:
        info = self._info_actualizacion
        if info is None:
            return
        notas = info.notas.strip() or "Mejoras y correcciones."
        resp = QMessageBox.question(
            self,
            f"Actualizar a v{info.version}",
            f"Hay una nueva versión disponible (v{info.version}).\n\n"
            f"Novedades:\n{notas[:800]}\n\n"
            "La aplicación se cerrará, se actualizará y volverá a abrirse.\n"
            "Sus datos, respaldos y credenciales NO se modifican.\n\n¿Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        self.btn_actualizar.setEnabled(False)
        self.mostrar_progreso(0, "Descargando actualización…")
        self._hilo_descarga = _HiloDescargar(info, self)
        self._hilo_descarga.progreso.connect(
            lambda p: self.mostrar_progreso(p, f"Descargando actualización… {p}%"))
        self._hilo_descarga.terminado.connect(self._al_terminar_descarga)
        self._hilo_descarga.error.connect(self._al_fallar_descarga)
        self._hilo_descarga.start()

    @Slot(object)
    def _al_terminar_descarga(self, ruta_zip) -> None:
        self.ocultar_progreso("Actualización descargada")
        try:
            actualizador.aplicar_y_reiniciar(ruta_zip)
        except Exception as e:
            QMessageBox.critical(self, "Error al actualizar", str(e))
            self.btn_actualizar.setEnabled(True)
            return
        # Cerrar limpio: el .bat espera a que este proceso termine y relanza
        esperar_hilos(5000)
        QApplication.quit()

    @Slot(str)
    def _al_fallar_descarga(self, msg: str) -> None:
        self.ocultar_progreso("")
        self.btn_actualizar.setEnabled(True)
        QMessageBox.warning(self, "No se pudo descargar",
                            f"Error al descargar la actualización:\n{msg}\n\nIntente más tarde.")
