"""
ui/componentes/dialogo_actualizar.py — Diálogo interactivo del Centro de Sincronización con Lectores Móviles.

Permite al usuario elegir entre:
1. Enviar mes a los lectores (Excel -> Nube): Reemplaza todo en Firestore con el mes activo.
2. Traer lecturas de los lectores (Nube -> Excel): Descarga lecturas registradas por los celulares.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import rutas


class DialogoActualizarBaseDatos(QDialog):
    """Diálogo modal para seleccionar la sincronización espejo con los lectores móviles."""

    ACCION_LOCAL = "local"
    ACCION_SUBIR_FIREBASE = "subir_firebase"
    ACCION_DESCARGAR_FIREBASE = "descargar_firebase"
    ACCION_CANCELAR = "cancelar"

    def __init__(self, parent: Optional[QWidget] = None, servicio: Optional[Any] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sincronización con Lectores Móviles")
        self.setFixedSize(600, 480)
        self.setModal(True)
        self.resultado_accion = self.ACCION_CANCELAR
        self.servicio = servicio or getattr(parent, "servicio", None)

        dir_bd = rutas.ruta_base_de_datos()
        self.archivos_excel = [p for p in dir_bd.glob("*.xlsx") if not p.name.startswith("~$") and p.is_file()]

        self._construir_ui()

    def _construir_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # 1. Encabezado
        lbl_titulo = QLabel("🔄 Sincronización con Lectores Móviles")
        lbl_titulo.setStyleSheet("font-size: 17px; font-weight: bold; color: #0f172a;")
        layout.addWidget(lbl_titulo)

        lbl_subtitulo = QLabel(
            "Gestiona el intercambio de padrones y lecturas entre tus Excel locales y la app celular:"
        )
        lbl_subtitulo.setStyleSheet("font-size: 13px; color: #475569;")
        layout.addWidget(lbl_subtitulo)

        # 2. Panel informativo de archivos y timestamps
        cfg = getattr(self.servicio, "config", {}) if self.servicio else {}
        ts_envio = cfg.get("ultimo_envio_lectores") or "No registrado"
        ts_descarga = cfg.get("ultima_descarga_lectores") or "No registrada"

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
        lay_p.setContentsMargins(8, 8, 8, 8)
        lay_p.setSpacing(6)

        n_arch = len(self.archivos_excel)
        nombres_str = ", ".join(p.name for p in self.archivos_excel[:3])
        if len(self.archivos_excel) > 3:
            nombres_str += f" y {len(self.archivos_excel) - 3} más..."

        lbl_bd_info = QLabel(
            f"📁 <b>Carpeta 'Base de datos':</b> {n_arch} archivo(s) Excel detectado(s)<br>"
            f"<span style='color: #64748b; font-size: 11px;'>{nombres_str or 'Carpeta vacía.'}</span>"
        )
        lbl_bd_info.setStyleSheet("font-size: 12px; color: #1e293b;")
        lay_p.addWidget(lbl_bd_info)

        lbl_ts = QLabel(
            f"⏱️ <b>Último envío a lectores:</b> <span style='color: #0369a1;'>{ts_envio}</span> &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"📥 <b>Última descarga:</b> <span style='color: #0369a1;'>{ts_descarga}</span>"
        )
        lbl_ts.setStyleSheet("font-size: 11px; color: #334155;")
        lay_p.addWidget(lbl_ts)

        layout.addWidget(panel_info)

        # 3. Exactamente 2 Tarjetas de Acción (Sin Recargar Local)
        # Tarjeta 1: Enviar mes a los lectores (Excel -> Nube)
        btn_subir = self._crear_tarjeta_accion(
            icono="☁️ ⬆️",
            titulo="Enviar mes a los lectores (Excel ➔ Nube)",
            badge="Sobreescribe Nube",
            badge_bg="#fee2e2",
            badge_color="#991b1b",
            badge_border="#fca5a5",
            descripcion="Sube el mes activo a Firebase en lotes ultrarrápidos para que los lectores lo vean en sus celulares. Borra sobrantes y versiones anteriores en la nube.",
            es_primario=True,
            on_click=self._elegir_subir,
        )
        layout.addWidget(btn_subir)

        # Tarjeta 2: Traer lecturas de los lectores (Nube -> Excel)
        btn_descargar = self._crear_tarjeta_accion(
            icono="📥 ⬇️",
            titulo="Traer lecturas de los lectores (Nube ➔ Excel)",
            badge="Descarga Espejo",
            badge_bg="#eff6ff",
            badge_color="#1e40af",
            badge_border="#93c5fd",
            descripcion="Descarga las lecturas registradas por los lectores móviles en sus celulares y las guarda en el Excel local sin tocar cobros, dinero ni lecturas ADMIN.",
            es_primario=False,
            on_click=self._elegir_descargar,
        )
        layout.addWidget(btn_descargar)

        layout.addStretch(1)

        # 4. Pie con Enlace a Carpeta y Botón Cancelar
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
                padding: 6px 18px; border: 1px solid #cbd5e1; border-radius: 6px;
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
        badge_bg: str,
        badge_color: str,
        badge_border: str,
        descripcion: str,
        es_primario: bool,
        on_click: Any,
    ) -> QFrame:
        tarjeta = QFrame()
        tarjeta.setCursor(Qt.CursorShape.PointingHandCursor)
        borde_color = "#38bdf8" if es_primario else "#e2e8f0"
        bg_color = "#f8fafc" if es_primario else "#ffffff"

        tarjeta.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border: 1px solid {borde_color};
                border-radius: 8px;
                padding: 12px 16px;
            }}
            QFrame:hover {{
                border-color: #0284c7;
                background-color: #f0f9ff;
            }}
        """)

        lay = QVBoxLayout(tarjeta)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(6)

        # Fila superior: Ícono, Título, Badge
        fila_top = QHBoxLayout()
        fila_top.setSpacing(8)

        lbl_icon = QLabel(icono)
        lbl_icon.setStyleSheet("font-size: 15px;")
        fila_top.addWidget(lbl_icon)

        lbl_tit = QLabel(titulo)
        lbl_tit.setStyleSheet("font-size: 13px; font-weight: bold; color: #0f172a;")
        fila_top.addWidget(lbl_tit)

        fila_top.addStretch(1)

        lbl_badge = QLabel(f" {badge} ")
        lbl_badge.setStyleSheet(f"""
            background-color: {badge_bg};
            color: {badge_color};
            border: 1px solid {badge_border};
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            padding: 2px 8px;
        """)
        fila_top.addWidget(lbl_badge)

        lay.addLayout(fila_top)

        # Descripción
        lbl_desc = QLabel(descripcion)
        lbl_desc.setStyleSheet("font-size: 11px; color: #64748b; line-height: 1.4;")
        lbl_desc.setWordWrap(True)
        lay.addWidget(lbl_desc)

        # Clic en toda la tarjeta
        tarjeta.mousePressEvent = lambda event: on_click()

        return tarjeta

    def _elegir_subir(self) -> None:
        import firebase_client as fb

        archivos = self.archivos_excel
        # Rechazar respaldos antiguos marcados como datos de prueba.
        tiene_archivo_prueba = False

        for a in archivos:
            try:
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

        if tiene_archivo_prueba:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setWindowTitle("Acceso Denegado por Seguridad")
            msg.setText("<b>Se detectó un archivo marcado como 'TIPO: ARCHIVO DE PRUEBA':</b>")
            msg.setInformativeText(
                "Por seguridad, los archivos de prueba NO se pueden subir al proyecto de producción real.\n\n"
                "Retire esa marca solo después de verificar que el archivo contiene datos reales."
            )
            msg.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg.exec()
            return

        # 2. Confirmación obligatoria con CONFIRMAR (Regla 5a)
        aviso_seguridad = (
            "Esto BORRARÁ todo lo que hay en Firebase y lo reemplazará con los Excel actuales. "
            "Las lecturas no descargadas se perderán.\n\n"
            "Para confirmar y proceder con el envío, escribe exactamente la palabra CONFIRMAR:"
        )

        texto, ok = QInputDialog.getText(
            self,
            "⚠️ Confirmar Reemplazo en Firebase",
            aviso_seguridad,
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
        dir_bd = rutas.ruta_base_de_datos()
        try:
            os.startfile(str(dir_bd))
        except Exception:
            pass
