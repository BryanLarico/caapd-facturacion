from typing import Any, Dict
import pytest
from PySide6.QtWidgets import QMessageBox

from servicios.datos_padron import ServicioDatosPadron
from ui.paginas.lecturas_dialogo import DialogoLectura


@pytest.fixture(autouse=True)
def mock_message_boxes(monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)


def test_guardar_lectura_recalcula_fila_completa(monkeypatch):
    servicio = ServicioDatosPadron.__new__(ServicioDatosPadron)
    servicio.periodo = "2026-10"
    servicio.base_dir = None
    servicio.config = {
        "mes_actual": {"periodo": "2026-10", "estado": "ABIERTO"},
        "ultimo_recibo": 100,
        "categorias": {
            "A": {
                "nombre": "Doméstico",
                "cargo_fijo": 2.0,
                "tarifa_desague": 0.0,
                "modo_rangos": "unico",
                "rangos": [
                    {"m3_desde": 0, "m3_hasta": 10, "precio_m3": 1.0},
                    {"m3_desde": 10, "m3_hasta": 20, "precio_m3": 2.0},
                    {"m3_desde": 20, "m3_hasta": None, "precio_m3": 3.0},
                ],
            }
        },
    }

    # Inicialmente anterior 10, actual 20 -> consumo 10 m3
    # Precio para 10 m3: 10 * 1.0 = 10.0 + cargo_fijo 2.0 = 12.0
    doc_u1 = {
        "id_usuario": "12345678",
        "nro_conexion": "1",
        "nombre": "JUAN PEREZ",
        "sector": "BARRIO DE LUCMANI",
        "codigo_categoria": "A",
        "deuda_anterior": 0.0,
        "consumo_total_m3": 10.0,
        "monto_agua": 10.0,
        "cargo_fijo": 2.0,
        "deuda_actual": 12.0,
        "total_a_pagar": 12.0,
        "pago": "NO",
        "monto_pagado": 0.0,
        "medidores": [
            {
                "nro_medidor": "M-001",
                "lectura_anterior": 10,
                "lectura_actual": 20,
                "estado_lectura": "LEIDO",
                "novedad": "NORMAL",
            }
        ],
    }

    servicio.mes = {"12345678": doc_u1}
    servicio.meses_encontrados = {"2026-10": servicio.mes}

    guardados = []
    monkeypatch.setattr(servicio, "guardar_en_respaldo_local", lambda p=None: guardados.append(p))
    monkeypatch.setattr(servicio, "_contar_op", lambda *args, **kwargs: None)

    # Modificar a lectura_actual = 28 (consumo pasa de 10 a 18 m3)
    # Categoría A para 18 m3: modo unico -> rango 10-20 -> precio_m3 = 2.0 -> agua: 18 * 2.0 = 36.0 + cargo 2.0 = 38.0
    res = servicio.guardar_lectura_medidor(
        periodo="2026-10",
        id_usuario="12345678",
        nro_medidor="M-001",
        lectura_actual=28,
        lectura_anterior=10,
    )

    assert res["consumo_total_m3"] == 18.0
    assert doc_u1["consumo_total_m3"] == 18.0
    assert doc_u1["monto_agua"] == 36.0
    assert doc_u1["cargo_fijo"] == 2.0
    assert doc_u1["deuda_actual"] == 38.0
    assert doc_u1["total_a_pagar"] == 38.0
    assert len(guardados) >= 1

    # Ahora modificar también lectura_anterior a 18 (consumo pasa a 28 - 18 = 10 m3)
    res2 = servicio.guardar_lectura_medidor(
        periodo="2026-10",
        id_usuario="12345678",
        nro_medidor="M-001",
        lectura_actual=28,
        lectura_anterior=18,
    )

    assert res2["consumo_total_m3"] == 10.0
    assert doc_u1["medidores"][0]["lectura_anterior"] == 18
    assert doc_u1["consumo_total_m3"] == 10.0
    assert doc_u1["monto_agua"] == 10.0
    assert doc_u1["deuda_actual"] == 12.0
    assert doc_u1["total_a_pagar"] == 12.0


