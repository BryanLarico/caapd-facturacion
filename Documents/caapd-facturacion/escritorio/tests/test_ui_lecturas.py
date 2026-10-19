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
import datetime
import threading

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHeaderView, QMessageBox

from servicios.datos import (
    ServicioDatosMemoria,
    obtener_periodo_actual,
    siguiente_periodo,
    todas_lecturas_completas,
)
from servicios.datos_padron import ServicioDatosPadron
from ui.paginas.lecturas_dialogo import DialogoLectura
from ui.paginas.lecturas import PaginaLecturas
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


def test_verificar_puede_abrir_mes_bloquea_si_hay_mes_activo(servicio_mock, monkeypatch):
    monkeypatch.setattr("servicios.datos.obtener_periodo_actual", lambda: "2026-10")

    # Sin mes activo: debe permitir abrir
    puede, motivo, sugerido = servicio_mock.verificar_puede_abrir_mes()
    assert puede is True
    assert sugerido == "2026-10"

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


def test_periodo_actual_se_obtiene_de_la_fecha_del_sistema():
    assert obtener_periodo_actual(datetime.date(2026, 10, 15)) == "2026-10"
    assert siguiente_periodo("2026-12") == "2027-01"


def test_todas_lecturas_completas_exige_estado_leido():
    assert todas_lecturas_completas({
        "usuario": {"medidores": [{"estado_lectura": "LEIDO"}]}
    })
    assert not todas_lecturas_completas({
        "usuario": {"medidores": [{"estado_lectura": "PENDIENTE"}]}
    })
    assert not todas_lecturas_completas({
        "usuario": {"medidores": [{"estado_lectura": "SIN_ACCESO"}]}
    })


def test_mes_cerrado_antiguo_permite_abrir_el_periodo_calendario_actual(
    servicio_mock, monkeypatch
):
    monkeypatch.setattr("servicios.datos.obtener_periodo_actual", lambda: "2026-10")
    servicio_mock.config["mes_actual"] = {
        "periodo": "2026-08",
        "estado": "CERRADO",
    }
    servicio_mock.mes = {
        "usuario": {"medidores": [{"estado_lectura": "LEIDO"}]}
    }

    puede, motivo, sugerido = servicio_mock.verificar_puede_abrir_mes()

    assert puede is True
    assert sugerido == "2026-10"

    # Aunque el periodo sea el mes anterior, no se puede avanzar con lecturas pendientes.
    servicio_mock.config["mes_actual"]["periodo"] = "2026-09"
    servicio_mock.mes["usuario"]["medidores"][0]["estado_lectura"] = "PENDIENTE"
    puede, _, _ = servicio_mock.verificar_puede_abrir_mes()
    assert puede is False

    # Nunca se permite saltar una base que continúa abierta.
    servicio_mock.config["mes_actual"] = {
        "periodo": "2026-06",
        "estado": "ABIERTO",
    }
    puede, _, _ = servicio_mock.verificar_puede_abrir_mes()
    assert puede is False


def test_mes_cerrado_con_lecturas_completas_permite_abrir_el_siguiente(
    servicio_mock, monkeypatch
):
    monkeypatch.setattr("servicios.datos.obtener_periodo_actual", lambda: "2026-09")
    servicio_mock.config["mes_actual"] = {
        "periodo": "2026-08",
        "estado": "CERRADO",
    }
    servicio_mock.mes = {
        "usuario": {"medidores": [{"estado_lectura": "LEIDO"}]}
    }

    puede, _, sugerido = servicio_mock.verificar_puede_abrir_mes()

    assert puede is True
    assert sugerido == "2026-09"


def test_servicio_padron_permite_mes_actual_si_la_ultima_base_es_antigua(monkeypatch):
    monkeypatch.setattr(
        "servicios.datos_padron.obtener_periodo_actual", lambda: "2026-10"
    )
    servicio = ServicioDatosPadron.__new__(ServicioDatosPadron)
    servicio.config = {
        "mes_actual": {"periodo": "2026-08", "estado": "CERRADO"}
    }
    servicio.periodo = "2026-08"
    servicio.mes = {
        "usuario": {"medidores": [{"estado_lectura": "LEIDO"}]}
    }

    puede, motivo, sugerido = servicio.verificar_puede_abrir_mes()

    assert puede is True
    assert sugerido == "2026-10"

    servicio.mes["usuario"]["medidores"][0]["estado_lectura"] = "PENDIENTE"
    puede, _, _ = servicio.verificar_puede_abrir_mes()
    assert puede is False


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


