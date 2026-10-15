"""
ui/ventana_principal.py — Ventana principal de la aplicación de escritorio CAAPD Ispacas.

Integra la barra superior de navegación, el QStackedWidget con las 7 pantallas,
banners de modo contingencia y cola offline, botones de respaldo y control de cierre seguro.
"""
import os
from typing import Dict, Optional

from PySide6.QtCore import QTimer, Qt
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

import respaldo
import rutas
from servicios import cola_offline
from servicios.datos import ServicioDatos
from servicios.metricas_monitoring import consultar_metricas_hoy
from ui.paginas.cobros import PaginaCobros
from ui.paginas.configuracion import PaginaConfiguracion
from ui.paginas.inicio import PaginaInicio
from ui.paginas.lectores import PaginaLectores
from ui.paginas.lecturas import PaginaLecturas
from ui.paginas.usuarios import PaginaUsuarios


class VentanaPrincipal(QMainWindow):
    """Ventana principal que gestiona la navegación y el estado global."""

    PAGINAS = ["inicio", "usuarios", "lecturas", "lectores", "cobros", "configuracion"]

    def __init__(
        self,
        servicio_datos: ServicioDatos,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.servicio = servicio_datos

        titulo = "CAAPD Ispacas — Facturación [ENTORNO DE PRUEBA]" if rutas.es_entorno_prueba() else "CAAPD Ispacas — Facturación"
        self.setWindowTitle(titulo)
        self.resize(1180, 780)
        self.setMinimumSize(960, 600)

        self.botones_nav: Dict[str, QPushButton] = {}

        self._construir_ui()
        self.actualizar_barra_estado()

        # Temporizador para verificar y sincronizar cola offline cada 60s
        self.timer_cola = QTimer(self)
        self.timer_cola.setInterval(60000)
        self.timer_cola.timeout.connect(self._verificar_y_sincronizar_cola)
        self.timer_cola.start()

        # Actualizar visibilidad inicial de banners
        self._actualizar_banner_cola()

    def _construir_ui(self) -> None:
        widget_central = QWidget()
        widget_central.setObjectName("widget_central")
        self.setCentralWidget(widget_central)

        layout_principal = QVBoxLayout(widget_central)
        layout_principal.setContentsMargins(0, 0, 0, 0)
        layout_principal.setSpacing(0)

        # 0. Banner permanente de Entorno de Prueba si CAAPD_ENTORNO=prueba
        if rutas.es_entorno_prueba():
            banner_prueba = QFrame()
            banner_prueba.setStyleSheet("background-color: #FEF3C7; border-bottom: 2px solid #F59E0B; padding: 4px;")
            l_pb = QHBoxLayout(banner_prueba)
            l_pb.setContentsMargins(16, 4, 16, 4)
            lbl_pb = QLabel("⚠️ <b>ENTORNO DE PRUEBA ACTIVO</b> — Bases de datos y respaldos aislados en 'Base de datos PRUEBA'")
            lbl_pb.setStyleSheet("color: #92400E; font-size: 12px;")
            l_pb.addWidget(lbl_pb)
            layout_principal.addWidget(banner_prueba)

        # 1. Barra Superior de Navegación
        nav_superior = self._crear_barra_superior()
        layout_principal.addWidget(nav_superior)

        # 2. Banners de Estado (Contingencia y Cola Offline)
        self.banner_contingencia = self._crear_banner_contingencia()
        layout_principal.addWidget(self.banner_contingencia)
        if not getattr(self.servicio, "es_contingencia", False):
            self.banner_contingencia.hide()

        self.banner_cola = self._crear_banner_cola()
        layout_principal.addWidget(self.banner_cola)
        self.banner_cola.hide()

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

    def _crear_banner_cola(self) -> QFrame:
        banner = QFrame()
        banner.setStyleSheet("""
            QFrame {
                background-color: #ffedd5;
                border-bottom: 1px solid #fed7aa;
                padding: 4px 16px;
            }
        """)
        lay = QHBoxLayout(banner)
        lay.setContentsMargins(16, 4, 16, 4)
        self.lbl_cola_texto = QLabel("⚠️ Hay 0 cambio(s) pendiente(s) de sincronizar con el servidor.")
        self.lbl_cola_texto.setStyleSheet("color: #9a3412; font-size: 13px; font-weight: 500;")
        lay.addWidget(self.lbl_cola_texto)

        btn_sinc = QPushButton("🔄 Sincronizar ahora")
        btn_sinc.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_sinc.setStyleSheet("""
            QPushButton {
                background-color: #ea580c; color: #ffffff;
                font-weight: bold; font-size: 11px;
                padding: 4px 10px; border-radius: 4px;
            }
            QPushButton:hover { background-color: #c2410c; }
        """)
        btn_sinc.clicked.connect(self._verificar_y_sincronizar_cola)
        lay.addWidget(btn_sinc)
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

        # Info de Respaldo
        self.lbl_ultimo_respaldo = QLabel("Último respaldo: —")
        self.lbl_ultimo_respaldo.setStyleSheet("color: #64748b; font-size: 11px;")
        layout.addWidget(self.lbl_ultimo_respaldo)

        btn_resp_ahora = QPushButton("💾 Respaldar ahora")
        btn_resp_ahora.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_resp_ahora.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9; color: #334155;
                font-size: 11px; font-weight: 500;
                padding: 3px 8px; border: 1px solid #cbd5e1; border-radius: 4px;
            }
            QPushButton:hover { background-color: #e2e8f0; }
        """)
        btn_resp_ahora.clicked.connect(self._accion_respaldar_ahora)
        layout.addWidget(btn_resp_ahora)

        btn_abrir_resp = QPushButton("📂 Respaldos")
        btn_abrir_resp.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_abrir_resp.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9; color: #334155;
                font-size: 11px; font-weight: 500;
                padding: 3px 8px; border: 1px solid #cbd5e1; border-radius: 4px;
            }
            QPushButton:hover { background-color: #e2e8f0; }
        """)
        btn_abrir_resp.clicked.connect(self._accion_abrir_carpeta_respaldos)
        layout.addWidget(btn_abrir_resp)

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
        """Actualiza los contadores de operaciones y fecha de respaldo en la barra inferior."""
        met_cloud = consultar_metricas_hoy()

        if met_cloud.get("disponible"):
            n_lect = met_cloud.get("lecturas", 0)
            n_escr = met_cloud.get("escrituras", 0)
            desde = met_cloud.get("desde_pacifico", "hoy")
            self.lbl_lecturas.setText(f"🔥 Hoy: {n_lect:,} lecturas".replace(",", " "))
            self.lbl_escrituras.setText(f"🔥 Hoy: {n_escr:,} escrituras".replace(",", " "))
            tooltip = f"Métricas reales de Google Cloud Monitoring (desde 00:00 Pacífico: {desde}). No consume cuota de Firestore."
            self.lbl_lecturas.setToolTip(tooltip)
            self.lbl_escrituras.setToolTip(tooltip)
        else:
            ops = self.servicio.get_ops()
            n_lect = ops.get("lecturas", 0)
            n_escr = ops.get("escrituras", 0)
            self.lbl_lecturas.setText(f"Lecturas: {n_lect}")
            self.lbl_escrituras.setText(f"Escrituras: {n_escr}")
            err = met_cloud.get("error") or "Rol 'Monitoring Viewer' pendiente en GCP"
            tooltip = f"Contador de sesión local. Para ver el consumo total en la nube, asigna el rol 'Monitoring Viewer' en Google Cloud Console ({err})."
            self.lbl_lecturas.setToolTip(tooltip)
            self.lbl_escrituras.setToolTip(tooltip)

        # Info del último respaldo
        info_resp = respaldo.obtener_info_ultimo_respaldo()
        if info_resp.get("fecha_hora"):
            self.lbl_ultimo_respaldo.setText(f"Último respaldo: {info_resp['fecha_hora']}")
        else:
            self.lbl_ultimo_respaldo.setText("Último respaldo: Pendiente")

    def _actualizar_banner_cola(self) -> None:
        n_pend = cola_offline.cantidad_pendientes()
        if n_pend > 0:
            self.lbl_cola_texto.setText(f"⚠️ Hay {n_pend} cambio(s) pendiente(s) de sincronizar con el servidor.")
            self.banner_cola.show()
        else:
            self.banner_cola.hide()

    def _verificar_y_sincronizar_cola(self) -> None:
        if getattr(self.servicio, "es_contingencia", False) or getattr(self.servicio, "es_local_first", False):
            self._actualizar_banner_cola()
            return

        res = cola_offline.sincronizar_cola(self.servicio)
        self._actualizar_banner_cola()
        if res["enviados"] > 0:
            self.actualizar_barra_estado()

    def _accion_respaldar_ahora(self) -> None:
        ruta = respaldo.ejecutar_respaldo_ahora()
        self.actualizar_barra_estado()
        if ruta and ruta.exists():
            QMessageBox.information(
                self,
                "Respaldo Completado",
                f"El respaldo en Excel se generó exitosamente en:\n\n{ruta}",
            )
        else:
            QMessageBox.warning(
                self,
                "Aviso de Respaldo",
                "El respaldo se programó pero no se completó de inmediato.",
            )

    def _accion_abrir_carpeta_respaldos(self) -> None:
        p = rutas.ruta_respaldos()
        try:
            os.startfile(p)
        except Exception:
            pass

    def _accion_abrir_carpeta_base_datos(self) -> None:
        p = rutas.ruta_base_de_datos()
        try:
            os.startfile(p)
        except Exception:
            pass

    def mostrar_progreso(self, porcentaje: int, texto: str = "") -> None:
        """Actualiza y muestra la barrita de progreso inferior."""
        self.barra_progreso.setValue(porcentaje)
        self.barra_progreso.show()
        if texto:
            self.lbl_estado_progreso.setText(texto)
            self.lbl_estado_progreso.show()

    def ocultar_progreso(self, texto_final: str = "") -> None:
        """Oculta la barrita de progreso."""
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
        """Control de cierre seguro: advierte de cambios offline y genera respaldo final."""
        n_pend = cola_offline.cantidad_pendientes()
        if n_pend > 0:
            resp = QMessageBox.question(
                self,
                "Cambios Pendientes sin Sincronizar",
                f"Hay {n_pend} cambio(s) pendiente(s) de sincronizar con el servidor.\n"
                f"Estos cambios se conservarán en disco para cuando se restablezca la conexión.\n\n"
                f"¿Está seguro de cerrar el programa ahora?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if resp != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        # Detener temporizadores activos
        try:
            self.timer_cola.stop()
        except Exception:
            pass

        # Generar respaldo de salida con aviso (solo para servicios reales)
        if not getattr(self.servicio, "es_memoria", False):
            try:
                cfg = self.servicio.cargar_config()
                usr = self.servicio.cargar_usuarios()
                mes = getattr(self.servicio, "mes", {})
                respaldo.ejecutar_respaldo_ahora(config=cfg, usuarios=usr, mes_docs=mes)
            except Exception:
                pass

        event.accept()
