"""
ui/paginas/inicio.py — Pantalla de Inicio (Panel de control) para CAAPD Ispacas.

Réplica exacta del panel HTML con carga asíncrona, banner de estado según
CONTEXTO §3b, métricas destacadas y avance de lecturas por sector.
"""
from typing import Any, Dict, List, Optional
from PySide6.QtCore import QThreadPool, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from servicios.datos import ServicioDatos
from ui.componentes.alerta import AlertaWidget
from ui.componentes.barra_progreso_sector import BarraProgresoSector
from ui.componentes.indicador_carga import IndicadorCarga
from ui.componentes.tarjeta_stat import TarjetaStat
from ui.hilos import Worker, mostrar_dialogo_error


class PaginaInicio(QWidget):
    """Pantalla principal con panel de control y estadísticas."""

    # Señal para solicitar cambio de página en la ventana principal
    solicitar_navegacion = Signal(str)
    # Señal para notificar que las operaciones Firebase han cambiado
    datos_cargados = Signal()

    def __init__(self, servicio_datos: ServicioDatos, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.servicio = servicio_datos
        self.thread_pool = QThreadPool.globalInstance()

        self._construir_ui()

    def _construir_ui(self) -> None:
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(0, 0, 0, 0)
        layout_principal.setSpacing(0)

        # Scroll Area para permitir scroll vertical si la resolución es baja
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        # Envoltorio para centrar el contenido hasta 1260px (proporcionado y elegante)
        scroll_wrapper = QWidget()
        scroll_wrapper_layout = QHBoxLayout(scroll_wrapper)
        scroll_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        scroll_wrapper_layout.setSpacing(0)

        contenedor = QWidget()
        contenedor.setMaximumWidth(1260)
        self.layout_contenido = QVBoxLayout(contenedor)
        self.layout_contenido.setContentsMargins(24, 12, 24, 12)
        self.layout_contenido.setSpacing(10)

        scroll_wrapper_layout.addStretch(1)
        scroll_wrapper_layout.addWidget(contenedor, stretch=10)
        scroll_wrapper_layout.addStretch(1)

        # --- 1. Encabezado ---
        fila_encabezado = QHBoxLayout()
        col_titulos = QVBoxLayout()
        col_titulos.setSpacing(2)

        lbl_titulo = QLabel("Panel de control")
        lbl_titulo.setObjectName("encabezado_titulo")
        col_titulos.addWidget(lbl_titulo)

        lbl_subtitulo = QLabel("Facturación mensual de agua potable")
        lbl_subtitulo.setObjectName("encabezado_subtitulo")
        col_titulos.addWidget(lbl_subtitulo)

        fila_encabezado.addLayout(col_titulos, stretch=1)

        # Indicador de carga
        self.indicador_carga = IndicadorCarga()
        fila_encabezado.addWidget(self.indicador_carga)

        # Botón Actualizar
        self.btn_actualizar = QPushButton("🔄 Actualizar")
        self.btn_actualizar.setProperty("class", "boton boton_secundario")
        self.btn_actualizar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_actualizar.setToolTip("Limpiar caché y recargar datos desde Firebase")
        self.btn_actualizar.clicked.connect(self.actualizar_datos)
        fila_encabezado.addWidget(self.btn_actualizar)

        self.layout_contenido.addLayout(fila_encabezado)

        # --- 2. Alerta de Mensaje Flash (si hay) ---
        self.alerta_flash = AlertaWidget(mensaje="", tipo="info", cerrable=True)
        self.alerta_flash.hide()
        self.layout_contenido.addWidget(self.alerta_flash)

        # --- 3. Contenedor de Mes (Banner o Alerta amarilla) ---
        self.widget_mes_contenedor = QWidget()
        self.layout_mes = QVBoxLayout(self.widget_mes_contenedor)
        self.layout_mes.setContentsMargins(0, 0, 0, 0)
        self.layout_mes.setSpacing(8)
        self.layout_contenido.addWidget(self.widget_mes_contenedor)

        # --- 4. Tarjetas de Estadísticas (Generados, Pagados, Pendientes) ---
        self.fila_stats = QHBoxLayout()
        self.fila_stats.setSpacing(12)

        self.card_generados = TarjetaStat(numero=0, label="Recibos generados", variante="azul")
        self.card_pagados = TarjetaStat(numero=0, label="Pagados", variante="verde")
        self.card_pendientes = TarjetaStat(numero=0, label="Pendientes de pago", variante="naranja")

        self.fila_stats.addWidget(self.card_generados)
        self.fila_stats.addWidget(self.card_pagados)
        self.fila_stats.addWidget(self.card_pendientes)

        self.layout_contenido.addLayout(self.fila_stats)

        # --- 5. Avance de Lecturas por Sector ---
        self.card_sectores = QFrame()
        self.card_sectores.setProperty("class", "tarjeta")
        self.layout_card_sectores = QVBoxLayout(self.card_sectores)
        self.layout_card_sectores.setContentsMargins(16, 10, 16, 10)
        self.layout_card_sectores.setSpacing(6)

        lbl_titulo_sectores = QLabel("📊 Avance de lecturas por sector")
        lbl_titulo_sectores.setObjectName("tarjeta_titulo")
        self.layout_card_sectores.addWidget(lbl_titulo_sectores)

        self.contenedor_filas_sectores = QWidget()
        self.layout_filas_sectores = QGridLayout(self.contenedor_filas_sectores)
        self.layout_filas_sectores.setContentsMargins(0, 0, 0, 0)
        self.layout_filas_sectores.setHorizontalSpacing(20)
        self.layout_filas_sectores.setVerticalSpacing(2)
        self.layout_card_sectores.addWidget(self.contenedor_filas_sectores)

        self.layout_contenido.addWidget(self.card_sectores)

        # Espaciador inferior flexible
        self.layout_contenido.addStretch(1)

        scroll.setWidget(scroll_wrapper)
        layout_principal.addWidget(scroll)

    def cargar_datos_asincrono(self, limpiar_cache: bool = False) -> None:
        """Lanza la carga de estadísticas en un hilo secundario sin congelar la UI."""
        self.indicador_carga.iniciar("Cargando estadísticas...")
        self.btn_actualizar.setEnabled(False)

        def tarea() -> Any:
            if limpiar_cache:
                self.servicio.limpiar_cache(limpiar_config=True)
            return self.servicio.obtener_estadisticas_inicio()

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
                self.cargar_datos_asincrono(limpiar_cache=True)
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
                    self.cargar_datos_asincrono(limpiar_cache=True)
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
                    self.cargar_datos_asincrono(limpiar_cache=True)

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

        self.cargar_datos_asincrono(limpiar_cache=True)

    def _al_recibir_datos(self, resultado: Any) -> None:
        config, stats_sectores, stats_recibos = resultado
        self.renderizar_datos(config, stats_sectores, stats_recibos)
        self.datos_cargados.emit()

    def _al_fallar_carga(self, err_msg: str) -> None:
        mostrar_dialogo_error(
            self,
            "Error al consultar Firebase",
            f"No se pudieron cargar las estadísticas:\n\n{err_msg}",
        )

    def _al_finalizar_carga(self) -> None:
        self.indicador_carga.detener()
        self.btn_actualizar.setEnabled(True)

    def renderizar_datos(
        self,
        config: Dict[str, Any],
        stats_sectores: List[Dict[str, Any]],
        stats_recibos: Dict[str, int],
    ) -> None:
        """Actualiza los widgets de la pantalla con los datos procesados."""
        # 1. Renderizar Mes Actual
        self._limpiar_layout(self.layout_mes)
        mes_actual = config.get("mes_actual", {})
        periodo = mes_actual.get("periodo")

        if periodo:
            # Banner del mes activo
            banner = QFrame()
            banner.setObjectName("banner_mes")

            # Sombra suave exclusiva en banner
            sombra_banner = QGraphicsDropShadowEffect(banner)
            sombra_banner.setBlurRadius(10)
            sombra_banner.setOffset(0, 2)
            sombra_banner.setColor(QColor(3, 105, 161, 40))
            banner.setGraphicsEffect(sombra_banner)

            banner_layout = QHBoxLayout(banner)
            banner_layout.setContentsMargins(16, 10, 16, 10)
            banner_layout.setSpacing(12)

            info_layout = QVBoxLayout()
            info_layout.setSpacing(2)

            periodo_formateado = periodo.replace("-", "/")
            lbl_periodo = QLabel(periodo_formateado)
            lbl_periodo.setObjectName("banner_periodo")
            info_layout.addWidget(lbl_periodo)

            emision = mes_actual.get("fecha_emision") or "—"
            vencimiento = mes_actual.get("fecha_vencimiento") or "—"
            estado = (mes_actual.get("estado") or "ABIERTO").upper()

            lbl_detalles = QLabel(
                f"Emisión: {emision}   ·   Vencimiento: {vencimiento}   ·   Estado: {estado}"
            )
            lbl_detalles.setObjectName("banner_detalles")
            info_layout.addWidget(lbl_detalles)

            banner_layout.addLayout(info_layout, stretch=1)

            # Botones según la tabla de CONTEXTO §3b
            botones_layout = QHBoxLayout()
            botones_layout.setSpacing(8)

            if estado == "ABIERTO":
                btn1 = QPushButton("📊 Ir a Lecturas")
                btn1.setProperty("class", "boton boton_primario boton_grande")
                btn1.setCursor(Qt.CursorShape.PointingHandCursor)
                btn1.clicked.connect(lambda: self.solicitar_navegacion.emit("lecturas"))
                botones_layout.addWidget(btn1)

                btn2 = QPushButton("🔒 Cerrar lecturas")
                btn2.setProperty("class", "boton boton_secundario")
                btn2.setCursor(Qt.CursorShape.PointingHandCursor)
                btn2.clicked.connect(self._cerrar_lecturas)
                botones_layout.addWidget(btn2)

            elif estado == "CERRADO":
                btn1 = QPushButton("🧾 Generar recibos")
                btn1.setProperty("class", "boton boton_primario boton_grande")
                btn1.setCursor(Qt.CursorShape.PointingHandCursor)
                btn1.clicked.connect(lambda: self.solicitar_navegacion.emit("cobros:emitir"))
                botones_layout.addWidget(btn1)

                btn2 = QPushButton("🔓 Reabrir lecturas")
                btn2.setProperty("class", "boton boton_secundario")
                btn2.setCursor(Qt.CursorShape.PointingHandCursor)
                btn2.clicked.connect(self._reabrir_lecturas)
                botones_layout.addWidget(btn2)

            elif estado == "FACTURADO":
                btn1 = QPushButton("💰 Ir a Cobros")
                btn1.setProperty("class", "boton boton_primario boton_grande")
                btn1.setCursor(Qt.CursorShape.PointingHandCursor)
                btn1.clicked.connect(lambda: self.solicitar_navegacion.emit("cobros"))
                botones_layout.addWidget(btn1)

                btn2 = QPushButton("📅 Abrir mes nuevo")
                btn2.setProperty("class", "boton boton_exito boton_grande")
                btn2.setCursor(Qt.CursorShape.PointingHandCursor)
                btn2.clicked.connect(self.abrir_dialogo_nuevo_mes)
                botones_layout.addWidget(btn2)

            btn_respaldo = QPushButton("📥 Respaldo Excel")
            btn_respaldo.setProperty("class", "boton boton_secundario")
            btn_respaldo.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_respaldo.clicked.connect(lambda: self.solicitar_navegacion.emit("cobros"))
            botones_layout.addWidget(btn_respaldo)

            banner_layout.addLayout(botones_layout)
            self.layout_mes.addWidget(banner)

        else:
            # No hay mes activo: Alerta amarilla con botón "Abrir mes nuevo"
            alerta_frame = QFrame()
            alerta_frame.setProperty("class", "alerta alerta_aviso")
            alerta_frame.setObjectName("alerta_aviso")

            alerta_layout = QHBoxLayout(alerta_frame)
            alerta_layout.setContentsMargins(16, 12, 16, 12)
            alerta_layout.setSpacing(14)

            lbl_icono = QLabel("⚠️")
            lbl_icono.setStyleSheet("font-size: 20px; background: transparent;")
            alerta_layout.addWidget(lbl_icono)

            lbl_txt = QLabel("No hay un mes activo. Haz clic en 'Abrir mes nuevo' para iniciar.")
            lbl_txt.setProperty("class", "alerta_texto_aviso")
            lbl_txt.setStyleSheet("background: transparent;")
            alerta_layout.addWidget(lbl_txt, stretch=1)

            btn_abrir = QPushButton("📅 Abrir mes nuevo")
            btn_abrir.setProperty("class", "boton boton_exito")
            btn_abrir.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_abrir.clicked.connect(self.abrir_dialogo_nuevo_mes)
            alerta_layout.addWidget(btn_abrir)

            self.layout_mes.addWidget(alerta_frame)

        # 2. Renderizar Tarjetas de Estadísticas
        self.card_generados.set_valor(stats_recibos.get("generados", 0))
        self.card_pagados.set_valor(stats_recibos.get("pagados", 0))
        self.card_pendientes.set_valor(stats_recibos.get("pendientes", 0))

        # 3. Renderizar Avance por Sectores (distribuido en 2 columnas para pantalla compacta)
        self._limpiar_layout(self.layout_filas_sectores)
        if stats_sectores:
            num_sectores = len(stats_sectores)
            columnas = 2 if num_sectores > 3 else 1
            for idx, s in enumerate(stats_sectores):
                fila_sector = BarraProgresoSector(
                    sector=s.get("sector", ""),
                    total=s.get("total", 0),
                    leidos=s.get("leidos", 0),
                )
                if columnas == 2:
                    fila = idx // 2
                    col = idx % 2
                    self.layout_filas_sectores.addWidget(fila_sector, fila, col)
                else:
                    self.layout_filas_sectores.addWidget(fila_sector, idx, 0)
        else:
            lbl_vacio = QLabel("Sin datos — Abre un mes para ver el avance de lecturas.")
            lbl_vacio.setStyleSheet("color: #64748b; font-style: italic; padding: 12px 0;")
            lbl_vacio.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout_filas_sectores.addWidget(lbl_vacio, 0, 0, 1, 2)

    def _limpiar_layout(self, layout: Any) -> None:
        """Remueve y elimina todos los widgets hijos de un layout."""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            elif item.layout():
                sub_layout = item.layout()
                while sub_layout.count():
                    sub_item = sub_layout.takeAt(0)
                    if sub_item.widget():
                        sub_item.widget().deleteLater()

    def abrir_dialogo_nuevo_mes(self) -> None:
        """Abre el diálogo modal de validación y apertura de mes."""
        from ui.paginas.mes_dialogo import DialogoAbrirMes
        diag = DialogoAbrirMes(self.servicio, self)
        if diag.exec() == QDialog.DialogCode.Accepted:
            self.actualizar_datos()

    def _cerrar_lecturas(self) -> None:
        """Cierra el periodo de lecturas previa confirmación."""
        cfg = self.servicio.cargar_config()
        periodo = cfg.get("mes_actual", {}).get("periodo") or "activo"

        resp = QMessageBox.question(
            self,
            "Cerrar lecturas",
            f"¿Deseas cerrar el periodo de lecturas para el mes {periodo}?\n\n"
            "Al cerrar, la aplicación móvil dejará de aceptar lecturas de los lectores.\n"
            "Luego podrás proceder a generar los recibos.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        self.indicador_carga.iniciar("Cerrando lecturas...")
        self.btn_actualizar.setEnabled(False)

        def tarea():
            return self.servicio.cerrar_lecturas(periodo)

        worker = Worker(tarea)
        worker.signals.resultado.connect(lambda r: self.actualizar_datos())
        worker.signals.error.connect(lambda err: mostrar_dialogo_error(self, "Error", err))
        worker.signals.finalizado.connect(self._al_finalizar_carga)
        self.thread_pool.start(worker)

    def _reabrir_lecturas(self) -> None:
        """Reabre las lecturas si el mes estaba en estado CERRADO."""
        cfg = self.servicio.cargar_config()
        periodo = cfg.get("mes_actual", {}).get("periodo") or "activo"

        resp = QMessageBox.question(
            self,
            "Reabrir lecturas",
            f"¿Deseas reabrir el registro de lecturas para el mes {periodo}?\n\n"
            "El estado volverá a ABIERTO y la app móvil volverá a recibir lecturas.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        self.indicador_carga.iniciar("Reabriendo lecturas...")
        self.btn_actualizar.setEnabled(False)

        def tarea():
            return self.servicio.reabrir_lecturas(periodo)

        worker = Worker(tarea)
        worker.signals.resultado.connect(lambda r: self.actualizar_datos())
        worker.signals.error.connect(lambda err: mostrar_dialogo_error(self, "Error", err))
        worker.signals.finalizado.connect(self._al_finalizar_carga)
        self.thread_pool.start(worker)

