"""
ui/paginas/usuarios_modelo.py — Modelo y Proxy para la tabla virtual de usuarios.

Optimizado para mostrar 800+ usuarios con renderizado virtual instantáneo (< 300 ms)
y filtrado en tiempo real (< 50 ms).
"""
from typing import Any, Dict, List, Optional
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor, QFont

import codigos


COLUMNAS = [
    "Conexión",
    "DNI / ID",
    "Apellidos y Nombres",
    "Sector",
    "Dirección",
    "Medidores",
    "Cat.",
    "Estado",
]


class ModeloUsuarios(QAbstractTableModel):
    """Modelo de datos tabular para el padrón de usuarios."""

    def __init__(self, usuarios: Optional[List[Dict[str, Any]]] = None, parent=None) -> None:
        super().__init__(parent)
        self._datos: List[Dict[str, Any]] = usuarios or []

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._datos)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(COLUMNAS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or index.row() >= len(self._datos):
            return None

        u = self._datos[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return str(u.get("nro_conexion") or "—")
            elif col == 1:
                uid = str(u.get("id_usuario") or u.get("_id") or "—")
                if u.get("es_pendiente"):
                    return f"{uid}  ⚠️"
                return uid
            elif col == 2:
                return str(u.get("nombre") or "").upper()
            elif col == 3:
                return str(u.get("sector") or "")
            elif col == 4:
                return str(u.get("direccion") or "S/N")
            elif col == 5:
                meds = u.get("medidores") or []
                meds_str = [m if isinstance(m, str) else m.get("nro_medidor", "") for m in meds]
                if meds_str:
                    return ", ".join(f"💧 {m}" for m in meds_str if m)
                return "(Sin medidor)"
            elif col == 6:
                return str(u.get("codigo_categoria") or "A")
            elif col == 7:
                return "Activo" if u.get("activo", True) else "Inactivo"

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (0, 1, 6, 7):
                return int(Qt.AlignmentFlag.AlignCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        elif role == Qt.ItemDataRole.ForegroundRole:
            if col == 0:
                return QColor("#0369a1")  # Azul primario conexión
            elif col == 1:
                return QColor("#b45309") if u.get("es_pendiente") else QColor("#0f172a")
            elif col == 2:
                return QColor("#0f172a")  # Nombre oscuro
            elif col in (3, 4, 6):
                return QColor("#334155")  # Texto informativo
            elif col == 5:
                return QColor("#0284c7")  # Medidores azul
            elif col == 7:
                return QColor("#16a34a") if u.get("activo", True) else QColor("#64748b")
            return QColor("#1e293b")

        elif role == Qt.ItemDataRole.FontRole:
            if col in (0, 1):
                f = QFont("Consolas", 10)
                f.setBold(True)
                return f
            elif col == 2:
                f = QFont()
                f.setBold(True)
                return f

        elif role == Qt.ItemDataRole.UserRole:
            return u

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if section < len(COLUMNAS):
                return COLUMNAS[section]
        return None

    def actualizar_datos(self, usuarios: List[Dict[str, Any]]) -> None:
        """Reemplaza los datos del modelo y notifica a la vista."""
        self.beginResetModel()
        self._datos = usuarios
        self.endResetModel()

    def obtener_usuario(self, row: int) -> Optional[Dict[str, Any]]:
        if 0 <= row < len(self._datos):
            return self._datos[row]
        return None


class ProxyUsuarios(QSortFilterProxyModel):
    """Proxy model con ordenamiento numérico por conexión y filtrado por pestañas."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.filtro_estado: str = "todos"  # todos, activos, inactivos, pendientes
        self.lista_ids_filtrados: Optional[set] = None

    def set_filtro_estado(self, filtro: str) -> None:
        self.filtro_estado = filtro.lower()
        self.invalidate()

    def set_ids_busqueda(self, ids_permitidos: Optional[set]) -> None:
        """Establece los IDs filtrados por la búsqueda inteligente de codigos.py."""
        self.lista_ids_filtrados = ids_permitidos
        self.invalidate()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        source_model: ModeloUsuarios = self.sourceModel()  # type: ignore
        u = source_model.obtener_usuario(source_row)
        if not u:
            return False

        # 1. Filtro por búsqueda inteligente
        if self.lista_ids_filtrados is not None:
            uid = str(u.get("id_usuario") or u.get("_id") or "")
            if uid not in self.lista_ids_filtrados:
                return False

        # 2. Filtro por estado
        if self.filtro_estado == "activos":
            return bool(u.get("activo", True))
        elif self.filtro_estado == "inactivos":
            return not bool(u.get("activo", True))
        elif self.filtro_estado == "pendientes":
            return bool(u.get("es_pendiente", False))

        return True

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        source_model: ModeloUsuarios = self.sourceModel()  # type: ignore
        u_left = source_model.obtener_usuario(left.row())
        u_right = source_model.obtener_usuario(right.row())
        if not u_left or not u_right:
            return False

        col = left.column()
        if col == 0:  # Conexión
            c_l = str(u_left.get("nro_conexion") or "")
            c_r = str(u_right.get("nro_conexion") or "")
            val_l = int(c_l) if c_l.isdigit() else 999999
            val_r = int(c_r) if c_r.isdigit() else 999999
            return val_l < val_r
        elif col == 1:  # DNI / ID
            return str(u_left.get("id_usuario") or "") < str(u_right.get("id_usuario") or "")
        elif col == 2:  # Nombre
            return str(u_left.get("nombre") or "") < str(u_right.get("nombre") or "")
        elif col == 3:  # Sector
            return str(u_left.get("sector") or "") < str(u_right.get("sector") or "")
        elif col == 4:  # Dirección
            return str(u_left.get("direccion") or "") < str(u_right.get("direccion") or "")
        elif col == 5:  # Medidores
            meds_l = u_left.get("medidores") or []
            meds_r = u_right.get("medidores") or []
            m_l = str(meds_l[0] if meds_l else "")
            m_r = str(meds_r[0] if meds_r else "")
            return m_l < m_r
        elif col == 6:  # Categoría
            return str(u_left.get("codigo_categoria") or "") < str(u_right.get("codigo_categoria") or "")
        elif col == 7:  # Estado
            return bool(u_left.get("activo", True)) < bool(u_right.get("activo", True))

        return super().lessThan(left, right)