def test_conciliacion_recalcula_inconsistencias(monkeypatch):
    servicio = ServicioDatosPadron.__new__(ServicioDatosPadron)
    servicio.periodo = "2026-10"
    servicio.base_dir = None
    servicio.config = {
        "mes_actual": {"periodo": "2026-10", "estado": "ABIERTO"},
        "ultimo_recibo": 200,
        "categorias": {
            "A": {
                "nombre": "Doméstico",
                "cargo_fijo": 2.0,
                "tarifa_desague": 0.0,
                "modo_rangos": "unico",
                "rangos": [
                    {"m3_desde": 0, "m3_hasta": 10, "precio_m3": 1.0},
                    {"m3_desde": 10, "m3_hasta": None, "precio_m3": 2.0},
                ],
            }
        },
    }

    # Fila inconsistente (como si alguien hubiera editado la celda de Excel a mano)
    # Lectura anterior 10, lectura actual 30 -> consumo real es 20 m3.
    # Pero las celdas tenían consumo grabado = 10 y total_a_pagar = 12.0
    doc_inconsistente = {
        "id_usuario": "87654321",
        "nro_conexion": "2",
        "nombre": "MARIA LOPEZ",
        "sector": "BARRIO DE LUCMANI",
        "codigo_categoria": "A",
        "deuda_anterior": 0.0,
        "consumo_total_m3": 10.0,  # Desfasado
        "monto_agua": 10.0,        # Desfasado
        "cargo_fijo": 2.0,
        "deuda_actual": 12.0,      # Desfasado
        "total_a_pagar": 12.0,     # Desfasado
        "pago": "NO",
        "monto_pagado": 0.0,
        "medidores": [
            {
                "nro_medidor": "M-002",
                "lectura_anterior": 10,
                "lectura_actual": 30,  # Fue editado a 30 en Excel
                "consumo": 10.0,       # Desfasado
                "estado_lectura": "LEIDO",
                "novedad": "NORMAL",
            }
        ],
    }

    servicio.mes = {"87654321": doc_inconsistente}
    servicio.meses_encontrados = {"2026-10": servicio.mes}

    guardados = []
    monkeypatch.setattr(servicio, "guardar_en_respaldo_local", lambda p=None: guardados.append(p))
    monkeypatch.setattr(servicio, "_contar_op", lambda *args, **kwargs: None)

    # Ejecutar conciliación
    res = servicio.conciliar_y_recalcular_base_datos("2026-10")

    assert res["inconsistencias_corregidas"] == 1
    assert doc_inconsistente["consumo_total_m3"] == 20.0
    # Para 20 m3 en categoría A: 20 * 2.0 = 40.0 + cargo 2.0 = 42.0
    assert doc_inconsistente["monto_agua"] == 40.0
    assert doc_inconsistente["deuda_actual"] == 42.0
    assert doc_inconsistente["total_a_pagar"] == 42.0
    assert len(guardados) >= 1

    # Si se vuelve a ejecutar sin cambios, detecta 0 inconsistencias
    res2 = servicio.conciliar_y_recalcular_base_datos("2026-10")
    assert res2["inconsistencias_corregidas"] == 0


def test_dialogo_lectura_permite_editar_anterior_y_actual(qapp, monkeypatch):
    servicio = ServicioDatosPadron.__new__(ServicioDatosPadron)
    servicio.periodo = "2026-10"

    item = {
        "id_usuario": "11111111",
        "nro_conexion": "5",
        "nombre": "CARLOS RIVERA",
        "sector": "CHAUPICERCA",
        "codigo_categoria": "A",
        "nro_medidor": "M-999",
        "lectura_anterior": 10,
        "lectura_actual": 20,
        "novedad": "NORMAL",
        "nota": "",
        "historial_m3": [10, 12, 11],
    }

    diag = DialogoLectura(
        servicio=servicio,
        periodo="2026-10",
        item=item,
        config={"observaciones": [{"codigo": "NORMAL", "texto": "Normal"}]},
    )

    # Ambos campos deben existir y tener sus valores iniciales
    assert diag.input_anterior.text() == "10"
    assert diag.input_actual.text() == "20"
    assert "10 m³" in diag.lbl_feedback_consumo.text()

    # Modificar lectura actual a 28 -> consumo debe ser 18 m3
    diag.input_actual.setText("28")
    assert "18 m³" in diag.lbl_feedback_consumo.text()

    # Modificar lectura anterior a 15 -> consumo debe ser 13 m3
    diag.input_anterior.setText("15")
    assert "13 m³" in diag.lbl_feedback_consumo.text()

    # Probar que _ejecutar_guardado llama al servicio con ambos valores
    llamadas = []
    monkeypatch.setattr(
        servicio,
        "guardar_lectura_medidor",
        lambda **kwargs: llamadas.append(kwargs) or {"ok": True},
    )

    diag._ejecutar_guardado()
    diag.thread_pool.waitForDone(3000)

    assert len(llamadas) == 1
    assert llamadas[0]["lectura_anterior"] == 15
    assert llamadas[0]["lectura_actual"] == 28

