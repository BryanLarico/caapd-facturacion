"""
ui/componentes/dialogo_actualizar.py — Diálogo interactivo del Centro de Actualización y Base de Datos.

Permite al usuario elegir entre:
1. Recargar localmente desde la carpeta 'Base de datos/' (0 lecturas a Firebase).
2. Subir / Restaurar los padrones y meses de 'Base de datos/' hacia Firebase Firestore.
3. Descargar las lecturas registradas por los lectores móviles en Firebase.
"""
from __future__ import annotations
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import rutas


class DialogoActualizarBaseDatos(QDialog):
    """Diálogo modal para seleccionar el tipo de actualización y gestión de base de datos."""

    ACCION_LOCAL = "local"
    ACCION_SUBIR_FIREBASE = "subir_firebase"
    ACCION_DESCARGAR_FIREBASE = "descargar_firebase"
    ACCION_CANCELAR = "cancelar"

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Centro de Actualización y Base de Datos")
        self.setFixedSize(560, 470)
        self.setModal(True)
        self.resultado_accion = self.ACCION_CANCELAR

        self._construir_ui()

    def _construir_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # 1. Encabezado
        lbl_titulo = QLabel("🔄 Centro de Actualización y Base de Datos")
        lbl_titulo.setStyleSheet("font-size: 17px; font-weight: bold; color: #0f172a;")
        layout.addWidget(lbl_titulo)

        lbl_subtitulo = QLabel(
            "Selecciona qué operación deseas realizar con los padrones y Firebase:"
        )
        lbl_subtitulo.setStyleSheet("font-size: 13px; color: #475569;")
        layout.addWidget(lbl_subtitulo)

        # 2. Panel informativo de archivos detectados
        dir_bd = rutas.ruta_base_de_datos()
        archivos = [p for p in dir_bd.glob("*.xlsx") if not p.name.startswith("~$")]
        panel_info = QFrame()
        panel_info.setStyleSheet("""
            QFrame {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 10px 14px;
            }
        """)
        lay_p = QVBoxLayout(panel_info)
        lay_p.setContentsMargins(4, 4, 4, 4)
        lay_p.setSpacing(4)

        n_arch = len(archivos)
        nombres_str = ", ".join(p.name for p in archivos[:3])
        if len(archivos) > 3:
            nombres_str += f" y {len(archivos) - 3} más..."

        lbl_bd_info = QLabel(
            f"📁 <b>Carpeta 'Base de datos':</b> {n_arch} archivo(s) Excel detectado(s)<br>"
            f"<span style='color: #64748b; font-size: 11px;'>{nombres_str or 'Carpeta vacía. Puedes colocar tus archivos Excel aquí.'}</span>"
        )
        lbl_bd_info.setStyleSheet("font-size: 12px; color: #1e293b;")
        lay_p.addWidget(lbl_bd_info)
        layout.addWidget(panel_info)

        # 3. Opciones de Acción
        # Opción 1: Recargar Local
        btn_local = self._crear_tarjeta_accion(
            icono="📂",
            titulo="Recargar Padrón Local (Recomendado)",
            badge="0 lecturas a Firebase",
            badge_color="#16a34a",
            descripcion="Lee las bases presentes en la carpeta 'Base de datos' y actualiza el programa en milisegundos sin consumir tu cuota de Firebase.",
            es_primario=True,
            on_click=self._elegir_local,
        )
        layout.addWidget(btn_local)

        # Opción 2: Subir / Restaurar a Firebase
        btn_subir = self._crear_tarjeta_accion(
            icono="☁️",
            titulo="Subir / Restaurar bases a Firebase",
            badge="Escritura en lote",
            badge_color="#ea580c",
            descripcion="Sube los usuarios y meses de la carpeta 'Base de datos' a Firestore. Ideal si borraste la base en la nube o cargas bases de simulación.",
            es_primario=False,
            on_click=self._elegir_subir,
        )
        layout.addWidget(btn_subir)

        # Opción 3: Descargar de lectores móviles
        btn_descargar = self._crear_tarjeta_accion(
            icono="📥",
            titulo="Descargar de lectores móviles",
            badge="Consulta Firebase",
            badge_color="#2563eb",
            descripcion="Descarga las lecturas registradas por los lectores móviles en sus celulares y las guarda en el Excel local.",
            es_primario=False,
            on_click=self._elegir_descargar,
        )
        layout.addWidget(btn_descargar)

        layout.addStretch(1)

        # 4. Pie con botón Cancelar
        fila_pie = QHBoxLayout()
        btn_abrir_carpeta = QPushButton("📂 Abrir carpeta 'Base de datos'")
        btn_abrir_carpeta.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_abrir_carpeta.setStyleSheet("""
            QPushButton {
                background: none; border: none; color: #0284c7;
                font-size: 12px; font-weight: 500; text-decoration: underline;
            }
            QPushButton:hover { color: #0369a1; }
        """)
        btn_abrir_carpeta.clicked.connect(self._abrir_carpeta_bd)
        fila_pie.addWidget(btn_abrir_carpeta)

        fila_pie.addStretch(1)

        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancelar.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9; color: #475569;
                padding: 6px 16px; border: 1px solid #cbd5e1; border-radius: 6px;
                font-size: 13px; font-weight: 500;
            }
            QPushButton:hover { background-color: #e2e8f0; }
        """)
        btn_cancelar.clicked.connect(self.reject)
        fila_pie.addWidget(btn_cancelar)

        layout.addLayout(fila_pie)

    def _crear_tarjeta_accion(
        self,
        icono: str,
        titulo: str,
        badge: str,
        badge_color: str,
        descripcion: str,
        es_primario: bool,
        on_click: Any,
    ) -> QFrame:
        tarjeta = QFrame()
        tarjeta.setCursor(Qt.CursorShape.PointingHandCursor)
        borde_color = "#38bdf8" if es_primario else "#e2e8f0"
        bg_color = "#f0f9ff" if es_primario else "#ffffff"

        tarjeta.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border: 1px solid {borde_color};
                border-radius: 8px;
                padding: 10px 14px;
            }}
            QFrame:hover {{
                border-color: #0284c7;
                background-color: #e0f2fe;
            }}
        """)

        lay = QVBoxLayout(tarjeta)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(4)

        # Fila superior: Ícono, Título, Badge
        fila_top = QHBoxLayout()
        fila_top.setSpacing(8)

        lbl_icon = QLabel(icono)
        lbl_icon.setStyleSheet("font-size: 16px;")
        fila_top.addWidget(lbl_icon)

        lbl_tit = QLabel(titulo)
        lbl_tit.setStyleSheet("font-size: 13px; font-weight: bold; color: #0f172a;")
        fila_top.addWidget(lbl_tit)

        fila_top.addStretch(1)

        lbl_badge = QLabel(f" {badge} ")
        lbl_badge.setStyleSheet(f"""
            background-color: {badge_color}18;
            color: {badge_color};
            border: 1px solid {badge_color}40;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            padding: 2px 6px;
        """)
        fila_top.addWidget(lbl_badge)

        lay.addLayout(fila_top)

        # Descripción
        lbl_desc = QLabel(descripcion)
        lbl_desc.setStyleSheet("font-size: 11px; color: #64748b; line-height: 1.3;")
        lbl_desc.setWordWrap(True)
        lay.addWidget(lbl_desc)

        # Hacer que toda la tarjeta sea clickeable
        tarjeta.mousePressEvent = lambda event: on_click()

        return tarjeta

    def _elegir_local(self) -> None:
        self.resultado_accion = self.ACCION_LOCAL
        self.accept()

    def _elegir_subir(self) -> None:
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        import firebase_client as fb
        import respaldo_excel

        archivos = self.archivos_excel
        # 1. Comprobar si algún archivo tiene 'TIPO: ARCHIVO DE PRUEBA'
        es_entorno_prueba = rutas.es_entorno_prueba()
        tiene_archivo_prueba = False

        for a in archivos:
            try:
                # Lectura rápida de LEEME
                import openpyxl
                wb = openpyxl.load_workbook(str(a), read_only=True)
                if "LEEME" in wb.sheetnames:
                    ws = wb["LEEME"]
                    for row in ws.iter_rows(max_row=20, max_col=2, values_only=True):
                        if row and row[0] and "ARCHIVO DE PRUEBA" in str(row[0]).upper():
                            tiene_archivo_prueba = True
                            break
                wb.close()
            except Exception:
                pass
            if tiene_archivo_prueba:
                break

        if tiene_archivo_prueba and not es_entorno_prueba:
            QMessageBox.critical(
                self,
                "Acceso Denegado por Seguridad",
                "Se detectó un archivo marcado como 'TIPO: ARCHIVO DE PRUEBA'.\n\n"
                "Por seguridad, los archivos de prueba NO se pueden subir al proyecto de producción real.\n"
                "Para utilizarlos, inicie la aplicación en Entorno de Prueba (iniciar_prueba.bat).",
            )
            return

        # 2. Si está en entorno de prueba y el proyecto destino es el real
        proyecto_id = fb.obtener_proyecto_id()
        proyecto_real = getattr(fb, "PROYECTO_REAL_ID", "caapd-ispacas-optimizado")

        if es_entorno_prueba and proyecto_id == proyecto_real:
            # Estimar documentos que se escribirán
            # Aproximadamente: usuarios (hasta 750) + meses (cada uno hasta 750) + 1 config
            docs_estimados = max(30, len(archivos) * 30 + 30)
            texto, ok = QInputDialog.getText(
                self,
                "⚠️ CONFIRMACIÓN DE SEGURIDAD REQUERIDA",
                f"Estás en ENTORNO DE PRUEBA pero conectado al proyecto de PRODUCCIÓN REAL:\n"
                f"  Proyecto ID: {proyecto_id}\n\n"
                f"Se escribirán aproximadamente {docs_estimados} documentos en Firestore.\n\n"
                f"Para confirmar y proceder con la escritura, escribe exactamente la palabra CONFIRMAR:",
            )
            if not ok or texto.strip() != "CONFIRMAR":
                QMessageBox.information(
                    self,
                    "Operación Cancelada",
                    "No se escribió la palabra CONFIRMAR. La sincronización hacia Firebase ha sido abortada.",
                )
                return

        self.resultado_accion = self.ACCION_SUBIR_FIREBASE
        self.accept()

    def _elegir_descargar(self) -> None:
        self.resultado_accion = self.ACCION_DESCARGAR_FIREBASE
        self.accept()

    def _abrir_carpeta_bd(self) -> None:
        import os
        dir_bd = rutas.ruta_base_de_datos()
        os.startfile(str(dir_bd))
