"""
tests/test_ui_configuracion.py — Pruebas unitarias para la pantalla de Configuración (Fase 6).
"""
import pytest
from PySide6.QtWidgets import QMessageBox

from ui.paginas.configuracion import PaginaConfiguracion
from servicios.datos import ServicioDatosMemoria


@pytest.fixture
def servicio_config_memoria():
    config = {
        "empresa": {
            "nombre": "COMITÉ DE ADMINISTRACIÓN DE AGUA POTABLE Y DESAGÜE DE ISPACAS",
            "resolucion": "192-2017",
            "telefono": "986054179",
            "whatsapp": "986054179",
            "direccion": "Calle 5 de Agosto s/n - Ispacas",
        },
        "igv": {"activo": True, "porcentaje": 0.18},
        "dias_vencimiento": 15,
        "ultimo_recibo": 105,
        "sectores": [
            "BARRIO DE CHAUPI",
            "BARRIO DE PACHAYZA",
            "BARRIO DE LUCMANI",
        ],
        "categorias": {
            "A": {
                "nombre": "Doméstico",
                "cargo_fijo": 1.50,
                "tarifa_desague": 0.0,
                "modo_rangos": "tramos",
                "rangos": [
                    {"m3_desde": 0, "m3_hasta": 10, "precio_m3": 1.00},
                    {"m3_desde": 11, "m3_hasta": None, "precio_m3": 1.50},
                ],
            },
            "B": {
                "nombre": "Comercial",
                "cargo_fijo": 3.00,
                "tarifa_desague": 0.50,
                "modo_rangos": "unico",
                "rangos": [
                    {"m3_desde": 0, "m3_hasta": None, "precio_m3": 2.00},
                ],
            },
        },
        "observaciones": [
            {"codigo": "NORMAL", "texto": "Normal", "alerta": False},
            {"codigo": "FUGA", "texto": "Fuga de agua", "alerta": True},
        ],
    }
    return ServicioDatosMemoria(config=config)


def test_ui_pagina_configuracion_carga(qtbot, servicio_config_memoria):
    pagina = PaginaConfiguracion(servicio_config_memoria)
    qtbot.addWidget(pagina)

    pagina.cargar_datos_asincrono()
    qtbot.waitUntil(lambda: pagina.config_cargada is True, timeout=2000)

    # Verificar datos cargados en pestaña Empresa
    assert "COMITÉ" in pagina.txt_empresa_nombre.text()
    assert pagina.txt_empresa_resolucion.text() == "192-2017"
    assert pagina.spin_dias_vencimiento.value() == 15
    assert pagina.spin_ultimo_recibo.value() == 105

    # Verificar IGV
    assert pagina.chk_igv_activo.isChecked() is True
    assert pagina.spin_igv_porcentaje.value() == 18.0

    # Verificar Sectores
    assert pagina.tabla_sectores.rowCount() == 3
    assert pagina.tabla_sectores.item(0, 1).text() == "BARRIO DE CHAUPI"

    # Verificar Observaciones
    assert pagina.tabla_observaciones.rowCount() == 2
    assert pagina.tabla_observaciones.item(0, 0).text() == "NORMAL"


def test_ui_pagina_configuracion_edicion_sectores_y_obs(qtbot, servicio_config_memoria, monkeypatch):
    pagina = PaginaConfiguracion(servicio_config_memoria)
    qtbot.addWidget(pagina)

    pagina.cargar_datos_asincrono()
    qtbot.waitUntil(lambda: pagina.config_cargada is True, timeout=2000)

    # Agregar sector simulando input
    from PySide6.QtWidgets import QInputDialog
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("HUAQUILLO", True))
    pagina._accion_agregar_sector()

    assert pagina.tabla_sectores.rowCount() == 4
    assert pagina.tabla_sectores.item(3, 1).text() == "HUAQUILLO"

    # Agregar observación simulando inputs
    respuestas = iter([("MEDIDOR_ROTO", True), ("Medidor destrozado", True)])
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: next(respuestas))
    pagina._accion_agregar_observacion()

    assert pagina.tabla_observaciones.rowCount() == 3
    assert pagina.tabla_observaciones.item(2, 0).text() == "MEDIDOR_ROTO"


def test_ui_pagina_configuracion_guardar(qtbot, servicio_config_memoria, monkeypatch):
    pagina = PaginaConfiguracion(servicio_config_memoria)
    qtbot.addWidget(pagina)

    pagina.cargar_datos_asincrono()
    qtbot.waitUntil(lambda: pagina.config_cargada is True, timeout=2000)

    # Modificar valores
    pagina.txt_empresa_telefono.setText("999888777")
    pagina.spin_ultimo_recibo.setValue(200)

    # Simular confirmación afirmativa
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)

    pagina._accion_guardar_configuracion()
    qtbot.waitUntil(lambda: pagina.btn_guardar.isEnabled() is True, timeout=2000)

    # Comprobar que el servicio en memoria fue actualizado
    cfg_actualizada = servicio_config_memoria.cargar_config()
    assert cfg_actualizada["empresa"]["telefono"] == "999888777"
    assert cfg_actualizada["ultimo_recibo"] == 200
