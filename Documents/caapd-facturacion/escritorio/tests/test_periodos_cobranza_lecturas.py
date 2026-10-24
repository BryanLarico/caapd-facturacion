import pytest
from servicios.datos_padron import ServicioDatosPadron


def test_obtener_periodo_cobranza_y_lecturas():
    servicio = ServicioDatosPadron.__new__(ServicioDatosPadron)
    servicio.periodo = "2026-10"
    servicio.base_dir = None
    servicio.config = {"mes_actual": {"periodo": "2026-10", "estado": "ABIERTO"}}
    servicio.meses_encontrados = {
        "2026-09": {
            "u1": {"nro_recibo": "REC-001", "total_a_pagar": 50.0, "pago": "SI", "medidores": [{"lectura_actual": 100}]}
        },
        "2026-10": {
            "u1": {"nro_recibo": None, "total_a_pagar": 0.0, "pago": "NO", "medidores": [{"lectura_actual": None}]}
        },
    }
    servicio.config_por_periodo = {
        "2026-09": {"mes_actual": {"estado": "FACTURADO"}},
        "2026-10": {"mes_actual": {"estado": "ABIERTO"}},
    }
    servicio.mes = servicio.meses_encontrados["2026-10"]

    assert "2026-10" in servicio.obtener_periodos_disponibles()
    assert "2026-09" in servicio.obtener_periodos_disponibles()

    # Caso 1: Lecturas en curso (2026-10 vacío, lectores en la calle) -> Cobranza activa es 2026-09
    assert servicio.obtener_periodo_cobranza() == "2026-09"
    assert servicio.obtener_periodo_lecturas() == "2026-10"

    # Caso 2: Se descargaron las lecturas de los lectores a 2026-10 -> Cobranza activa pasa a 2026-10
    servicio.meses_encontrados["2026-10"]["u1"]["medidores"] = [{"lectura_actual": 125}]
    assert servicio.obtener_periodo_cobranza() == "2026-10"


def test_sincronizar_deudas_desde_mes_previo(monkeypatch):
    servicio = ServicioDatosPadron.__new__(ServicioDatosPadron)
    servicio.periodo = "2026-10"
    servicio.base_dir = None

    mes_2026_09 = {
        # Cliente que pagó en los días de lecturas (ej. 28 de octubre)
        "u1": {
            "total_a_pagar": 45.0,
            "monto_pagado": 45.0,
            "pago": "SI",
            "meses_adeudados": 1,
        },
        # Cliente que NO pagó
        "u2": {
            "total_a_pagar": 30.0,
            "monto_pagado": 0.0,
            "pago": "NO",
            "meses_adeudados": 1,
        },
        # Cliente con deuda manual en mes actual
        "u3": {
            "total_a_pagar": 20.0,
            "monto_pagado": 20.0,
            "pago": "SI",
            "meses_adeudados": 1,
        },
    }

    mes_2026_10 = {
        # Inicialmente tenía arrastre de deuda porque se creó el mes antes de que pagara
        "u1": {
            "deuda_anterior": 45.0,
            "meses_adeudados": 2,
            "deuda_actual": 25.0,
            "total_a_pagar": 70.0,
        },
        "u2": {
            "deuda_anterior": 30.0,
            "meses_adeudados": 1,
            "deuda_actual": 20.0,
            "total_a_pagar": 50.0,
        },
        "u3": {
            "deuda_anterior": 100.0,
            "deuda_anterior_manual": True,
            "meses_adeudados": 1,
            "deuda_actual": 15.0,
            "total_a_pagar": 115.0,
        },
    }

    servicio.meses_encontrados = {
        "2026-09": mes_2026_09,
        "2026-10": mes_2026_10,
    }
    servicio.mes = mes_2026_10

    # Mock guardar_en_respaldo_local para evitar I/O
    guardados = []
    monkeypatch.setattr(servicio, "guardar_en_respaldo_local", lambda p: guardados.append(p))

    actualizados = servicio.sincronizar_deudas_desde_mes_previo("2026-10")

    # u1 pagó -> su deuda anterior en 2026-10 pasa a 0 y meses_adeudados = 1
    assert mes_2026_10["u1"]["deuda_anterior"] == 0.0
    assert mes_2026_10["u1"]["meses_adeudados"] == 1
    assert mes_2026_10["u1"]["total_a_pagar"] == 25.0

    # u2 no pagó -> meses_adeudados pasa a 2
    assert mes_2026_10["u2"]["deuda_anterior"] == 30.0
    assert mes_2026_10["u2"]["meses_adeudados"] == 2
    assert mes_2026_10["u2"]["total_a_pagar"] == 50.0

    # u3 tiene deuda manual -> no se modifica
    assert mes_2026_10["u3"]["deuda_anterior"] == 100.0

    assert actualizados >= 1
    assert "2026-10" in guardados
