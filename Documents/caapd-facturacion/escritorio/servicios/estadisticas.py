"""
servicios/estadisticas.py — Función pura para el cálculo de estadísticas de Inicio.

Calcula métricas de avance de lecturas por sector y estadísticas de recibos
a partir de datos en memoria sin depender de Firebase ni de Qt.
"""
from typing import Any, Dict, List, Tuple


def calcular_estadisticas_inicio(
    config: Dict[str, Any],
    usuarios: Dict[str, Dict[str, Any]],
    mes: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Calcula estadísticas de avance de lecturas y de recibos para el panel de Inicio.

    Retorna:
        (stats_sectores, stats_recibos)
        - stats_sectores: lista de dicts con claves:
            'sector', 'total', 'leidos', 'porcentaje', 'completo'
        - stats_recibos: dict con 'generados', 'pagados', 'pendientes'
    """
    cfg = config or {}
    users = usuarios or {}
    mes_docs = mes or {}

    stats_sectores: List[Dict[str, Any]] = []
    stats_recibos: Dict[str, int] = {
        "generados": 0,
        "pagados": 0,
        "pendientes": 0,
    }

    sectores = cfg.get("sectores", [])
    for sector in sectores:
        total = sum(
            1 for u in users.values()
            if u.get("sector") == sector and u.get("activo", True)
        )
        leidos = 0
        for uid, doc in mes_docs.items():
            u = users.get(uid, {})
            # Si el usuario no está en el padrón, intentamos leer sector del doc del mes
            user_sector = u.get("sector") or doc.get("sector")
            if user_sector != sector:
                continue

            medidores_doc = doc.get("medidores", [])
            if medidores_doc and all(
                m.get("lectura_actual") is not None for m in medidores_doc
            ):
                leidos += 1

        pct = int(leidos / total * 100) if total > 0 else 0
        stats_sectores.append({
            "sector": sector,
            "total": total,
            "leidos": leidos,
            "porcentaje": pct,
            "completo": (leidos == total and total > 0),
        })

    for uid, doc in mes_docs.items():
        if doc.get("nro_recibo"):
            stats_recibos["generados"] += 1
            monto_pagado = float(doc.get("monto_pagado") or 0)
            total_a_pagar = float(doc.get("total_a_pagar") or 0)
            if monto_pagado >= total_a_pagar > 0:
                stats_recibos["pagados"] += 1
            else:
                stats_recibos["pendientes"] += 1

    return stats_sectores, stats_recibos
