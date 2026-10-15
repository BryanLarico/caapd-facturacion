"""
tests/test_ui_lecturas.py — Pruebas unitarias y de interfaz para Fase D3 (Mes y Lecturas).

Cubre:
1. Verificación previa de base existente (bloqueo si hay mes activo o periodo duplicado).
2. Apertura de mes con usuarios activos y semilla previa.
3. Validación de consumo de medidores y recálculo de consumo_total_m3.
4. Cierre y reapertura de lecturas.
5. ModeloLecturas, ProxyLecturas, filtrado por sector y filtros rápidos por estado.
6. Diálogo de registro/corrección de lecturas y validación de alertas.
"""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from servicios.datos import ServicioDatosMemoria
from ui.paginas.lecturas_dialogo import DialogoLectura
from ui.paginas.lecturas_modelo import ModeloLecturas, ProxyLecturas
from ui.paginas.mes_dialogo import DialogoAbrirMes


@pytest.fixture(autouse=True)
def mock_message_boxes(monkeypatch):
    """Evita modales bloqueantes durante la ejecución de los tests."""
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)


@pytest.fixture
def servicio_mock():
    config = {
        "sectores": ["BARRIO DE CHAUPI", "BARRIO DE PACHAYZA", "BARRIO DE LUCMANI"],
        "categorias": {
            "A": {"nombre": "Doméstico", "cargo_fijo": 1.5, "modo_rangos": "unico", "rangos": [{"m3_desde": 0, "m3_hasta": None, "precio_m3": 1.0}]}
        },
        "observaciones": [
            {"codigo": "NORMAL", "texto": "Normal"},
            {"codigo": "MEDIDOR_DANADO", "texto": "Medidor dañado"},
            {"codigo": "CAMBIO_MEDIDOR", "texto": "Cambio de medidor"},
        ],
        "mes_actual": {"periodo": None, "estado": "CERRADO"},
        "dias_vencimiento": 15,
    }
    usuarios = {
        "70112233": {
            "nro_conexion": "000001",
            "nombre": "JUAN PEREZ QUISPE",
            "sector": "BARRIO DE CHAUPI",
            "direccion": "CALLE REAL 100",
            "codigo_categoria": "A",
            "activo": True,
            "medidores": ["001001"],
        },
        "70223344": {
            "nro_conexion": "000002",
            "nombre": "MARIA LOPEZ FLORES",
            "sector": "BARRIO DE PACHAYZA",
            "direccion": "AV CENTRAL 200",
            "codigo_categoria": "A",
            "activo": True,
            "medidores": ["002001", "002002"],
        },
        "SD-001": {
            "nro_conexion": "000003",
            "nombre": "PEDRO SIN DNI",
            "sector": "BARRIO DE LUCMANI",
            "direccion": "S/N",
            "codigo_categoria": "A",
            "activo": False,  # Inactivo: no debe entrar al mes
            "medidores": ["003001"],
        },
    }
    return ServicioDatosMemoria(config=config, usuarios=usuarios)


def test_verificar_puede_abrir_mes_bloquea_si_hay_mes_activo(servicio_mock):
    # Sin mes activo: debe permitir abrir
    puede, motivo, sugerido = servicio_mock.verificar_puede_abrir_mes()
    assert puede is True
    assert sugerido is not None

    # Con mes ABIERTO en curso: debe bloquear
    servicio_mock.config["mes_actual"] = {"periodo": "2026-09", "estado": "ABIERTO"}
    puede, motivo, _ = servicio_mock.verificar_puede_abrir_mes()
    assert puede is False
    assert "Ya existe una base activa" in motivo

    # Con mes CERRADO sin facturar: debe bloquear
    servicio_mock.config["mes_actual"] = {"periodo": "2026-09", "estado": "CERRADO"}
    puede, motivo, _ = servicio_mock.verificar_puede_abrir_mes()
    assert puede is False
    assert "Debe cerrarse y facturarse" in motivo

    # Con mes FACTURADO: sí debe permitir abrir el siguiente
    servicio_mock.config["mes_actual"] = {"periodo": "2026-09", "estado": "FACTURADO"}
    puede, _, sugerido = servicio_mock.verificar_puede_abrir_mes()
    assert puede is True
    assert sugerido == "2026-10"


def test_verificar_periodo_disponible_bloquea_si_base_existe(servicio_mock):
    # No existe la base 2026-10
    disp, _ = servicio_mock.verificar_periodo_disponible("2026-10")
    assert disp is True

    # Si simulamos que ya existe una base previa
    servicio_mock.meses_existentes = {"2026-09"}
    disp, mot = servicio_mock.verificar_periodo_disponible("2026-09")
    assert disp is False
    assert "Ya existe una base de datos registrada" in mot


def test_abrir_mes_crea_documentos_para_usuarios_activos(servicio_mock):
    lecturas_ini = {"001001": 50, "002001": 120, "002002": 30}
    res = servicio_mock.abrir_mes(
        periodo="2026-10",
        fecha_emision="2026-10-10",
        fecha_vencimiento="2026-10-25",
        lecturas_iniciales=lecturas_ini,
    )

    assert res["periodo"] == "2026-10"
    assert res["estado"] == "ABIERTO"
    # Solo los 2 usuarios activos (SD-001 es inactivo)
    assert res["usuarios_creados"] == 2

    mes_docs = servicio_mock.cargar_mes("2026-10")
    assert "70112233" in mes_docs
    assert "70223344" in mes_docs
    assert "SD-001" not in mes_docs

    # Verificar lectura anterior asignada
    doc_juan = mes_docs["70112233"]
    assert doc_juan["medidores"][0]["lectura_anterior"] == 50
    assert doc_juan["medidores"][0]["estado_lectura"] == "PENDIENTE"
    assert doc_juan["medidores"][0]["lectura_actual"] is None
    assert doc_juan["consumo_total_m3"] is None