def test_abrir_mes_copia_datos_relevantes_del_mes_anterior(servicio_mock):
    servicio_mock.config["mes_actual"] = {
        "periodo": "2026-09",
        "estado": "FACTURADO",
    }
    servicio_mock.periodo = "2026-09"
    documento_anterior = {
        "70112233": {
            "nro_conexion": "000001",
            "nombre": "NOMBRE ANTERIOR",
            "sector": "SECTOR ANTERIOR",
            "direccion": "DIRECCION ANTERIOR",
            "codigo_categoria": "B",
            "medidores": [{
                "nro_medidor": "001001",
                "lectura_anterior": 100,
                "lectura_actual": 120,
                "fecha_anterior": "2026-08-25",
                "fecha_lectura": "2026-09-25",
                "consumo": 20,
                "estado_lectura": "LEIDO",
                "novedad": "NORMAL",
                "nota": "Nota de septiembre",
                "registrado_por": "lector@example.com",
            }],
            "consumo_total_m3": 20,
            "historial_m3": [1, 2, 3, 4],
            "total_a_pagar": 100,
            "monto_pagado": 25,
            "meses_adeudados": 2,
            "nro_recibo": "000123",
        }
    }
    servicio_mock.mes = documento_anterior
    servicio_mock.meses_encontrados = {"2026-09": documento_anterior}

    servicio_mock.abrir_mes("2026-10", "2026-10-01", "2026-10-15")

    nuevo = servicio_mock.mes["70112233"]
    medidor = nuevo["medidores"][0]
    assert medidor["lectura_anterior"] == 120
    assert medidor["fecha_anterior"] == "2026-09-25"
    assert medidor["consumo_anterior"] == 20
    assert medidor["lectura_actual"] is None
    assert medidor["estado_lectura"] == "PENDIENTE"
    assert medidor["nota"] == ""
    assert medidor["registrado_por"] is None
    assert nuevo["nombre"] == "JUAN PEREZ QUISPE"
    assert nuevo["historial_m3"] == [1, 2, 3, 4, 20]
    assert nuevo["deuda_anterior"] == 75
    assert nuevo["meses_adeudados"] == 3
    assert nuevo["nro_recibo"] is None
    assert nuevo["total_a_pagar"] is None
    assert nuevo["monto_pagado"] == 0


def test_abrir_mes_padron_copia_lectura_y_saldo_del_mes_anterior(monkeypatch):
    servicio = ServicioDatosPadron.__new__(ServicioDatosPadron)
    anterior = {
        "70112233": {
            "medidores": [{
                "nro_medidor": "001001",
                "lectura_anterior": 100,
                "lectura_actual": 120,
                "fecha_lectura": "2026-09-25",
                "estado_lectura": "LEIDO",
            }],
            "consumo_total_m3": 20,
            "historial_m3": [1, 2, 3, 4],
            "total_a_pagar": 100,
            "monto_pagado": 100,
            "meses_adeudados": 1,
        }
    }
    servicio.config = {"mes_actual": {"periodo": "2026-09", "estado": "FACTURADO"}}
    servicio.periodo = "2026-09"
    servicio.usuarios = {
        "70112233": {
            "nro_conexion": "000001",
            "nombre": "JUAN PEREZ",
            "sector": "BARRIO DE CHAUPI",
            "direccion": "CALLE REAL",
            "codigo_categoria": "A",
            "activo": True,
            "medidores": ["001001"],
        }
    }
    servicio.mes = anterior
    servicio.meses_encontrados = {"2026-09": anterior}
    monkeypatch.setattr(servicio, "guardar_en_respaldo_local", lambda: None)

    resultado = servicio.abrir_mes("2026-10", "2026-10-01", "2026-10-15")

    assert resultado["usuarios_creados"] == 1
    nuevo = servicio.mes["70112233"]
    assert nuevo["medidores"][0]["lectura_anterior"] == 120
    assert nuevo["medidores"][0]["fecha_anterior"] == "2026-09-25"
    assert nuevo["medidores"][0]["consumo_anterior"] == 20
    assert nuevo["historial_m3"] == [1, 2, 3, 4, 20]
    assert nuevo["deuda_anterior"] == 0
    assert nuevo["meses_adeudados"] == 1


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
    assert proxy.rowCount() == 2  # Maria y Carlos (SIN_ACCESO también falta)

    # El filtro de SIN_ACCESO sigue disponible en el modelo aunque ya no haya botón.
    proxy.set_filtro_estado("sin_acceso")
    assert proxy.rowCount() == 1  # Solo Carlos

    # Filtrar por Con observacion
    proxy.set_filtro_estado("con_observacion")
    assert proxy.rowCount() == 1  # Solo Carlos (CASA_CERRADA)


