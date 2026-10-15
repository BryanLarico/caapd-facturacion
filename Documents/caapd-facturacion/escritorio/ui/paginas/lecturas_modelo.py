"""
ui/paginas/lecturas_modelo.py — Modelo de datos y Proxy para la tabla de lecturas del mes.

Estructura virtual con QAbstractTableModel + QSortFilterProxyModel:
- Cada fila representa un medidor asociado a un abonado en el mes actual.
- Filtrado por pestañas de sectores y filtros de estado.
- Búsqueda inteligente usando codigos.buscar.
- Ordenamiento numérico por conexión.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Set
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor, QFont

import codigos

COLUMNAS_LECTURAS = [
    "Conexión",
    "ID / DNI",
    "Persona",
    "Sector",
    "Medidor",
    "Lect. Anterior",
    "Lect. Actual",
    "Consumo (m³)",
    "Estado",
    "Observación",
    "Nota",
    "Registrado por",
]


class ModeloLecturas(QAbstractTableModel):
    """Modelo virtual de tabla para las lecturas de los medidores en el mes."""

    def __init__(self, items: Optional[List[Dict[str, Any]]] = None, parent=None) -> None:
        super().__init__(parent)
        self._datos: List[Dict[str, Any]] = items or []

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._datos)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(COLUMNAS_LECTURAS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or index.row() >= len(self._datos):
            return None

        row = self._datos[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return str(row.get("nro_conexion") or "—")
            elif col == 1:
                uid = str(row.get("id_usuario") or "—")
                if row.get("es_pendiente"):
                    return f"{uid}  ⚠️"
                return uid
            elif col == 2:
                return str(row.get("nombre") or "").upper()
            elif col == 3:
                return str(row.get("sector") or "")
            elif col == 4:
                return f"💧 {row.get('nro_medidor') or '—'}"
            elif col == 5:
                ant = row.get("lectura_anterior")
                return str(ant) if ant is not None else "0"
            elif col == 6:
                act = row.get("lectura_actual")
                return str(act) if act is not None else "—"
            elif col == 7:
                act = row.get("lectura_actual")
                if act is not None:
                    ant = row.get("lectura_anterior") or 0
                    nov = row.get("novedad")
                    if act < ant and nov == "CAMBIO_MEDIDOR":
                        return f"{act} m³ (Nuevo)"
                    return f"{act - ant} m³"
                return "—"
            elif col == 8:
                est = str(row.get("estado_lectura") or "PENDIENTE").upper()
                if est == "LEIDO":
                    return "Leído"
                elif est == "SIN_ACCESO":
                    return "Sin acceso"
                return "Pendiente"
            elif col == 9:
                nov = str(row.get("novedad") or "").strip()
                if not nov or nov == "NORMAL":
                    return "Normal"
                return nov.replace("_", " ").title()
            elif col == 10:
                return str(row.get("nota") or "")
            elif col == 11:
                return str(row.get("registrado_por") or "—")

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (0, 1, 4, 5, 6, 7, 8):
                return int(Qt.AlignmentFlag.AlignCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        elif role == Qt.ItemDataRole.ForegroundRole:
            if col == 0:
                return QColor("#0369a1")  # Azul primario conexión
            elif col == 1:
                return QColor("#b45309") if row.get("es_pendiente") else QColor("#0f172a")
            elif col == 2:
                return QColor("#0f172a")  # Titular oscuro
            elif col in (3, 10, 11):
                return QColor("#334155")  # Sector / Nota / Registrado por
            elif col == 4:
                return QColor("#0284c7")  # Medidor
            elif col == 5:
                return QColor("#475569")  # Lectura anterior
            elif col == 6:
                if row.get("lectura_actual") is None:
                    return QColor("#94a3b8")  # Gris pendiente
                return QColor("#0f172a")
            elif col == 7:
                act = row.get("lectura_actual")
                if act is not None:
                    ant = row.get("lectura_anterior") or 0
                    if act < ant and row.get("novedad") != "CAMBIO_MEDIDOR":
                        return QColor("#dc2626")  # Rojo negativo
                    return QColor("#16a34a")  # Verde
                return QColor("#94a3b8")
            elif col == 8:
                est = str(row.get("estado_lectura") or "PENDIENTE").upper()
                if est == "LEIDO":
                    return QColor("#16a34a")
                elif est == "SIN_ACCESO":
                    return QColor("#dc2626")
                return QColor("#d97706")  # Ámbar pendiente
            elif col == 9:
                nov = str(row.get("novedad") or "").strip()
                if nov and nov != "NORMAL":
                    return QColor("#b45309")
                return QColor("#64748b")
            return QColor("#1e293b")

        elif role == Qt.ItemDataRole.FontRole:
            if col in (0, 1, 4, 5, 6, 7):
                f = QFont("Consolas", 10)
                if col in (0, 6, 7):
                    f.setBold(True)
                return f
            elif col == 2:
                f = QFont()
                f.setBold(True)
                return f

        elif role == Qt.ItemDataRole.UserRole:
            return row

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if section < len(COLUMNAS_LECTURAS):
                return COLUMNAS_LECTURAS[section]
        return None

    def actualizar_datos(self, items: List[Dict[str, Any]]) -> None:
        """Actualiza la lista interna de filas de medidores."""
        self.beginResetModel()
        self._datos = items
        self.endResetModel()

    def obtener_item(self, row: int) -> Optional[Dict[str, Any]]:
        if 0 <= row < len(self._datos):
            return self._datos[row]
        return None


class ProxyLecturas(QSortFilterProxyModel):
    """Proxy model con soporte para filtros por sector, filtros de estado y búsqueda inteligente."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.filtro_sector: str = "todos"
        self.filtro_estado: str = "todos"  # todos, faltan, sin_acceso, con_observacion
        self.ids_permitidos: Optional[Set[str]] = None

    def set_filtro_sector(self, sector: str) -> None:
        self.filtro_sector = sector.strip()
        self.invalidate()

    def set_filtro_estado(self, estado: str) -> None:
        self.filtro_estado = estado.lower().strip()
        self.invalidate()

    def set_ids_permitidos(self, ids: Optional[Set[str]]) -> None:
        self.ids_permitidos = ids
        self.invalidate()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        source_model: ModeloLecturas = self.sourceModel()  # type: ignore
        item = source_model.obtener_item(source_row)
        if not item:
            return False

        # 1. Filtro por búsqueda inteligente
        if self.ids_permitidos is not None:
            uid = str(item.get("id_usuario") or "")
            if uid not in self.ids_permitidos:
                return False

        # 2. Filtro por Sector
        if self.filtro_sector and self.filtro_sector.lower() != "todos":
            if str(item.get("sector") or "").upper() != self.filtro_sector.upper():
                return False

        # 3. Filtro por Estado
        est = str(item.get("estado_lectura") or "PENDIENTE").upper()
        if self.filtro_estado == "faltan":
            if est != "PENDIENTE":
                return False
        elif self.filtro_estado == "sin_acceso":
            if est != "SIN_ACCESO":
                return False
        elif self.filtro_estado == "con_observacion":
            nov = str(item.get("novedad") or "").strip()
            nota = str(item.get("nota") or "").strip()
            if not ((nov and nov != "NORMAL") or nota):
                return False

        return True

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        # Orden numérico por conexión en columna 0
        if left.column() == 0 and right.column() == 0:
            source_model: ModeloLecturas = self.sourceModel()  # type: ignore
            l_item = source_model.obtener_item(left.row())
            r_item = source_model.obtener_item(right.row())
            if l_item and r_item:
                c_l = str(l_item.get("nro_conexion") or "")
                c_r = str(r_item.get("nro_conexion") or "")
                v_l = int(c_l) if c_l.isdigit() else 999999
                v_r = int(c_r) if c_r.isdigit() else 999999
                return v_l < v_r
        return super().lessThan(left, right)
