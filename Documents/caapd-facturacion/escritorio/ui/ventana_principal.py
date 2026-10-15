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
from ui.hilos import Worker, esperar_hilos, mostrar_dialogo_error
from ui.paginas.cobros import PaginaCobros
from ui.paginas.configuracion import PaginaConfiguracion
from ui.paginas.inicio import PaginaInicio
from ui.paginas.lectores import PaginaLectores
from ui.paginas.lecturas import PaginaLecturas
from ui.paginas.usuarios import PaginaUsuarios


class VentanaPrincipal(QMainWindow):
    """Ventana principal que gestiona la navegación y el estado global."""

    PAGINAS = ["inicio", "usuarios", "lecturas", "lectores", "cobros", "configuracion"]

    # Señales internas para actualizar la barra de progreso de forma segura
    # cuando mostrar_progreso()/ocultar_progreso() se invocan desde un hilo Worker.
    _senal_progreso = Signal(int, str)
    _senal_ocultar_progreso = Signal(str)

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
        self._senal_progreso.connect(self._mostrar_progreso_ui, Qt.ConnectionType.QueuedConnection)
        self._senal_ocultar_progreso.connect(self._ocultar_progreso_ui, Qt.ConnectionType.QueuedConnection)

        self.actualizar_barra_estado()

        # Temporizador para verificar cambios externos en los archivos Excel cada 15s
        self.timer_archivos = QTimer(self)
        self.timer_archivos.setInterval(15000)
        self.timer_archivos.timeout.connect(self._verificar_archivos_externos)
        self.timer_archivos.start()

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
        self.stacked_widget.addWidget(self.pagina_configuracion) # 5

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
        lbl = QLabel("🟡 <b>MODO CONTINGENCIA / RESPALDO:</b> Operando sin conexión al servidor desde el archivo Excel. Los cambios se guardarán localmente.")
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

        # Logo: 💧 CAAPD Ispacas
        lbl_logo = QLabel('💧 <span style="color: #06b6d4;">CAAPD</span> Ispacas')
        lbl_logo.setObjectName("nav_logo")
        lbl_logo.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(lbl_logo)

        layout.addSpacing(12)

        # Lista de enlaces / botones (6 secciones)
        items_nav = [
            ("inicio", "🏠 Inicio"),
            ("usuarios", "👤 Usuarios"),
            ("lecturas", "📊 Lecturas"),
            ("lectores", "📱 Lectores"),
            ("cobros", "💰 Cobros"),
            ("configuracion", "⚙️ Configuración"),
        ]

        for clave, texto in items_nav:
            btn = QPushButton(texto)
            btn.setObjectName(f"nav_{clave}")
            btn.setProperty("class", "nav_boton")
            btn.setProperty("activo", "false")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, c=clave: self.navegar_a(c))
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

        btn_abrir_bd = QPushButton("📁 Base de datos")
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
        self.lbl_estado_progreso.setStyleSheet("color: #0369a1; font-size: 11px; font-weight: 600;")
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
            if abrir_asistente:
                QTimer.singleShot(150, self.pagina_cobros.abrir_asistente_recibos)
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

    def _pintar_contadores_locales(self) -> None:
        """Muestra el contador de sesión local (se usa mientras no hay métricas de la nube)."""
        ops = self.servicio.get_ops()
        n_lect = ops.get("lecturas", 0)
        n_escr = ops.get("escrituras", 0)
        self.lbl_lecturas.setText(f"Lecturas: {n_lect}")
        self.lbl_escrituras.setText(f"Escrituras: {n_escr}")
        tooltip = (
            "Contador de sesión local. Para ver el consumo total en la nube, asigna el rol "
            "'Monitoring Viewer' en Google Cloud Console."
        )
        self.lbl_lecturas.setToolTip(tooltip)
        self.lbl_escrituras.setToolTip(tooltip)

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
        msg.setText("<b>Se detectaron cambios en los archivos de 'Base de datos':</b>")
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
            worker.signals.resultado.connect(self._al_terminar_recarga_externa, Qt.ConnectionType.QueuedConnection)
            worker.signals.error.connect(self._al_fallar_recarga_externa, Qt.ConnectionType.QueuedConnection)
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
        mostrar_dialogo_error(self, "Error al recargar la base de datos", err_msg)
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