def test_pantalla_lecturas_sin_filtro_sin_acceso_y_con_registrado_por(qtbot, servicio_mock):
    pagina = PaginaLecturas(servicio_mock)
    qtbot.addWidget(pagina)
    config = servicio_mock.cargar_config()
    config["mes_actual"] = {
        "periodo": "2026-10",
        "estado": "ABIERTO",
        "fecha_emision": "2026-10-01",
        "fecha_vencimiento": "2026-10-20",
    }
    documentos = {
        "70112233": {
            "nro_conexion": "000001",
            "nombre": "JUAN PEREZ QUISPE",
            "sector": "BARRIO DE CHAUPI",
            "medidores": [{
                "nro_medidor": "001001",
                "lectura_anterior": 50,
                "lectura_actual": 65,
                "estado_lectura": "LEIDO",
                "novedad": "NORMAL",
                "registrado_por": "LECTOR",
            }],
        },
        "70223344": {
            "nro_conexion": "000002",
            "nombre": "MARIA LOPEZ FLORES",
            "sector": "BARRIO DE PACHAYZA",
            "medidores": [{
                "nro_medidor": "002001",
                "lectura_anterior": 120,
                "lectura_actual": None,
                "estado_lectura": "PENDIENTE",
                "novedad": "NORMAL",
                "registrado_por": "ADMIN",
            }],
        },
        "70334455": {
            "nro_conexion": "000003",
            "nombre": "CARLOS SOSA",
            "sector": "BARRIO DE LUCMANI",
            "medidores": [{
                "nro_medidor": "003001",
                "lectura_anterior": 80,
                "lectura_actual": None,
                "estado_lectura": "SIN_ACCESO",
                "novedad": "CASA_CERRADA",
                "registrado_por": "LECTOR",
            }],
        },
    }

    pagina._al_recibir_datos((config, "2026-10", documentos))

    assert not hasattr(pagina, "btn_filtro_sin_acceso")
    assert pagina.btn_filtro_todos.text() == "Todos (3)"
    assert pagina.btn_filtro_faltan.text() == "Faltan (2)"
    assert (
        int(pagina.btn_filtro_todos.text().split("(")[1][:-1])
        == int(pagina.btn_filtro_faltan.text().split("(")[1][:-1]) + 1
    )

    assert pagina.modelo_base.columnCount() == 11
    encabezados = [
        pagina.modelo_base.headerData(i, Qt.Orientation.Horizontal)
        for i in range(pagina.modelo_base.columnCount())
    ]
    assert encabezados == [
        "CONEXIÓN", "ID / DNI", "PERSONA", "SECTOR", "MEDIDOR",
        "LECT. ANTERIOR", "LECT. ACTUAL", "CONSUMO (M³)", "ESTADO",
        "OBSERVACIÓN", "NOTA",
    ]

    fila_sin_acceso = next(
        i for i, item in enumerate(pagina.lista_items_completa)
        if item["estado_lectura"] == "SIN_ACCESO"
    )
    estado_index = pagina.modelo_base.index(fila_sin_acceso, 8)
    assert pagina.modelo_base.data(estado_index) == "Sin acceso"
    assert pagina.modelo_base.data(
        estado_index, Qt.ItemDataRole.ToolTipRole) == "Sin acceso"
    assert pagina.modelo_base.obtener_item(fila_sin_acceso)["registrado_por"] == "LECTOR"
    sector_index = pagina.modelo_base.index(fila_sin_acceso, 3)
    assert pagina.modelo_base.data(
        sector_index, Qt.ItemDataRole.ToolTipRole) == "BARRIO DE LUCMANI"

    header = pagina.tabla.horizontalHeader()
    for column in (0, 1, 3, 4, 5, 6, 7, 8):
        assert header.sectionResizeMode(
            column) == QHeaderView.ResizeMode.ResizeToContents
    assert header.sectionResizeMode(2) == QHeaderView.ResizeMode.Stretch
    pagina.resize(1366, 760)
    pagina.show()
    qtbot.wait(100)
    assert sum(
        header.sectionSize(column)
        for column in range(pagina.modelo_base.columnCount())
    ) <= pagina.tabla.viewport().width()


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


