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
                "modo_rangos": "unico",
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
    monkeypatch.setattr(QInputDialog, "getText",
                        lambda *args, **kwargs: ("HUAQUILLO", True))
    pagina._accion_agregar_sector()

    assert pagina.tabla_sectores.rowCount() == 4
    assert pagina.tabla_sectores.item(3, 1).text() == "HUAQUILLO"

    # Agregar observación simulando inputs
    respuestas = iter([("MEDIDOR_ROTO", True), ("Medidor destrozado", True)])
    monkeypatch.setattr(QInputDialog, "getText",
                        lambda *args, **kwargs: next(respuestas))
    pagina._accion_agregar_observacion()

    assert pagina.tabla_observaciones.rowCount() == 3
    assert pagina.tabla_observaciones.item(2, 0).text() == "MEDIDOR_ROTO"

    # Al haber agregado filas, el botón Guardar debe estar habilitado
    assert pagina.btn_guardar.isEnabled() is True


def test_ui_pagina_configuracion_guardar(qtbot, servicio_config_memoria, monkeypatch):
    pagina = PaginaConfiguracion(servicio_config_memoria)
    qtbot.addWidget(pagina)

    pagina.cargar_datos_asincrono()
    qtbot.waitUntil(lambda: pagina.config_cargada is True, timeout=2000)

    # Recién cargado: sin cambios -> botón deshabilitado
    assert pagina.btn_guardar.isEnabled() is False

    # Modificar valores -> botón habilitado
    pagina.txt_empresa_telefono.setText("999888777")
    pagina.spin_ultimo_recibo.setValue(200)
    assert pagina.btn_guardar.isEnabled() is True

    # Simular confirmación afirmativa
    monkeypatch.setattr(QMessageBox, "question", lambda *args,
                        **kwargs: QMessageBox.StandardButton.Yes)

    pagina._accion_guardar_configuracion()
    # Tras guardar, la línea base se reinicia y el botón vuelve a deshabilitarse
    qtbot.waitUntil(lambda: pagina.config_actual.get(
        "ultimo_recibo") == 200, timeout=2000)
    qtbot.waitUntil(lambda: pagina.btn_guardar.isEnabled()
                    is False, timeout=2000)

    # Comprobar que el servicio en memoria fue actualizado
    cfg_actualizada = servicio_config_memoria.cargar_config()
    assert cfg_actualizada["empresa"]["telefono"] == "999888777"
    assert cfg_actualizada["ultimo_recibo"] == 200
    # El método de facturación siempre se persiste como rango único
    assert cfg_actualizada["categorias"]["A"]["modo_rangos"] == "unico"


def test_ui_boton_guardar_deshabilitado_sin_cambios(qtbot, servicio_config_memoria):
    pagina = PaginaConfiguracion(servicio_config_memoria)
    qtbot.addWidget(pagina)

    pagina.cargar_datos_asincrono()
    qtbot.waitUntil(lambda: pagina.config_cargada is True, timeout=2000)

    assert pagina.btn_guardar.isEnabled() is False          # sin cambios
    pagina.spin_dias_vencimiento.setValue(20)
    assert pagina.btn_guardar.isEnabled() is True           # con cambio
    pagina.spin_dias_vencimiento.setValue(15)
    assert pagina.btn_guardar.isEnabled() is False          # vuelve al valor original

    # Elementos eliminados de la pantalla
    # Método de facturación eliminado
    assert not hasattr(pagina, "rb_modo_unico")
    assert not hasattr(pagina, "rb_modo_tramos")
    # Subir/Bajar eliminados
    assert not hasattr(pagina, "btn_subir_sector")
    assert not hasattr(pagina, "btn_bajar_sector")
    # sin pestaña Respaldo y Contingencia
    assert pagina.tabs.count() == 4
    for i in range(pagina.tabs.count()):
        assert "Respaldo" not in pagina.tabs.tabText(i)


def test_ui_cambio_de_categoria_conserva_edicion(qtbot, servicio_config_memoria):
    """Al editar la categoría A y pasar a B, los cambios de A se conservan en caché."""
    pagina = PaginaConfiguracion(servicio_config_memoria)
    qtbot.addWidget(pagina)

    pagina.cargar_datos_asincrono()
    qtbot.waitUntil(lambda: pagina.config_cargada is True, timeout=2000)

    pagina.spin_cat_cargo_fijo.setValue(9.75)              # editar categoría A
    pagina.spin_cat_cargo_fijo_sin_consumo.setValue(7.25)
    pagina.combo_categoria.setCurrentIndex(1)              # pasar a B
    assert pagina.config_actual["categorias"]["A"]["cargo_fijo"] == 9.75
    assert pagina.config_actual["categorias"]["A"]["cargo_fijo_sin_consumo"] == 7.25
    # sigue habiendo cambios pendientes
    assert pagina.btn_guardar.isEnabled() is True

    pagina.combo_categoria.setCurrentIndex(0)              # volver a A
    assert pagina.spin_cat_cargo_fijo.value() == 9.75
    assert pagina.spin_cat_cargo_fijo_sin_consumo.value() == 7.25

