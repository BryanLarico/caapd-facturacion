"""
main.py — Punto de entrada del programa de escritorio CAAPD Ispacas.

Inicia la aplicación PySide6, aplica fuentes y tema QSS, y abre la ventana principal.
"""
from ui.ventana_principal import VentanaPrincipal
from ui.hilos import (
    RecolectorBasuraGUI,
    esperar_hilos,
    instalar_diagnostico_cierre,
    precargar_firebase_en_hilo_principal,
)
from servicios.cancelacion import marcar_cierre
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPalette
from PySide6.QtCore import QThreadPool
import rutas
from pathlib import Path
import faulthandler
import sys
import os
import warnings

# Silenciar el aviso de Google sobre Python 3.10 (no es un error; solo ruido en consola)
warnings.filterwarnings("ignore", category=FutureWarning, module=r"google\..*")

# Configuración inicial de rutas

if "--worker-descarga-lecturas" in sys.argv:
    sys.argv.remove("--worker-descarga-lecturas")
    import os
    from servicios.descarga_lecturas_proc import main as main_descarga_lecturas

    os._exit(main_descarga_lecturas())


# Importar firebase_admin/gRPC desde el hilo principal poco después de abrir la
# ventana. Evita que la PRIMERA importación del código nativo de gRPC ocurra dentro
# de un hilo del QThreadPool (causa de cierres silenciosos en Windows al usar
# «Extraer lecturas de los lectores» / «Enviar mes a los lectores»).
PRECARGAR_FIREBASE_AL_INICIO = True
RETARDO_PRECARGA_MS = 1500


def aplicar_paleta_clara(app: QApplication) -> None:
    """Fuerza una paleta clara. Evita que Windows en modo oscuro tiña de negro
    los widgets que el QSS no cubre (contenedor de desplegables, menús, etc.)."""
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor("#f0f9ff"))
    pal.setColor(QPalette.ColorRole.WindowText, QColor("#0f172a"))
    pal.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#f8fafc"))
    pal.setColor(QPalette.ColorRole.Text, QColor("#0f172a"))
    pal.setColor(QPalette.ColorRole.Button, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor("#0f172a"))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor("#0f172a"))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor("#94a3b8"))
    pal.setColor(QPalette.ColorRole.Highlight, QColor("#0369a1"))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.Link, QColor("#0369a1"))
    pal.setColor(QPalette.ColorRole.Light, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.Midlight, QColor("#e2e8f0"))
    pal.setColor(QPalette.ColorRole.Mid, QColor("#cbd5e1"))
    pal.setColor(QPalette.ColorRole.Dark, QColor("#94a3b8"))
    pal.setColor(QPalette.ColorRole.Shadow, QColor("#64748b"))
    app.setPalette(pal)


def configurar_fuentes(app: QApplication) -> None:
    """Intenta cargar la fuente empaquetada Inter; si falla, recurre a Segoe UI."""
    fuente_cargada = False
    ruta_inter = rutas.ruta_fuentes("Inter-Variable.ttf")

    if ruta_inter.exists():
        font_id = QFontDatabase.addApplicationFont(str(ruta_inter))
        if font_id != -1:
            familias = QFontDatabase.applicationFontFamilies(font_id)
            if familias:
                app.setFont(QFont(familias[0], 10))
                fuente_cargada = True

    if not fuente_cargada:
        # Fallback del sistema en Windows
        app.setFont(QFont("Segoe UI", 10))


def cargar_estilos(app: QApplication) -> None:
    """Carga y aplica la hoja de estilos tema.qss."""
    ruta_qss = rutas.ruta_recurso("ui", "estilos", "tema.qss")
    if ruta_qss.exists():
        with open(ruta_qss, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())


def main() -> None:
    rutas.preparar_directorios()

    # Registro de fallos nativos (cierres sin traceback): escritorio/logs/crash.log
    try:
        ruta_crash = rutas.ruta_aplicacion("logs", "crash.log")
        ruta_crash.parent.mkdir(parents=True, exist_ok=True)
        _archivo_crash = open(ruta_crash, "a", encoding="utf-8")
        faulthandler.enable(file=_archivo_crash, all_threads=True)
    except Exception:
        pass

    if sys.platform == "win32":
        os.environ.setdefault("QT_QPA_PLATFORM", "windows:darkmode=0")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    aplicar_paleta_clara(app)
    app.setApplicationName("CAAPD Ispacas Facturación")

    # El programa SOLO termina cuando el usuario cierra la ventana principal
    # (VentanaPrincipal.closeEvent llama a app.quit()). Así, ningún diálogo,
    # ventana auxiliar o estado transitorio puede provocar que Qt salga del
    # bucle de eventos mientras un Worker sigue trabajando.
    app.setQuitOnLastWindowClosed(False)
    # Deja en logs/hilos.log el motivo de cualquier cierre (lastWindowClosed,
    # aboutToQuit, excepciones no capturadas) para diagnosticar cierres sin traceback.
    instalar_diagnostico_cierre(app)

    app._recolector_gc = RecolectorBasuraGUI(app)

    # Configuración de estilos y tipografía
    configurar_fuentes(app)
    cargar_estilos(app)

    # Servicio de datos: Local-First por defecto desde Padrones Excel (0 lecturas a Firebase en arranque)
    servicio_datos = None
    if "--firebase" in sys.argv:
        from servicios.datos import ServicioDatosFirebase
        servicio_datos = ServicioDatosFirebase()
    elif "--contingencia" in sys.argv:
        from servicios.datos_contingencia import ServicioDatosContingencia
        try:
            servicio_datos = ServicioDatosContingencia()
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(None, "Error de Contingencia", str(e))
            sys.exit(1)
    else:
        from servicios.datos_padron import ServicioDatosPadron
        servicio_datos = ServicioDatosPadron()

    # Ventana principal
    ventana = VentanaPrincipal(servicio_datos)
    ventana.showMaximized()

    # Carga de datos asíncrona de Inicio (la ventana se muestra inmediatamente)
    ventana.pagina_inicio.cargar_datos_asincrono()

    # Precarga de Firebase/gRPC en el hilo principal (solo importación, 0 lecturas).
    if PRECARGAR_FIREBASE_AL_INICIO:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(RETARDO_PRECARGA_MS,
                          precargar_firebase_en_hilo_principal)

    # Antes de destruir QApplication, esperar a los Workers del pool (cierre limpio).
    app.aboutToQuit.connect(marcar_cierre)
    app.aboutToQuit.connect(lambda: esperar_hilos(5000))

    codigo = app.exec()
    pool = QThreadPool.globalInstance()
    pool.clear()
    pool.waitForDone(5000)
    ventana.deleteLater()
    app.processEvents()
    del ventana
    sys.exit(codigo)


if __name__ == "__main__":
    main()
