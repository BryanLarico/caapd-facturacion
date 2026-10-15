"""
main.py — Punto de entrada del programa de escritorio CAAPD Ispacas.

Inicia la aplicación PySide6, aplica fuentes y tema QSS, y abre la ventana principal.
"""
from pathlib import Path
import sys

# Configuración inicial de rutas
import rutas

from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication

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

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