def test_dialogo_abrir_mes_muestra_carga_y_no_se_cierra_antes_de_terminar(
    qtbot, servicio_mock, monkeypatch
):
    workers = []
    diag = DialogoAbrirMes(servicio_mock)
    qtbot.addWidget(diag)
    diag.show()
    diag.thread_pool = type("PoolCapturador", (), {
        "start": lambda self, worker: workers.append(worker)
    })()

    diag._ejecutar_apertura()

    assert len(workers) == 1
    assert not diag.indicador.isHidden()
    assert not diag.btn_abrir.isEnabled()
    assert not diag.btn_cancelar.isEnabled()
    assert diag.isVisible()

    workers[0].run()

    assert diag.result() == QMessageBox.DialogCode.Accepted
    assert diag.indicador.isHidden()


def test_dialogo_abrir_mes_mantiene_dialogo_y_restaura_controles_si_falla(
    qtbot, servicio_mock, monkeypatch
):
    workers = []
    errores = []
    diag = DialogoAbrirMes(servicio_mock)
    qtbot.addWidget(diag)
    diag.show()
    diag.thread_pool = type("PoolCapturador", (), {
        "start": lambda self, worker: workers.append(worker)
    })()
    monkeypatch.setattr(
        "ui.paginas.mes_dialogo.mostrar_dialogo_error",
        lambda *args: errores.append(args[-1]),
    )
    monkeypatch.setattr(
        servicio_mock, "abrir_mes",
        lambda **kwargs: (_ for _ in ()).throw(OSError("No se pudo guardar el Excel")),
    )

    diag._ejecutar_apertura()
    assert not diag.indicador.isHidden()
    workers[0].run()

    assert diag.isVisible()
    assert diag.btn_abrir.isEnabled()
    assert diag.btn_cancelar.isEnabled()
    assert diag.panel_form.isEnabled()
    assert diag.indicador.isHidden()
    assert errores == ["No se pudo guardar el Excel"]


def test_abrir_mes_refresca_lecturas_sin_abrir_dialogo_actualizar(
    qtbot, servicio_mock, monkeypatch
):
    pagina = PaginaLecturas(servicio_mock)
    qtbot.addWidget(pagina)
    refrescos = []

    class DialogoAceptado:
        def __init__(self, servicio, parent):
            pass

        def exec(self):
            return QMessageBox.DialogCode.Accepted

    monkeypatch.setattr("ui.paginas.lecturas.DialogoAbrirMes", DialogoAceptado)
    monkeypatch.setattr(
        pagina, "cargar_datos_asincrono",
        lambda **kwargs: refrescos.append(kwargs),
    )
    monkeypatch.setattr(
        pagina, "actualizar_datos",
        lambda: pytest.fail("No debe abrir el diálogo de sincronización"),
    )

    pagina._abrir_modal_mes()

    assert refrescos == [{"forzar": True}]


