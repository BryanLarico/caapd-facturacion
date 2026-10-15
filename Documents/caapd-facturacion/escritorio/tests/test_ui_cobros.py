"""
tests/test_ui_cobros.py — Pruebas unitarias de la pantalla unificada de Cobros y Facturación.

Prueba el modelo de 7 columnas, los filtros por chips, la ficha del usuario,
el cobro todo o nada, el asistente de emisión de recibos y la exportación de morosos.
"""
import os
from pathlib import Path
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMessageBox

from servicios.datos import ServicioDatosMemoria
from ui.paginas.asistente_recibos import DialogoAsistenteEmitirRecibos
from ui.paginas.cobros import PaginaCobros
from ui.paginas.cobros_modelo import ModeloCobros, ProxyCobros


@pytest.fixture(autouse=True)
def mock_message_boxes(monkeypatch):
    """Evita diálogos bloqueantes de QMessageBox en pruebas."""
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)


@pytest.fixture
def servicio_memoria_cobros():
    config = {
        "ultimo_recibo": 105,
        "sectores": ["BARRIO DE CHAUPI", "BARRIO DE PACHAYZA"],
        "categorias": {
            "A": {
                "nombre": "Doméstico",
                "tarifa_desague": 0.0,
                "cargo_fijo": 1.5,
                "modo_rangos": "unico",
                "rangos": [{"m3_desde": 0, "m3_hasta": None, "precio_m3": 1.0}],
            }
        },
        "mes_actual": {
            "periodo": "2026-10",
            "estado": "FACTURADO",
            "fecha_emision": "2026-10-01",
            "fecha_vencimiento": "2026-10-16",
        },
    }
    mes = {
        "07654321": {
            "id_usuario": "07654321",
            "nro_conexion": "000796",
            "nombre": "QUISPE CARLOS",
            "sector": "BARRIO DE CHAUPI",
            "direccion": "CALLE REAL 100",
            "codigo_categoria": "A",
            "nro_recibo": "000000101",
            "consumo_total_m3": 16,
            "total_a_pagar": 17.50,
            "deuda_anterior": 0.0,
            "meses_adeudados": 1,
            "monto_pagado": 0.0,
            "fecha_pago": None,
            "medidores": [
                {
                    "nro_medidor": "003386",
                    "lectura_anterior": 40,
                    "lectura_actual": 56,
                    "novedad": "MEDIDOR_DANADO",
                    "nota": "La tapa está rota",
                    "registrado_por": "lector1@caapd.org",
                }
            ],
        },
        "07654322": {
            "id_usuario": "07654322",
            "nro_conexion": "000800",
            "nombre": "FLORES MARIA",
            "sector": "BARRIO DE PACHAYZA",
            "direccion": "AV CENTRAL 200",
            "codigo_categoria": "A",
            "nro_recibo": "000000102",
            "consumo_total_m3": 10,
            "total_a_pagar": 35.00,
            "deuda_anterior": 17.50,
            "meses_adeudados": 2,
            "monto_pagado": 0.0,
            "fecha_pago": None,
            "medidores": [
                {
                    "nro_medidor": "001234",
                    "lectura_anterior": 100,
                    "lectura_actual": 110,
                    "novedad": "NORMAL",
                    "nota": "",
                    "registrado_por": "ADMIN",
                }
            ],
        },
        "07654323": {
            "id_usuario": "07654323",
            "nro_conexion": "000805",
            "nombre": "MAMANI JOSE",
            "sector": "BARRIO DE CHAUPI",
            "direccion": "JR LIMA S/N",
            "codigo_categoria": "A",
            "nro_recibo": "000000103",
            "consumo_total_m3": 15,
            "total_a_pagar": 52.50,
            "deuda_anterior": 35.00,
            "meses_adeudados": 3,  # Corte
            "monto_pagado": 0.0,
            "fecha_pago": None,
            "medidores": [
                {
                    "nro_medidor": "009999",
                    "lectura_anterior": 200,
                    "lectura_actual": 215,
                    "novedad": "LECTURA_ESTIMADA",
                    "nota": "Estimada por secretaria",
                    "registrado_por": "ADMIN",
                }
            ],
        },
        "07654324": {
            "id_usuario": "07654324",
            "nro_conexion": "000810",
            "nombre": "ZAPATA ELENA",
            "sector": "BARRIO DE PACHAYZA",
            "direccion": "CALLE UNION 50",
            "codigo_categoria": "A",
            "nro_recibo": "000000104",
            "consumo_total_m3": 18,
            "total_a_pagar": 20.00,
            "deuda_anterior": 0.0,
            "meses_adeudados": 1,
            "monto_pagado": 20.00,  # Totalmente pagado
            "fecha_pago": "2026-10-10",
            "medidores": [
                {
                    "nro_medidor": "005555",
                    "lectura_anterior": 50,
                    "lectura_actual": 68,
                    "novedad": "NORMAL",
                    "nota": "",
                    "registrado_por": "ADMIN",
                }
            ],
        },
    }
    return ServicioDatosMemoria(config=config, mes=mes)


