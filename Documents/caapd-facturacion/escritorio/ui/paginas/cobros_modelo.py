"""
ui/paginas/cobros_modelo.py — Modelo y Proxy para la tabla unificada de Cobros y Morosos.

Tabla optimizada de 7 columnas:
0. Conexión
1. N° Recibo
2. Titular
3. Sector
4. m³ (consumo del mes)
5. Total (S/.)
6. Estado

Color de fila según morosidad:
- 2 meses adeudados  -> fila naranja
- 3 o más meses      -> fila roja
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from PySide6.QtCore import QAbstractTableModel, QEvent, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

import codigos
from ui.estilos.paleta import PALETA

COLUMNAS_COBROS = [
    "CONEXIÓN",
    "N° RECIBO",
    "TITULAR",
    "SECTOR",
    "m³",
    "TOTAL (S/.)",
    "ESTADO",
]

TOOLTIP_COLUMNAS = {
    4: "Consumo del mes en metros cúbicos (m³)",
}

# Colores de fila por morosidad: (fondo, texto)
COLOR_FILA_DOS_MESES = (QColor("#fdba74"), QColor("#7c2d12"))   # Naranja
COLOR_FILA_CORTE = (QColor("#fca5a5"), QColor(
    "#7f1d1d"))       # Rojo (3+ meses)

# Abreviaturas legibles de sectores si se desea, manteniendo el nombre completo en ToolTip
SECTOR_ABREV = {
    "BARRIO DE CHAUPI": "Chaupi",
    "BARRIO DE PACHAYZA": "Pachayza",
    "BARRIO DE LUCMANI": "Lucmani",
    "HUAQUILLO": "Huaquillo",
    "CHAUPICERCA": "Chaupicerca",
    "AYACUCHO": "Ayacucho",
}


def color_fila_morosidad(doc: Dict[str, Any]):
    """
    Devuelve (fondo, texto) para la fila según los meses adeudados, o None si no aplica.
    Solo se colorea si tiene recibo emitido y aún tiene saldo pendiente.
    """
    tot_pagar = float(doc.get("total_a_pagar") or 0.0)
    m_pagado = float(doc.get("monto_pagado") or 0.0)
    saldo = max(0.0, round(tot_pagar - m_pagado, 2))
    meses = int(doc.get("meses_adeudados") or 1)
    tiene_recibo = bool(doc.get("nro_recibo"))
    if not tiene_recibo or saldo <= 0.0:
        return None
    if meses >= 3:
        return COLOR_FILA_CORTE
    if meses == 2:
        return COLOR_FILA_DOS_MESES
    return None


class DelegadoFilasCobros(QStyledItemDelegate):
    """
    Pinta el fondo de la fila completa con el color de morosidad.

    Mantiene también el resaltado del hover en toda la fila para que una celda
    individual no tape los colores de morosidad.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._fila_sobrevolada = -1
        self._vista = parent
        if self._vista is not None:
            self._vista.setMouseTracking(True)
            self._vista.viewport().setMouseTracking(True)
            self._vista.entered.connect(self._al_ingresar_indice)
            self._vista.destroyed.connect(self._al_destruir_vista)
            self._vista.viewport().installEventFilter(self)

    def _al_destruir_vista(self, *_args) -> None:
        self._vista = None

    def _al_ingresar_indice(self, index: QModelIndex) -> None:
        self._actualizar_fila_sobrevolada(index.row() if index.isValid() else -1)

    def eventFilter(self, watched, event) -> bool:
        if self._vista is not None and watched == self._vista.viewport():
            if event.type() == QEvent.Type.MouseMove:
                indice = self._vista.indexAt(event.position().toPoint())
                fila = indice.row() if indice.isValid() else -1
                self._actualizar_fila_sobrevolada(fila)
            elif event.type() == QEvent.Type.Leave:
                self._actualizar_fila_sobrevolada(-1)
        return super().eventFilter(watched, event)

    def _actualizar_fila_sobrevolada(self, fila: int) -> None:
        if fila != self._fila_sobrevolada:
            self._fila_sobrevolada = fila
            if self._vista is not None:
                self._vista.viewport().update()

    def color_fondo_fila(self, index: QModelIndex) -> QColor:
        brush = index.data(Qt.ItemDataRole.BackgroundRole)
        if self._fila_sobrevolada != index.row():
            return brush.color() if brush is not None else QColor()
        if brush is not None:
            return brush.color().lighter(108)
        return QColor(PALETA.PRIMARIO_CLARO)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        color_fondo = self.color_fondo_fila(index)
        brush = QBrush(color_fondo) if color_fondo.isValid() else None
        if brush is not None and not (option.state & QStyle.StateFlag.State_Selected):
            painter.save()
            painter.fillRect(option.rect, brush)
            painter.restore()
        option = QStyleOptionViewItem(option)
        option.state &= ~QStyle.StateFlag.State_MouseOver
        if brush is not None:
            option.features &= ~QStyleOptionViewItem.ViewItemFeature.Alternate
            option.backgroundBrush = brush
        super().paint(painter, option, index)