def test_guardar_lectura_medidor_y_recalcular_consumo(servicio_mock):
    servicio_mock.abrir_mes("2026-10", "2026-10-10", "2026-10-25", {"001001": 50})
    
    # Guardar lectura para Juan (50 -> 65 = 15 m³)
    res = servicio_mock.guardar_lectura_medidor(
        periodo="2026-10",
        id_usuario="70112233",
        nro_medidor="001001",
        lectura_actual=65,
        novedad="NORMAL",
    )
    assert res["consumo_total_m3"] == 15.0

    doc_juan = servicio_mock.cargar_mes("2026-10")["70112233"]
    med = doc_juan["medidores"][0]
    assert med["lectura_actual"] == 65
    assert med["estado_lectura"] == "LEIDO"
    assert doc_juan["consumo_total_m3"] == 15.0


def test_guardar_lectura_invalida_menor_sin_cambio_lanza_error(servicio_mock):
    servicio_mock.abrir_mes("2026-10", "2026-10-10", "2026-10-25", {"001001": 50})

    # Lectura 40 < 50 sin cambio de medidor debe fallar
    with pytest.raises(ValueError):
        servicio_mock.guardar_lectura_medidor(
            periodo="2026-10",
            id_usuario="70112233",
            nro_medidor="001001",
            lectura_actual=40,
            novedad="NORMAL",
        )

    # Con novedad CAMBIO_MEDIDOR debe ser válida (consumo = 40)
    res = servicio_mock.guardar_lectura_medidor(
        periodo="2026-10",
        id_usuario="70112233",
        nro_medidor="001001",
        lectura_actual=40,
        novedad="CAMBIO_MEDIDOR",
    )
    assert res["consumo_total_m3"] == 40.0


def test_cerrar_y_reabrir_lecturas(servicio_mock):
    servicio_mock.abrir_mes("2026-10", "2026-10-10", "2026-10-25")
    assert servicio_mock.config["mes_actual"]["estado"] == "ABIERTO"

    # Cerrar
    servicio_mock.cerrar_lecturas("2026-10")
    assert servicio_mock.config["mes_actual"]["estado"] == "CERRADO"

    # Reabrir
    servicio_mock.reabrir_lecturas("2026-10")
    assert servicio_mock.config["mes_actual"]["estado"] == "ABIERTO"


def test_modelo_lecturas_y_proxy_filtros(qtbot, servicio_mock):
    items = [
        {
            "id_usuario": "70112233",
            "nro_conexion": "000001",
            "nombre": "JUAN PEREZ",
            "sector": "BARRIO DE CHAUPI",
            "nro_medidor": "001001",
            "lectura_anterior": 50,
            "lectura_actual": 65,
            "estado_lectura": "LEIDO",
            "novedad": "NORMAL",
            "nota": "",
        },
        {
            "id_usuario": "70223344",
            "nro_conexion": "000002",
            "nombre": "MARIA LOPEZ",
            "sector": "BARRIO DE PACHAYZA",
            "nro_medidor": "002001",
            "lectura_anterior": 120,
            "lectura_actual": None,
            "estado_lectura": "PENDIENTE",
            "novedad": "",
            "nota": "",
        },
        {
            "id_usuario": "70334455",
            "nro_conexion": "000003",
            "nombre": "CARLOS SOSA",
            "sector": "BARRIO DE CHAUPI",
            "nro_medidor": "003001",
            "lectura_anterior": 80,
            "lectura_actual": None,
            "estado_lectura": "SIN_ACCESO",
            "novedad": "CASA_CERRADA",
            "nota": "Reja con candado",
        },
    ]

    modelo = ModeloLecturas(items)
    proxy = ProxyLecturas()
    proxy.setSourceModel(modelo)

    assert proxy.rowCount() == 3

    # Filtrar por sector Chaupi
    proxy.set_filtro_sector("BARRIO DE CHAUPI")
    assert proxy.rowCount() == 2

    # Restablecer sector y filtrar por estado Faltan
    proxy.set_filtro_sector("todos")
    proxy.set_filtro_estado("faltan")
    assert proxy.rowCount() == 1  # Solo Maria

    # Filtrar por Sin acceso
    proxy.set_filtro_estado("sin_acceso")
    assert proxy.rowCount() == 1  # Solo Carlos

    # Filtrar por Con observacion
    proxy.set_filtro_estado("con_observacion")
    assert proxy.rowCount() == 1  # Solo Carlos (CASA_CERRADA)


def test_dialogo_abrir_mes_ui(qtbot, servicio_mock):
    diag = DialogoAbrirMes(servicio_mock)
    qtbot.addWidget(diag)

    assert diag.btn_abrir.isEnabled() is True
    # Periodo sugerido
    assert len(diag.input_periodo.text()) == 7

    # Si se intenta abrir un periodo ya existente, la UI lo bloquea
    servicio_mock.meses_existentes = {"2026-08"}
    diag.input_periodo.setText("2026-08")
    assert diag.btn_abrir.isEnabled() is False
    assert not diag.lbl_alerta_periodo.isHidden()
