"""
main.py — Punto de entrada del programa de escritorio CAAPD Ispacas.

Inicia la aplicación PySide6, aplica fuentes y tema QSS, y abre la ventana principal.
"""
from pathlib import Path
import faulthandler
import sys
import warnings

# Silenciar el aviso de Google sobre Python 3.10 (no es un error; solo ruido en consola)
warnings.filterwarnings("ignore", category=FutureWarning, module=r"google\..*")

# Configuración inicial de rutas
import rutas

from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication

from ui.hilos import esperar_hilos
from ui.ventana_principal import VentanaPrincipal


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

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("CAAPD Ispacas Facturación")

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

    # Antes de destruir QApplication, esperar a los Workers del pool (cierre limpio).
    app.aboutToQuit.connect(lambda: esperar_hilos(5000))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