class ModeloCobros(QAbstractTableModel):
    """Modelo de datos tabular para la pantalla unificada de cobros y facturación."""

    def __init__(self, datos: Optional[List[Dict[str, Any]]] = None, parent=None):
        super().__init__(parent)
        self._datos: List[Dict[str, Any]] = datos or []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._datos)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(COLUMNAS_COBROS)

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if orientation == Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole:
                return COLUMNAS_COBROS[section]
            if role == Qt.ItemDataRole.ToolTipRole:
                return TOOLTIP_COLUMNAS.get(section)
            if role == Qt.ItemDataRole.TextAlignmentRole:
                if section in (0, 1, 6):
                    return int(Qt.AlignmentFlag.AlignCenter)
                elif section in (4, 5):
                    return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or index.row() >= len(self._datos):
            return None

        doc = self._datos[index.row()]
        col = index.column()

        tot_pagar = float(doc.get("total_a_pagar") or 0.0)
        m_pagado = float(doc.get("monto_pagado") or 0.0)
        saldo = max(0.0, round(tot_pagar - m_pagado, 2))
        m_adeudados = int(doc.get("meses_adeudados") or 1)
        consumo_m3 = doc.get("consumo_total_m3")

        # Alertas de medidor
        meds = doc.get("medidores") or []
        novedades_alertables = [
            str(m.get("novedad") or "").strip().upper()
            for m in meds
            if str(m.get("novedad") or "").strip().upper() not in ("", "NORMAL")
        ]
        tiene_alertas = len(novedades_alertables) > 0

        # Estado textual
        if not doc.get("nro_recibo") or tot_pagar == 0.0 and consumo_m3 is None:
            estado_txt = "Sin Facturar"
        elif saldo <= 0.0 and tot_pagar > 0.0:
            estado_txt = "Pagado"
        elif m_pagado > 0.0 and saldo > 0.0:
            estado_txt = f"Parcial (S/. {saldo:.2f})"
        elif m_adeudados >= 3:
            estado_txt = f"Corte ({m_adeudados} m.)"
        elif m_adeudados == 2:
            estado_txt = "2 Meses"
        else:
            estado_txt = "Pendiente"

        color_fila = color_fila_morosidad(doc)

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                con = doc.get("nro_conexion")
                return str(con).zfill(6) if con else "—"
            elif col == 1:
                n_rec = doc.get("nro_recibo")
                return str(n_rec).zfill(9) if n_rec else "—"
            elif col == 2:
                return doc.get("nombre") or "—"
            elif col == 3:
                sec = doc.get("sector") or "—"
                return SECTOR_ABREV.get(sec, sec)
            elif col == 4:
                return f"{int(consumo_m3)}" if consumo_m3 is not None else "—"
            elif col == 5:
                return f"S/. {tot_pagar:.2f}"
            elif col == 6:
                return estado_txt

        elif role == Qt.ItemDataRole.ToolTipRole:
            if col == 3:
                return doc.get("sector") or ""
            elif col == 4:
                return f"{int(consumo_m3)} m³ consumidos este mes" if consumo_m3 is not None else ""
            elif col == 6 and tiene_alertas:
                return f"Alerta de medidor: {', '.join(novedades_alertables)}"

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (0, 1, 6):
                return int(Qt.AlignmentFlag.AlignCenter)
            elif col in (4, 5):
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        elif role == Qt.ItemDataRole.FontRole:
            if col in (0, 5) or (color_fila is not None and col == 6):
                f = QFont()
                f.setBold(True)
                return f

        elif role == Qt.ItemDataRole.BackgroundRole:
            # Fila completa coloreada según morosidad (naranja 2 meses, rojo 3+ meses)
            if color_fila is not None:
                return QBrush(color_fila[0])

        elif role == Qt.ItemDataRole.ForegroundRole:
            # En filas coloreadas usamos un texto oscuro uniforme para buena legibilidad
            if color_fila is not None:
                return QBrush(color_fila[1])

            if col == 0:
                return QBrush(QColor("#0369a1"))
            elif col == 1:
                return QBrush(QColor("#475569"))
            elif col == 5:
                if saldo <= 0.0 and tot_pagar > 0.0:
                    return QBrush(QColor("#16a34a"))  # Verde si está pagado
                return QBrush(QColor("#0f172a"))
            elif col == 6:  # Estado
                if not doc.get("nro_recibo") or (tot_pagar == 0.0 and consumo_m3 is None):
                    return QBrush(QColor("#64748b"))  # Gris sin facturar
                if saldo <= 0.0 and tot_pagar > 0.0:
                    return QBrush(QColor("#16a34a"))  # Verde pagado
                elif m_adeudados >= 3:
                    return QBrush(QColor("#dc2626"))  # Rojo corte 3+ meses
                elif m_adeudados == 2:
                    return QBrush(QColor("#ea580c"))  # Naranja fuerte 2 meses
                # Ámbar / naranja pendiente 1 mes
                return QBrush(QColor("#d97706"))

        return None

    def actualizar_datos(self, nuevos_datos: List[Dict[str, Any]]) -> None:
        """Reemplaza la lista completa de recibos y notifica a las vistas."""
        self.beginResetModel()
        self._datos = list(nuevos_datos)
        self.endResetModel()

    def obtener_item(self, row: int) -> Optional[Dict[str, Any]]:
        """Devuelve el diccionario original del documento en la fila dada."""
        if 0 <= row < len(self._datos):
            return self._datos[row]
        return None


