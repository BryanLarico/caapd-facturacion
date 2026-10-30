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


def test_traer_lecturas_de_lectores_emite_recibos_y_calcula_morosidad(monkeypatch):
    servicio = ServicioDatosPadron.__new__(ServicioDatosPadron)
    servicio.periodo = "2026-10"
    servicio.base_dir = None
    servicio.config = {
        "mes_actual": {"periodo": "2026-10", "estado": "ABIERTO"},
        "ultimo_recibo": 150,
        "categorias": {
            "A": {
                "nombre": "Doméstico",
                "cargo_fijo": 5.0,
                "tarifa_plana": False,
                "rangos": [{"hasta": 10, "precio": 1.0}],
            }
        },
    }
    # Usuario 1: pagó en 2026-09
    # Usuario 2: debía 1 mes en 2026-09 y no pagó -> debe pasar a 2 Meses (Naranja)
    # Usuario 3: debía 2 meses en 2026-09 y no pagó -> debe pasar a Corte 3 meses (Rojo)
    mes_2026_09 = {
        "u1": {"total_a_pagar": 20.0, "monto_pagado": 20.0, "pago": "SI", "meses_adeudados": 1, "nro_recibo": "000000148"},
        "u2": {"total_a_pagar": 25.0, "monto_pagado": 0.0, "pago": "NO", "meses_adeudados": 1, "nro_recibo": "000000149"},
        "u3": {"total_a_pagar": 40.0, "monto_pagado": 0.0, "pago": "NO", "meses_adeudados": 2, "nro_recibo": "000000150"},
    }
    mes_2026_10 = {
        "u1": {
            "nro_conexion": "1",
            "codigo_categoria": "A",
            "deuda_anterior": 20.0,
            "meses_adeudados": 1,
            "nro_recibo": None,
            "medidores": [{"nro_medidor": "M1", "lectura_anterior": 100, "lectura_actual": 110}],
        },
        "u2": {
            "nro_conexion": "2",
            "codigo_categoria": "A",
            "deuda_anterior": 25.0,
            "meses_adeudados": 1,
            "nro_recibo": None,
            "medidores": [{"nro_medidor": "M2", "lectura_anterior": 50, "lectura_actual": 55}],
        },
        "u3": {
            "nro_conexion": "3",
            "codigo_categoria": "A",
            "deuda_anterior": 40.0,
            "meses_adeudados": 2,
            "nro_recibo": None,
            "medidores": [{"nro_medidor": "M3", "lectura_anterior": 200, "lectura_actual": 210}],
        },
    }
    servicio.meses_encontrados = {
        "2026-09": mes_2026_09,
        "2026-10": mes_2026_10,
    }
    servicio.mes = mes_2026_10

    monkeypatch.setattr(servicio, "guardar_en_respaldo_local", lambda *args, **kwargs: None)
    monkeypatch.setattr(servicio, "_contar_op", lambda *args, **kwargs: None)

    # Ejecutar traer_lecturas_de_lectores (lecturas completas localmente)
    servicio.traer_lecturas_de_lectores("2026-10")

    # Verificar que los 3 usuarios tienen número de recibo consecutivo
    assert mes_2026_10["u1"]["nro_recibo"] is not None
    assert mes_2026_10["u2"]["nro_recibo"] is not None
    assert mes_2026_10["u3"]["nro_recibo"] is not None
    assert int(mes_2026_10["u1"]["nro_recibo"]) > 150

    # u1: pagó mes anterior -> deuda_anterior = 0, meses_adeudados = 1
    assert mes_2026_10["u1"]["deuda_anterior"] == 0.0
    assert mes_2026_10["u1"]["meses_adeudados"] == 1

    # u2: no pagó mes anterior (tenía 1 mes) -> pasa a meses_adeudados = 2 (Naranja)
    assert mes_2026_10["u2"]["deuda_anterior"] == 25.0
    assert mes_2026_10["u2"]["meses_adeudados"] == 2

    # u3: no pagó mes anterior (tenía 2 meses) -> pasa a meses_adeudados = 3 (Rojo/Corte)
    assert mes_2026_10["u3"]["deuda_anterior"] == 40.0
    assert mes_2026_10["u3"]["meses_adeudados"] == 3

    # Estado del mes pasó a FACTURADO
    assert servicio.config["mes_actual"]["estado"] == "FACTURADO"

    # Verificar que en el modelo de cobros se colorea correctamente
    from ui.paginas.cobros_modelo import color_fila_morosidad, COLOR_FILA_DOS_MESES, COLOR_FILA_CORTE
    assert color_fila_morosidad(mes_2026_10["u1"]) is None
    assert color_fila_morosidad(mes_2026_10["u2"]) == COLOR_FILA_DOS_MESES
    assert color_fila_morosidad(mes_2026_10["u3"]) == COLOR_FILA_CORTE