def test_modelo_y_proxy_7_columnas():
    datos = [
        {
            "id_usuario": "07654321",
            "nro_conexion": "000796",
            "nro_recibo": "000000101",
            "nombre": "QUISPE CARLOS",
            "sector": "BARRIO DE CHAUPI",
            "consumo_total_m3": 16,
            "total_a_pagar": 17.50,
            "monto_pagado": 0.0,
            "meses_adeudados": 1,
            "medidores": [{"nro_medidor": "003386", "novedad": "MEDIDOR_DANADO"}],
        },
        {
            "id_usuario": "07654322",
            "nro_conexion": "000800",
            "nro_recibo": "000000102",
            "nombre": "FLORES MARIA",
            "sector": "BARRIO DE PACHAYZA",
            "consumo_total_m3": 10,
            "total_a_pagar": 35.00,
            "monto_pagado": 0.0,
            "meses_adeudados": 2,
            "medidores": [{"nro_medidor": "001234", "novedad": "NORMAL"}],
        },
        {
            "id_usuario": "07654323",
            "nro_conexion": "000805",
            "nro_recibo": "000000103",
            "nombre": "MAMANI JOSE",
            "sector": "BARRIO DE CHAUPI",
            "consumo_total_m3": 15,
            "total_a_pagar": 50.00,
            "monto_pagado": 0.0,
            "meses_adeudados": 3,
            "medidores": [{"nro_medidor": "009999", "novedad": "NORMAL"}],
        },
        {
            "id_usuario": "07654324",
            "nro_conexion": "000810",
            "nro_recibo": "000000104",
            "nombre": "ZAPATA ELENA",
            "sector": "BARRIO DE PACHAYZA",
            "consumo_total_m3": 18,
            "total_a_pagar": 20.00,
            "monto_pagado": 20.00,
            "meses_adeudados": 1,
            "medidores": [{"nro_medidor": "005555", "novedad": "NORMAL"}],
        },
    ]

    modelo = ModeloCobros(datos)
    assert modelo.rowCount() == 4
    assert modelo.columnCount() == 7

    # Columnas: 0:Conexión, 1:N° Recibo, 2:Titular, 3:Sector, 4:Consumo, 5:Total, 6:Estado
    assert modelo.data(modelo.index(0, 0)) == "000796"
    assert modelo.data(modelo.index(0, 1)) == "000000101"
    assert modelo.data(modelo.index(0, 2)) == "QUISPE CARLOS"
    assert modelo.data(modelo.index(0, 3)) == "Chaupi"
    assert modelo.data(modelo.index(0, 4)) == "16"
    assert modelo.data(modelo.index(0, 5)) == "S/. 17.50"
    assert modelo.data(modelo.index(0, 6)) == "Pendiente"

    assert modelo.data(modelo.index(1, 6)) == "2 Meses"
    assert "Corte" in modelo.data(modelo.index(2, 6))
    assert modelo.data(modelo.index(3, 6)) == "Pagado"

    # Probar Proxy y Filtros
    proxy = ProxyCobros()
    proxy.setSourceModel(modelo)
    assert proxy.rowCount() == 4

    # Filtrar por sector
    proxy.set_filtro_sector("BARRIO DE PACHAYZA")
    assert proxy.rowCount() == 2

    # Filtrar solo pendientes
    proxy.set_filtro_sector("todos")
    proxy.set_filtro_estado("pendientes")
    assert proxy.rowCount() == 3

    # Filtrar lista de corte
    proxy.set_filtro_estado("corte")
    assert proxy.rowCount() == 1
    assert proxy.data(proxy.index(0, 2)) == "MAMANI JOSE"

    # Filtrar pagados
    proxy.set_filtro_estado("pagados")
    assert proxy.rowCount() == 1
    assert proxy.data(proxy.index(0, 2)) == "ZAPATA ELENA"

    # Filtrar con alertas
    proxy.set_filtro_estado("con_alertas")
    assert proxy.rowCount() == 1
    assert proxy.data(proxy.index(0, 2)) == "QUISPE CARLOS"

    # Búsqueda inteligente por conexión
    proxy.set_filtro_estado("todos")
    proxy.set_texto_filtro("800")
    assert proxy.rowCount() == 1
    assert proxy.data(proxy.index(0, 2)) == "FLORES MARIA"