class ProxyCobros(QSortFilterProxyModel):
    """Proxy para búsqueda inteligente y filtrado por sector y estado de mora."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._filtro_sector: str = "todos"
        # todos, sin_facturar, pendientes, dos_meses, corte, pagados, con_alertas
        self._filtro_estado: str = "todos"
        self._texto_filtro: str = ""

    def set_filtro_sector(self, sector: str) -> None:
        self._filtro_sector = (sector or "todos").strip()
        self.invalidate()

    def set_filtro_estado(self, estado: str) -> None:
        self._filtro_estado = (estado or "todos").strip().lower()
        self.invalidate()

    def set_texto_filtro(self, texto: str) -> None:
        self._texto_filtro = (texto or "").strip()
        self.invalidate()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        modelo: ModeloCobros = self.sourceModel()  # type: ignore
        doc = modelo.obtener_item(source_row)
        if not doc:
            return False

        # 1. Filtro por Sector
        if self._filtro_sector != "todos":
            if (doc.get("sector") or "") != self._filtro_sector:
                return False

        tot_pagar = float(doc.get("total_a_pagar") or 0.0)
        m_pagado = float(doc.get("monto_pagado") or 0.0)
        saldo = max(0.0, round(tot_pagar - m_pagado, 2))
        meses = int(doc.get("meses_adeudados") or 1)
        tiene_recibo = bool(doc.get("nro_recibo"))
        esta_pagado = (saldo <= 0.0 and tot_pagar > 0.0)

        # 2. Filtro por Estado / Mora
        if self._filtro_estado == "sin_facturar":
            if tiene_recibo and tot_pagar > 0.0:
                return False
        elif self._filtro_estado == "pendientes":
            if esta_pagado or not tiene_recibo:
                return False
        elif self._filtro_estado == "dos_meses":
            if esta_pagado or meses != 2 or not tiene_recibo:
                return False
        elif self._filtro_estado == "corte":
            if esta_pagado or meses < 3 or not tiene_recibo:
                return False
        elif self._filtro_estado == "pagados":
            if not esta_pagado:
                return False
        elif self._filtro_estado == "con_alertas":
            meds = doc.get("medidores") or []
            tiene_alerta = any(
                str(m.get("novedad") or "").strip(
                ).upper() not in ("", "NORMAL")
                or bool(str(m.get("nota") or "").strip())
                for m in meds
            )
            if not tiene_alerta:
                return False

        # 3. Filtro por Texto Inteligente
        if self._texto_filtro:
            q_limpia = self._texto_filtro.strip()
            recibo = str(doc.get("nro_recibo") or "")

            if q_limpia.isdigit() and (q_limpia in recibo or q_limpia.zfill(9) == recibo):
                return True

            raw_meds = doc.get("medidores") or []
            medidores = [
                m.get("nro_medidor", "") if isinstance(m, dict) else str(m)
                for m in raw_meds
            ]
            conexion = str(doc.get("nro_conexion") or "")
            dni = str(doc.get("id_usuario") or doc.get("_id") or "")
            nombre = str(doc.get("nombre") or "")

            if q_limpia.isdigit():
                len_q = len(q_limpia)
                target_med = q_limpia.zfill(6) if len_q < 6 else q_limpia
                target_con = q_limpia.zfill(6) if len_q < 6 else q_limpia
                target_dni = q_limpia.zfill(8) if len_q < 8 else q_limpia

                if (
                    any(m == target_med for m in medidores)
                    or conexion == target_con
                    or dni == target_dni
                ):
                    return True

                if (
                    any(q_limpia in m for m in medidores)
                    or q_limpia in conexion
                    or q_limpia in dni
                ):
                    return True
                return False
            else:
                palabras = [codigos.quitar_tildes(
                    p).lower() for p in q_limpia.split() if p]
                nom_norm = codigos.quitar_tildes(nombre).lower()
                dni_norm = dni.lower()

                if q_limpia.lower() in dni_norm:
                    return True
                if all(p in nom_norm for p in palabras):
                    return True
                return False

        return True

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        modelo: ModeloCobros = self.sourceModel()  # type: ignore
        d_left = modelo.obtener_item(left.row())
        d_right = modelo.obtener_item(right.row())
        if not d_left or not d_right:
            return False

        col = left.column()
        if col == 0:  # Conexión
            c_l = str(d_left.get("nro_conexion") or "")
            c_r = str(d_right.get("nro_conexion") or "")
            val_l = int(c_l) if c_l.isdigit() else 999999
            val_r = int(c_r) if c_r.isdigit() else 999999
            return val_l < val_r
        elif col == 1:  # N° Recibo
            r_l = str(d_left.get("nro_recibo") or "")
            r_r = str(d_right.get("nro_recibo") or "")
            val_l = int(r_l) if r_l.isdigit() else 999999999
            val_r = int(r_r) if r_r.isdigit() else 999999999
            return val_l < val_r
        elif col == 2:  # Titular
            return str(d_left.get("nombre") or "").upper() < str(d_right.get("nombre") or "").upper()
        elif col == 3:  # Sector
            return str(d_left.get("sector") or "").upper() < str(d_right.get("sector") or "").upper()
        elif col == 4:  # m³
            c_l = float(d_left.get("consumo_total_m3") or 0.0)
            c_r = float(d_right.get("consumo_total_m3") or 0.0)
            return c_l < c_r
        elif col == 5:  # Total S/.
            return float(d_left.get("total_a_pagar") or 0.0) < float(d_right.get("total_a_pagar") or 0.0)
        elif col == 6:  # Estado
            return int(d_left.get("meses_adeudados") or 1) < int(d_right.get("meses_adeudados") or 1)

        return super().lessThan(left, right)
