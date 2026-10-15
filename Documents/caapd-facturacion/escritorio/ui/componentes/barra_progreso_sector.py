"""
ui/componentes/barra_progreso_sector.py — Fila de avance de lecturas por sector.

Muestra nombre de sector, cantidad leída/total, check verde al 100% y barra de progreso.
"""
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)


class BarraProgresoSector(QFrame):
    """
    Componente para visualizar el porcentaje de lecturas completadas en un sector.
    """

    def __init__(
        self,
        sector: str = "",
        total: int = 0,
        leidos: int = 0,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("class", "sector_fila")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(10)

        # Nombre del sector
        self.lbl_sector = QLabel(sector)
        self.lbl_sector.setObjectName("sector_nombre")
        self.lbl_sector.setStyleSheet("font-size: 13px; font-weight: 500;")
        layout.addWidget(self.lbl_sector, stretch=1)

        # Contenedor derecho: Texto y barra
        der_layout = QVBoxLayout()
        der_layout.setContentsMargins(0, 0, 0, 0)
        der_layout.setSpacing(2)

        # Texto con avance y check
        check_str = " ✅" if (leidos == total and total > 0) else ""
        self.lbl_avance = QLabel(f"{leidos} de {total}{check_str}")
        self.lbl_avance.setObjectName("sector_progreso_txt")
        self.lbl_avance.setStyleSheet("font-size: 11px;")
        self.lbl_avance.setAlignment(Qt.AlignmentFlag.AlignRight)
        der_layout.addWidget(self.lbl_avance)

        # Barra de progreso
        pct = int(leidos / total * 100) if total > 0 else 0
        self.barra = QProgressBar()
        self.barra.setRange(0, 100)
        self.barra.setValue(pct)
        self.barra.setTextVisible(False)
        self.barra.setFixedHeight(8)
        self.barra.setFixedWidth(140)

        if pct == 100 and total > 0:
            self.barra.setProperty("completo", "true")
        else:
            self.barra.setProperty("completo", "false")

        der_layout.addWidget(self.barra)
        layout.addLayout(der_layout)

    def actualizar(self, total: int, leidos: int) -> None:
        """Actualiza las cifras y el progreso visual."""
        check_str = " ✅" if (leidos == total and total > 0) else ""
        self.lbl_avance.setText(f"{leidos} de {total}{check_str}")
        pct = int(leidos / total * 100) if total > 0 else 0
        self.barra.setValue(pct)
        if pct == 100 and total > 0:
            self.barra.setProperty("completo", "true")
        else:
            self.barra.setProperty("completo", "false")
        self.barra.style().unpolish(self.barra)
        self.barra.style().polish(self.barra)
