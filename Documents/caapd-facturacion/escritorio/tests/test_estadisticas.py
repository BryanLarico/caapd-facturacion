"""
tests/test_estadisticas.py — Pruebas unitarias de servicios/estadisticas.py.
"""
from servicios.estadisticas import calcular_estadisticas_inicio


def test_estadisticas_sin_datos():
    stats_sectores, stats_recibos = calcular_estadisticas_inicio({}, {}, {})
    assert stats_sectores == []
    assert stats_recibos == {"generados": 0, "pagados": 0, "pendientes": 0}


def test_estadisticas_sectores_y_recibos():
    config = {
        "sectores": ["CENTRO", "ALTO", "BAJO"],
    }
    usuarios = {
        "001": {"sector": "CENTRO", "activo": True},
        "002": {"sector": "CENTRO", "activo": True},
        "003": {"sector": "ALTO", "activo": True},
        "004": {"sector": "ALTO", "activo": False},  # Inactivo, no suma al total
    }
    mes = {
        "001": {
            "sector": "CENTRO",
            "medidores": [{"lectura_actual": 120}],
            "nro_recibo": "000000001",
            "total_a_pagar": 17.50,
            "monto_pagado": 17.50,  # Pagado completo
        },
        "002": {
            "sector": "CENTRO",
            "medidores": [{"lectura_actual": None}],  # No leído
            "nro_recibo": "000000002",
            "total_a_pagar": 20.00,
            "monto_pagado": 0.0,  # Pendiente
        },
        "003": {
            "sector": "ALTO",
            "medidores": [{"lectura_actual": 50}],
            # Sin nro_recibo todavía
        },
    }

    stats_sectores, stats_recibos = calcular_estadisticas_inicio(config, usuarios, mes)

    # Verificar sectores
    # CENTRO: 2 activos, 1 leído (50%)
    s_centro = next(s for s in stats_sectores if s["sector"] == "CENTRO")
    assert s_centro["total"] == 2
    assert s_centro["leidos"] == 1
    assert s_centro["porcentaje"] == 50
    assert not s_centro["completo"]

    # ALTO: 1 activo, 1 leído (100%, completo)
    s_alto = next(s for s in stats_sectores if s["sector"] == "ALTO")
    assert s_alto["total"] == 1
    assert s_alto["leidos"] == 1
    assert s_alto["porcentaje"] == 100
    assert s_alto["completo"]

    # BAJO: 0 activos, 0 leídos
    s_bajo = next(s for s in stats_sectores if s["sector"] == "BAJO")
    assert s_bajo["total"] == 0
    assert s_bajo["leidos"] == 0
    assert s_bajo["porcentaje"] == 0
    assert not s_bajo["completo"]

    # Verificar recibos
    assert stats_recibos["generados"] == 2
    assert stats_recibos["pagados"] == 1
    assert stats_recibos["pendientes"] == 1