def test_recarga_forzada_lecturas_actualiza_padron_en_worker(
    qtbot, servicio_mock, monkeypatch
):
    servicio_mock.es_local_first = True
    servicio_mock.config["mes_actual"]["periodo"] = "2026-10"
    hilos_recarga = []

    def recargar_excel(limpiar_config=True):
        hilos_recarga.append(threading.get_ident())
        servicio_mock.mes = {
            "nuevo": {
                "nro_conexion": "000099",
                "nombre": "USUARIO NUEVO",
                "sector": "BARRIO DE CHAUPI",
                "medidores": [{"nro_medidor": "009999", "lectura_actual": None}],
            }
        }

    monkeypatch.setattr(
        servicio_mock,
        "limpiar_cache",
        recargar_excel,
    )
    pagina = PaginaLecturas(servicio_mock)
    qtbot.addWidget(pagina)
    hilo_gui = threading.get_ident()

    pagina.cargar_datos_asincrono(forzar=True)
    qtbot.waitUntil(
        lambda: (
            bool(hilos_recarga)
            and pagina.btn_actualizar.isEnabled()
            and any(fila["id_usuario"] == "nuevo" for fila in pagina.lista_items_completa)
        ),
        timeout=5000,
    )

    assert len(hilos_recarga) == 1
    assert hilos_recarga[0] != hilo_gui


def test_dialogo_sugiere_mes_actual_si_la_ultima_base_es_antigua(
    qtbot, servicio_mock, monkeypatch
):
    monkeypatch.setattr("servicios.datos.obtener_periodo_actual", lambda: "2026-10")
    servicio_mock.config["mes_actual"] = {
        "periodo": "2026-08",
        "estado": "CERRADO",
    }
    servicio_mock.mes = {
        "usuario": {"medidores": [{"estado_lectura": "LEIDO"}]}
    }
    diag = DialogoAbrirMes(servicio_mock)
    qtbot.addWidget(diag)

    assert diag.input_periodo.text() == "2026-10"
    assert diag.btn_abrir.isEnabled() is True


def test_pagina_lecturas_habilita_abrir_mes_si_cerrado_y_todo_leido(
    qtbot, servicio_mock, monkeypatch
):
    monkeypatch.setattr("servicios.datos.obtener_periodo_actual", lambda: "2026-09")
    servicio_mock.config["mes_actual"] = {
        "periodo": "2026-08",
        "estado": "CERRADO",
    }
    servicio_mock.mes = {
        "70112233": {
            "medidores": [{"estado_lectura": "LEIDO"}],
        },
    }
    pagina = PaginaLecturas(servicio_mock)
    qtbot.addWidget(pagina)

    pagina._al_recibir_datos((
        servicio_mock.config,
        "2026-08",
        servicio_mock.mes,
    ))

    assert pagina.btn_abrir_mes.isEnabled() is True

    servicio_mock.mes["70112233"]["medidores"][0]["estado_lectura"] = "PENDIENTE"
    pagina._al_recibir_datos((
        servicio_mock.config,
        "2026-08",
        servicio_mock.mes,
    ))
    assert pagina.btn_abrir_mes.isEnabled() is False


def test_pagina_lecturas_btn_actualizar_excel(qtbot, servicio_mock):
    pagina = PaginaLecturas(servicio_mock)
    qtbot.addWidget(pagina)

    assert hasattr(pagina, "btn_actualizar_excel")
    assert pagina.btn_actualizar_excel.text() == "Actualizar Excel"
    assert pagina.btn_actualizar_excel.property("activo") == "false"
    assert pagina.btn_actualizar_excel.property("class") == "filtro_btn_excel"

    # Clic en el botón
    pagina.btn_actualizar_excel.click()
    assert pagina.btn_actualizar_excel.property("activo") == "true"

    qtbot.waitUntil(lambda: pagina.btn_actualizar_excel.isEnabled() is True, timeout=2000)
    assert pagina.btn_actualizar_excel.text() == "Actualizar Excel"

    # Al cambiar de filtro, se desactiva
    pagina._seleccionar_filtro_estado("faltan")
    assert pagina.btn_actualizar_excel.property("activo") == "false"