def test_servicio_registro_y_anulacion_pago(servicio_memoria_cobros):
    servicio = servicio_memoria_cobros
    ops_inicial = servicio.get_ops()["escrituras"]

    # 1. Pago de QUISPE CARLOS (17.50)
    res_pago = servicio.registrar_pago("2026-10", "07654321", 17.50, fecha_pago="2026-10-13")
    assert res_pago["monto_pagado"] == 17.50
    assert res_pago["fecha_pago"] == "2026-10-13"
    assert servicio.mes["07654321"]["monto_pagado"] == 17.50
    assert servicio.get_ops()["escrituras"] == ops_inicial + 1

    # 2. Anulación de cobro a QUISPE CARLOS
    res_anular = servicio.anular_pago("2026-10", "07654321")
    assert res_anular["monto_pagado"] == 0.0
    assert res_anular["fecha_pago"] is None
    assert servicio.mes["07654321"]["monto_pagado"] == 0.0
    assert servicio.get_ops()["escrituras"] == ops_inicial + 2


def test_exportar_reporte_morosos_excel(servicio_memoria_cobros, tmp_path):
    servicio = servicio_memoria_cobros
    ruta_test = tmp_path / "test_morosos.xlsx"

    ruta_generada = servicio.exportar_reporte_morosos_excel("2026-10", str(ruta_test))
    assert os.path.exists(ruta_generada)
    assert os.path.getsize(ruta_generada) > 0


def test_ui_pagina_cobros_flujo_unificado(qtbot, servicio_memoria_cobros):
    pagina = PaginaCobros(servicio_memoria_cobros)
    qtbot.addWidget(pagina)

    pagina.cargar_datos_asincrono()
    qtbot.waitUntil(lambda: len(pagina.lista_items_completa) == 4, timeout=2000)

    assert pagina.modelo.rowCount() == 4

    # Buscar a QUISPE CARLOS
    fila_quispe = -1
    for r in range(pagina.proxy.rowCount()):
        if "QUISPE CARLOS" in pagina.proxy.data(pagina.proxy.index(r, 2)):
            fila_quispe = r
            break
    assert fila_quispe >= 0

    pagina.tabla.selectRow(fila_quispe)
    assert "QUISPE CARLOS" in pagina.lbl_ficha_nombre.text()
    assert pagina.btn_marcar_pagado.isEnabled() is True
    assert pagina.btn_anular_cobro.isEnabled() is False

    # Verificar que el recuadro de alertas muestre la observación del medidor
    assert not pagina.box_alerta_medidor.isHidden()
    assert "La tapa está rota" in pagina.lbl_texto_alerta_medidor.text()

    # Probar cobro todo o nada
    pagina._accion_marcar_pagado()
    assert pagina.item_seleccionado["monto_pagado"] == 17.50
    assert pagina.btn_marcar_pagado.isHidden()
    assert pagina.btn_anular_cobro.isEnabled() is True


def test_dialogo_asistente_recibos(qtbot, servicio_memoria_cobros):
    # Simular mes cerrado con un medidor pendiente de lectura
    servicio_memoria_cobros.mes["07654321"]["medidores"][0]["lectura_actual"] = None
    diag = DialogoAsistenteEmitirRecibos(servicio_memoria_cobros)
    qtbot.addWidget(diag)

    # Debe iniciar en Paso 1 y detectar el faltante
    assert diag.stacked_pasos.currentIndex() == 0
    assert diag.tabla_faltantes.rowCount() >= 1

    # Estimar faltante automáticamente
    diag._estimar_faltantes_automatico()
    assert diag.tabla_faltantes.isHidden()