def test_extraccion_parcial_multidias_lecturas(monkeypatch):
    servicio = ServicioDatosPadron.__new__(ServicioDatosPadron)
    servicio.periodo = "2026-10"
    servicio.base_dir = None
    servicio.config = {
        "mes_actual": {"periodo": "2026-10", "estado": "ABIERTO"},
        "ultimo_recibo": 100,
        "categorias": {
            "A": {
                "nombre": "Doméstico",
                "cargo_fijo": 1.5,
                "tarifa_plana": False,
                "rangos": [{"hasta": 10, "precio": 1.5}],
            }
        },
    }
    mes_2026_10 = {
        "u1": {
            "nro_conexion": "1",
            "codigo_categoria": "A",
            "deuda_anterior": 0.0,
            "meses_adeudados": 1,
            "nro_recibo": None,
            "medidores": [{"nro_medidor": "M1", "lectura_anterior": 100, "lectura_actual": None, "estado_lectura": "PENDIENTE"}],
        },
        "u2": {
            "nro_conexion": "2",
            "codigo_categoria": "A",
            "deuda_anterior": 0.0,
            "meses_adeudados": 1,
            "nro_recibo": None,
            "medidores": [{"nro_medidor": "M2", "lectura_anterior": 50, "lectura_actual": None, "estado_lectura": "PENDIENTE"}],
        },
    }
    servicio.meses_encontrados = {"2026-10": mes_2026_10}
    servicio.mes = mes_2026_10

    monkeypatch.setattr(servicio, "guardar_en_respaldo_local", lambda *args, **kwargs: None)
    monkeypatch.setattr(servicio, "_contar_op", lambda *args, **kwargs: None)
    monkeypatch.setattr(servicio, "sincronizar_deudas_desde_mes_previo", lambda *args, **kwargs: 0)

    # Simular Día 1: Lector en celular solo leyó u1 (M1 = 108 m³), u2 sigue PENDIENTE
    docs_dia_1 = {
        "u1": {
            "medidores": [{"nro_medidor": "M1", "lectura_actual": 108, "estado_lectura": "LEIDO", "novedad": "NORMAL"}],
        },
        "u2": {
            "medidores": [{"nro_medidor": "M2", "lectura_actual": None, "estado_lectura": "PENDIENTE", "novedad": "NORMAL"}],
        },
    }
    monkeypatch.setattr(servicio, "_descargar_docs_en_subproceso", lambda *args, **kwargs: {"docs": docs_dia_1, "recibidos": 2})

    # Ejecutar extracción Día 1 en la PC
    res_dia_1 = servicio.traer_lecturas_de_lectores("2026-10")
    assert res_dia_1["actualizados"] == 1

    # u1 debe estar leído con su consumo real (108 - 100 = 8 m³)
    assert mes_2026_10["u1"]["medidores"][0]["lectura_actual"] == 108
    assert mes_2026_10["u1"]["medidores"][0]["consumo"] == 8
    assert mes_2026_10["u1"]["medidores"][0]["estado_lectura"] == "LEIDO"
    # No debe tener recibo todavía porque el mes sigue abierto
    assert mes_2026_10["u1"]["nro_recibo"] is None

    # u2 NO debe haber sido alterado a consumo cero ni ESTIMADO
    assert mes_2026_10["u2"]["medidores"][0]["lectura_actual"] is None
    assert mes_2026_10["u2"]["medidores"][0]["estado_lectura"] == "PENDIENTE"
    assert mes_2026_10["u2"]["nro_recibo"] is None

    # El mes debe permanecer ABIERTO
    assert servicio.config["mes_actual"]["estado"] == "ABIERTO"

    # Simular Día 2: Lector lee u2 (M2 = 57 m³)
    docs_dia_2 = {
        "u1": {
            "medidores": [{"nro_medidor": "M1", "lectura_actual": 108, "estado_lectura": "LEIDO", "novedad": "NORMAL"}],
        },
        "u2": {
            "medidores": [{"nro_medidor": "M2", "lectura_actual": 57, "estado_lectura": "LEIDO", "novedad": "NORMAL"}],
        },
    }
    monkeypatch.setattr(servicio, "_descargar_docs_en_subproceso", lambda *args, **kwargs: {"docs": docs_dia_2, "recibidos": 2})

    # Ejecutar extracción Día 2 en la PC
    res_dia_2 = servicio.traer_lecturas_de_lectores("2026-10")
    assert res_dia_2["actualizados"] == 2

    # Ahora ambos están leídos
    assert mes_2026_10["u1"]["medidores"][0]["lectura_actual"] == 108
    assert mes_2026_10["u2"]["medidores"][0]["lectura_actual"] == 57
    assert mes_2026_10["u2"]["medidores"][0]["consumo"] == 7
    assert mes_2026_10["u2"]["medidores"][0]["estado_lectura"] == "LEIDO"

    # Ahora sí se emitieron recibos porque todas las lecturas están completas
    assert mes_2026_10["u1"]["nro_recibo"] is not None
    assert mes_2026_10["u2"]["nro_recibo"] is not None
    assert servicio.config["mes_actual"]["estado"] == "FACTURADO"


