"""
ui/paginas/lectores_modelo.py — Modelo y Proxy para la tabla de lectores móviles.
"""
from __future__ import annotations
import datetime
from typing import Any, Dict, List, Optional
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QBrush, QColor, QFont


COLUMNAS = [
    "CORREO ELECTRÓNICO",
    "NOMBRE COMPLETO",
    "ESTADO",
    "ÚLTIMO ACCESO",
    "ID (UID)",
]


class ModeloLectores(QAbstractTableModel):
    """Modelo de datos tabular para la lista de lectores de Firebase Auth."""

    def __init__(self, datos: Optional[List[Dict[str, Any]]] = None, parent=None):
        super().__init__(parent)
        self._datos: List[Dict[str, Any]] = datos or []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._datos)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(COLUMNAS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole:
                return COLUMNAS[section]
            if role == Qt.ItemDataRole.TextAlignmentRole:
                if section in (2, 3):
                    return int(Qt.AlignmentFlag.AlignCenter)
                return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or index.row() >= len(self._datos):
            return None

        lector = self._datos[index.row()]
        if isinstance(lector, str):
            lector = {
                "uid": lector,
                "email": lector,
                "display_name": lector.split("@")[0] if "@" in lector else lector,
                "disabled": False,
            }
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return lector.get("email", "")
            elif col == 1:
                return lector.get("display_name") or "—"
            elif col == 2:
                return "Deshabilitado" if lector.get("disabled") else "Activo"
            elif col == 3:
                last_ts = lector.get("last_sign_in") or lector.get("created_at")
                if last_ts:
                    try:
                        # Timestamp en milisegundos
                        dt = datetime.datetime.fromtimestamp(last_ts / 1000.0)
                        return dt.strftime("%d/%m/%Y %H:%M")
                    except Exception:
                        return str(last_ts)
                return "Nunca"
            elif col == 4:
                return lector.get("uid", "")

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (2, 3):
                return int(Qt.AlignmentFlag.AlignCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        elif role == Qt.ItemDataRole.ForegroundRole:
            if col == 0:
                return QBrush(QColor("#0369a1"))  # Azul corporativo
            elif col == 1:
                return QBrush(QColor("#0f172a"))  # Oscuro alto contraste
            elif col == 2:
                # Verde para activo, Rojo para deshabilitado
                return QBrush(QColor("#dc2626")) if lector.get("disabled") else QBrush(QColor("#16a34a"))
            elif col in (3, 4):
                return QBrush(QColor("#64748b"))  # Gris medio

        elif role == Qt.ItemDataRole.FontRole:
            fuente = QFont()
            if col in (0, 2):
                fuente.setBold(True)
            elif col == 4:
                fuente.setFamily("Consolas")
                fuente.setPointSize(9)
            return fuente

        elif role == Qt.ItemDataRole.UserRole:
            # Retorna el dict completo del lector
            return lector

        return None

    def actualizar_datos(self, nuevos_datos: List[Dict[str, Any]]) -> None:
        self.beginResetModel()
        self._datos = list(nuevos_datos)
        self.endResetModel()

    def actualizar_lector_en_fila(self, uid: str, cambios: Dict[str, Any]) -> int:
        """Actualiza campos de un lector en memoria y emite dataChanged para esa fila sin resetear el modelo."""
        for row, l in enumerate(self._datos):
            if l.get("uid") == uid:
                l.update(cambios)
                top_left = self.index(row, 0)
                bottom_right = self.index(row, self.columnCount() - 1)
                self.dataChanged.emit(top_left, bottom_right)
                return row
        return -1

    def eliminar_lector_por_uid(self, uid: str) -> bool:
        """Elimina un lector de la lista del modelo."""
        for row, l in enumerate(self._datos):
            if l.get("uid") == uid:
                self.beginRemoveRows(QModelIndex(), row, row)
                self._datos.pop(row)
                self.endRemoveRows()
                return True
        return False

    def obtener_lector(self, row: int) -> Optional[Dict[str, Any]]:
        if 0 <= row < len(self._datos):
            return self._datos[row]
        return None


class ProxyLectores(QSortFilterProxyModel):
    """Proxy para filtrar y ordenar lectores por texto y estado."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._texto_filtro: str = ""
        self._filtro_estado: str = "todos"  # "todos", "activos", "deshabilitados"

    def set_texto_filtro(self, texto: str) -> None:
        self._texto_filtro = texto.strip().lower()
        self.invalidate()

    def set_filtro_estado(self, estado: str) -> None:
        self._filtro_estado = estado.lower()
        self.invalidate()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model: ModeloLectores = self.sourceModel()
        lector = model.obtener_lector(source_row)
        if not lector:
            return False

        if isinstance(lector, str):
            lector = {
                "uid": lector,
                "email": lector,
                "display_name": lector.split("@")[0] if "@" in lector else lector,
                "disabled": False,
            }

        # Filtro por estado
        disabled = bool(lector.get("disabled", False))
        if self._filtro_estado == "activos" and disabled:
            return False
        if self._filtro_estado == "deshabilitados" and not disabled:
            return False

        # Filtro por texto (email o nombre)
        if self._texto_filtro:
            email = (lector.get("email") or "").lower()
            nombre = (lector.get("display_name") or "").lower()
            uid = (lector.get("uid") or "").lower()
            if (self._texto_filtro not in email and 
                self._texto_filtro not in nombre and 
                self._texto_filtro not in uid):
                return False

        return True
