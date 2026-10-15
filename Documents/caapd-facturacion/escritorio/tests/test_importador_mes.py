"""
tests/test_importador_mes.py — Pruebas de la importación mensual y padrones históricos desde Excel.
"""
import os
from unittest.mock import patch

import openpyxl
import pytest
from servicios.importador_mes import importar_mes_desde_excel, mapear_columnas


def test_importador_preserva_sin_acceso_y_registrado_por(tmp_path):
    ruta_excel = tmp_path / "lecturas.xlsx"
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append([
        "Conexión", "DNI", "Nombre", "Sector", "Medidor",
        "Lect. Anterior", "Lect. Actual", "Novedad",
    ])
    hoja.append([
        "1", "70112233", "USUARIO", "BARRIO DE LUCMANI", "1001",
        25, None, "SIN_ACCESO",
    ])
    libro.save(ruta_excel)

    with patch("firebase_client.cargar_usuarios", return_value={}), \
         patch("firebase_client.guardar_usuarios_lote"), \
         patch("firebase_client.guardar_mes_lote") as mock_guardar_mes, \
         patch("firebase_client.limpiar_cache"), \
         patch("respaldo.on_datos_cambiados"):
        importar_mes_desde_excel(ruta_excel, periodo="2026-08")

    _, usuarios_mes = mock_guardar_mes.call_args.args
    medidor = usuarios_mes["70112233"]["medidores"][0]
    assert medidor["estado_lectura"] == "SIN_ACCESO"
    assert medidor["registrado_por"] == "EXCEL_IMPORT"


@pytest.mark.parametrize(
    ("encabezado", "clave"),
    [
        ("Conexión", "conexion"),
        ("DNI", "dni"),
        ("Lectura anterior", "lectura_anterior"),
    ],
)
def test_mapear_columnas(encabezado, clave):
    assert clave in mapear_columnas([encabezado])


def test_importar_plantilla_modelo():
    """Valida que la plantilla de prueba se lea e interprete correctamente."""
    ruta_plantilla = os.path.join(os.path.dirname(__file__), "..", "datos", "PLANTILLA_IMPORTAR_MES.xlsx")
    assert os.path.exists(ruta_plantilla), f"No se encontró la plantilla en {ruta_plantilla}"

    usuarios_mock = {
        "70112233": {"_id": "70112233", "nombre": "QUISPE MAMANI, JUAN CARLOS", "nro_conexion": "000001", "medidores": ["001001"]},
        "70667788": {"_id": "70667788", "nombre": "ZAMBRANO DIAZ, ROSA", "nro_conexion": "000006", "medidores": ["006001"]},
    }

    with patch("firebase_client.cargar_usuarios", return_value=usuarios_mock), \
         patch("firebase_client.guardar_usuarios_lote") as mock_guardar_usr, \
         patch("firebase_client.guardar_mes_lote") as mock_guardar_mes, \
         patch("firebase_client.actualizar_usuario"), \
         patch("firebase_client.limpiar_cache"), \
         patch("respaldo.on_datos_cambiados"):

        res = importar_mes_desde_excel(
            ruta_excel=ruta_plantilla,
            periodo="2026-08",
            es_mes_activo=False,
        )

        assert res["periodo"] == "2026-08"
        # 6 abonados únicos en 7 filas
        assert res["usuarios_procesados"] == 6
        assert res["medidores_procesados"] == 7

        mock_guardar_mes.assert_called_once()
        periodo_call, usuarios_mes_dict = mock_guardar_mes.call_args[0]
        assert periodo_call == "2026-08"
        assert len(usuarios_mes_dict) == 6

        # Abonado con 2 medidores (filas 6 y 7 -> DNI 70667788)
        assert "70667788" in usuarios_mes_dict
        u6 = usuarios_mes_dict["70667788"]
        assert len(u6["medidores"]) == 2
        meds_nums = [m["nro_medidor"] for m in u6["medidores"]]
        assert "006001" in meds_nums and "006002" in meds_nums
        # Consumos acumulados: (52 - 40) + (20 - 15) = 12 + 5 = 17 m3
        assert u6["consumo_total_m3"] == 17

        # Abonado con cambio de medidor (fila 5 -> DNI 70556677)
        u5 = usuarios_mes_dict["70556677"]
        assert len(u5["medidores"]) == 1
        assert u5["medidores"][0]["novedad"] == "CAMBIO_MEDIDOR"
