"""
tests/test_respaldo_contingencia.py — Pruebas unitarias de la Fase 6:
Respaldo en Excel, script de restauración, cola offline y modo contingencia.
"""
from __future__ import annotations
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

import respaldo_excel
import respaldo
from scripts.restaurar_excel import restaurar_datos
from servicios.cola_offline import (
    cargar_cola,
    guardar_cola,
    encolar_cambio,
    cantidad_pendientes,
    sincronizar_cola,
)
from servicios.datos_contingencia import ServicioDatosContingencia


# ---------------------------------------------------------------------------
# Fixtures y Datos de Prueba
# ---------------------------------------------------------------------------

@pytest.fixture
def datos_prueba():
    config = {
        "mes_actual": {
            "periodo": "2026-10",
            "estado": "ABIERTO",
            "fecha_emision": "2026-10-01",
            "fecha_vencimiento": "2026-10-25",
        },
        "ultimo_recibo": 4200,
        "sectores": ["CENTRO", "ALTO", "BAJO"],
        "categorias": {
            "A": {"nombre": "Doméstico", "cargo_fijo": 1.5, "tarifa_desague": 0.0},
            "B": {"nombre": "Comercial", "cargo_fijo": 3.0, "tarifa_desague": 0.5},
        },
    }

    usuarios = {
        "30770349": {
            "id_usuario": "30770349",
            "nro_conexion": "000101",
            "nombre": "MONTALVO TORRES, MANUELA",
            "sector": "CENTRO",
            "direccion": "JR. LIMA 123",
            "codigo_categoria": "A",
            "activo": True,
            "medidores": ["MED-01", "MED-02"],
        },
        "41829304": {
            "id_usuario": "41829304",
            "nro_conexion": "000102",
            "nombre": "QUISPE MAMANI, JUAN",
            "sector": "ALTO",
            "direccion": "CALLE SAN MARTIN 45",
            "codigo_categoria": "A",
            "activo": True,
            "medidores": ["MED-03"],
        },
        "SD-001": {
            "id_usuario": "SD-001",
            "nro_conexion": "000103",
            "nombre": "RAMIREZ LOPEZ, ROSA",
            "sector": "BAJO",
            "direccion": "AV. PROGRESO S/N",
            "codigo_categoria": "B",
            "activo": True,
            "medidores": ["MED-04"],
        },
    }

    mes_docs = {
        "30770349": {
            "id_usuario": "30770349",
            "nro_conexion": "000101",
            "nombre": "MONTALVO TORRES, MANUELA",
            "sector": "CENTRO",
            "direccion": "JR. LIMA 123",
            "codigo_categoria": "A",
            "medidores": [
                {
                    "nro_medidor": "MED-01",
                    "lectura_anterior": 100,
                    "lectura_actual": 115,
                    "fecha_lectura": "2026-10-05",
                    "novedad": "NORMAL",
                    "nota": "Sin novedad",
                    "fecha_anterior": "2026-09-05",
                    "consumo_anterior": 14,
                    "estado_lectura": "LEIDO",
                    "registrado_por": "ADMIN",
                },
                {
                    "nro_medidor": "MED-02",
                    "lectura_anterior": 50,
                    "lectura_actual": 58,
                    "fecha_lectura": "2026-10-05",
                    "novedad": "NORMAL",
                    "nota": "Segundo medidor",
                    "fecha_anterior": "2026-09-05",
                    "consumo_anterior": 8,
                    "estado_lectura": "LEIDO",
                    "registrado_por": "ADMIN",
                },
            ],
            "historial_m3": [10.0, 12.0, 14.0],
            "consumo_total_m3": 23.0,
            "nro_recibo": "004201",
            "deuda_anterior": 0.0,
            "total_a_pagar": 24.50,
            "meses_adeudados": 1,
            "monto_pagado": 24.50,
            "fecha_pago": "2026-10-10",
            "monto_agua": 23.0,
            "monto_desague": 0.0,
            "cargo_fijo": 1.5,
            "igv": 0.0,
            "redondeo": 0.0,
        },
        "41829304": {
            "id_usuario": "41829304",
            "nro_conexion": "000102",
            "nombre": "QUISPE MAMANI, JUAN",
            "sector": "ALTO",
            "direccion": "CALLE SAN MARTIN 45",
            "codigo_categoria": "A",
            "medidores": [
                {
                    "nro_medidor": "MED-03",
                    "lectura_anterior": 200,
                    "lectura_actual": 210,
                    "fecha_lectura": "2026-10-06",
                    "novedad": "NORMAL",
                    "nota": "",
                    "fecha_anterior": "2026-09-06",
                    "consumo_anterior": 10,
                    "estado_lectura": "LEIDO",
                    "registrado_por": "ADMIN",
                }
            ],
            "historial_m3": [8.0, 9.0, 10.0],
            "consumo_total_m3": 10.0,
            "nro_recibo": "004202",
            "deuda_anterior": 11.50,
            "total_a_pagar": 23.00,
            "meses_adeudados": 2,
            "monto_pagado": 0.0,
            "fecha_pago": None,
            "monto_agua": 10.0,
            "monto_desague": 0.0,
            "cargo_fijo": 1.5,
            "igv": 0.0,
            "redondeo": 0.0,
        },
        "SD-001": {
            "id_usuario": "SD-001",
            "nro_conexion": "000103",
            "nombre": "RAMIREZ LOPEZ, ROSA",
            "sector": "BAJO",
            "direccion": "AV. PROGRESO S/N",
            "codigo_categoria": "B",
            "medidores": [
                {
                    "nro_medidor": "MED-04",
                    "lectura_anterior": 30,
                    "lectura_actual": 35,
                    "fecha_lectura": "2026-10-07",
                    "novedad": "NORMAL",
                    "nota": "Comercial",
                    "fecha_anterior": "2026-09-07",
                    "consumo_anterior": 5,
                    "estado_lectura": "LEIDO",
                    "registrado_por": "ADMIN",
                }
            ],
            "historial_m3": [5.0, 5.0, 5.0],
            "consumo_total_m3": 5.0,
            "nro_recibo": "004203",
            "deuda_anterior": 0.0,
            "total_a_pagar": 10.50,
            "meses_adeudados": 1,
            "monto_pagado": 0.0,
            "fecha_pago": None,
            "monto_agua": 7.0,
            "monto_desague": 0.5,
            "cargo_fijo": 3.0,
            "igv": 0.0,
            "redondeo": 0.0,
        },
    }

    return {"config": config, "usuarios": usuarios, "mes_docs": mes_docs}


# ---------------------------------------------------------------------------
# 1. Pruebas de Respaldo Excel (Roundtrip e Integridad)
# ---------------------------------------------------------------------------

def test_generar_y_leer_respaldo_excel_roundtrip(tmp_path, datos_prueba):
    """Verifica que el respaldo exportado a Excel se lea reconstruyendo exactamente los datos."""
    ruta_archivo = tmp_path / "RESPALDO_2026-10.xlsx"

    # Generar Excel
    ruta_res = respaldo_excel.generar_respaldo_excel(
        config=datos_prueba["config"],
        usuarios=datos_prueba["usuarios"],
        mes_docs=datos_prueba["mes_docs"],
        periodo="2026-10",
        ruta_archivo=ruta_archivo,
    )
    assert ruta_res.exists()

    # Leer Excel
    leido = respaldo_excel.leer_respaldo_excel(ruta_archivo)

    # 1. Metadatos y validación
    assert leido["periodo"] == "2026-10"
    assert leido["validacion"]["coincide"] is True
    assert leido["validacion"]["total_docs_obtenido"] == 3
    assert abs(leido["validacion"]["suma_obtenida"] - 58.00) < 0.01

    # 2. Configuración
    assert leido["config"]["ultimo_recibo"] == 4200
    assert "CENTRO" in leido["config"]["sectores"]

    # 3. Padrón de usuarios
    assert len(leido["usuarios"]) == 3
    u_multi = leido["usuarios"]["30770349"]
    assert u_multi["nombre"] == "MONTALVO TORRES, MANUELA"
    assert "MED-01" in u_multi["medidores"]
    assert "MED-02" in u_multi["medidores"]
    assert leido["usuarios"]["SD-001"]["codigo_categoria"] == "B"

    # 4. Documentos del mes (incluyendo usuario con múltiples medidores)
    doc_multi = leido["mes_docs"]["30770349"]
    assert len(doc_multi["medidores"]) == 2
    assert doc_multi["medidores"][0]["nro_medidor"] == "MED-01"
    assert doc_multi["medidores"][0]["lectura_actual"] == 115
    assert doc_multi["medidores"][1]["nro_medidor"] == "MED-02"
    assert doc_multi["medidores"][1]["lectura_actual"] == 58
    assert doc_multi["total_a_pagar"] == 24.50
    assert doc_multi["monto_pagado"] == 24.50
    assert doc_multi["fecha_pago"] == "2026-10-10"


# ---------------------------------------------------------------------------
# 2. Pruebas de Script de Restauración (Simulación y Opciones)
# ---------------------------------------------------------------------------

def test_restaurar_datos_simulacion(datos_prueba):
    """Verifica que restaurar_datos en modo simular no altere la base y reporte conteos exactos."""
    datos_completos = {
        "periodo": "2026-10",
        "config": datos_prueba["config"],
        "usuarios": datos_prueba["usuarios"],
        "mes_docs": datos_prueba["mes_docs"],
    }

    # Simulación completa
    res = restaurar_datos(datos_completos, db_firestore=None, simular=True)
    assert res["simulacion"] is True
    assert res["config_escrito"] is True
    assert res["usuarios_nuevos"] == 3
    assert res["mes_docs_nuevos"] == 3
    assert res["suma_total_restaurada"] == 58.00

    # Solo configuración
    res_cfg = restaurar_datos(datos_completos, db_firestore=None, solo_seccion="config", simular=True)
    assert res_cfg["config_escrito"] is True
    assert res_cfg["usuarios_nuevos"] == 0
    assert res_cfg["mes_docs_nuevos"] == 0

    # Solo usuarios
    res_usr = restaurar_datos(datos_completos, db_firestore=None, solo_seccion="usuarios", simular=True)
    assert res_usr["config_escrito"] is False
    assert res_usr["usuarios_nuevos"] == 3
    assert res_usr["mes_docs_nuevos"] == 0

    # Solo mes
    res_mes = restaurar_datos(datos_completos, db_firestore=None, solo_seccion="mes", simular=True)
    assert res_mes["config_escrito"] is False
    assert res_mes["usuarios_nuevos"] == 0
    assert res_mes["mes_docs_nuevos"] == 3
    assert res_mes["suma_total_restaurada"] == 58.00

    # Opción inválida
    with pytest.raises(ValueError, match="Opción --solo inválida"):
        restaurar_datos(datos_completos, solo_seccion="invalida", simular=True)


# ---------------------------------------------------------------------------
# 3. Pruebas de Cola Offline (Encolar, Persistir y Sincronizar)
# ---------------------------------------------------------------------------

def test_cola_offline_flujo_completo(tmp_path):
    """Verifica el encolado de operaciones en disco y la sincronización con el servicio remoto."""
    ruta_cola_tmp = tmp_path / "cola_pendiente.json"

    with patch("servicios.cola_offline._ruta_cola", return_value=ruta_cola_tmp):
        # 1. Cola inicialmente vacía
        assert cantidad_pendientes() == 0

        # 2. Encolar cobro, anulación y lectura
        evt1 = encolar_cambio("pago", {
            "periodo": "2026-10",
            "id_usuario": "41829304",
            "monto_pagado": 23.00,
            "fecha_pago": "2026-10-13",
        })
        evt2 = encolar_cambio("anular_pago", {
            "periodo": "2026-10",
            "id_usuario": "30770349",
        })
        evt3 = encolar_cambio("lectura", {
            "periodo": "2026-10",
            "id_usuario": "SD-001",
            "nro_medidor": "MED-04",
            "lectura_actual": 40,
        })

        assert cantidad_pendientes() == 3
        items = cargar_cola()
        assert len(items) == 3
        assert items[0]["tipo"] == "pago"
        assert items[1]["tipo"] == "anular_pago"
        assert items[2]["tipo"] == "lectura"

        # 3. Sincronización exitosa con servicio remoto simulado
        servicio_remoto = MagicMock()
        resultado = sincronizar_cola(servicio_remoto)

        assert resultado["enviados"] == 3
        assert resultado["fallidos"] == 0
        assert resultado["pendientes"] == 0
        assert cantidad_pendientes() == 0

        servicio_remoto.registrar_pago.assert_called_once_with(
            periodo="2026-10",
            id_usuario="41829304",
            monto_pagado=23.00,
            fecha_pago="2026-10-13",
        )
        servicio_remoto.anular_pago.assert_called_once_with(
            periodo="2026-10",
            id_usuario="30770349",
        )
        servicio_remoto.guardar_lectura_medidor.assert_called_once()


def test_cola_offline_reintento_ante_fallo(tmp_path):
    """Verifica que si la sincronización remota falla, los elementos se conserven incrementando reintentos."""
    ruta_cola_tmp = tmp_path / "cola_pendiente.json"

    with patch("servicios.cola_offline._ruta_cola", return_value=ruta_cola_tmp):
        encolar_cambio("pago", {
            "periodo": "2026-10",
            "id_usuario": "41829304",
            "monto_pagado": 10.0,
        })

        servicio_remoto = MagicMock()
        servicio_remoto.registrar_pago.side_effect = ConnectionError("Sin internet")

        resultado = sincronizar_cola(servicio_remoto)
        assert resultado["enviados"] == 0
        assert resultado["fallidos"] == 1
        assert resultado["pendientes"] == 1
        assert cantidad_pendientes() == 1

        items = cargar_cola()
        assert items[0]["reintentos"] == 1
        assert "Sin internet" in items[0]["ultimo_error"]


# ---------------------------------------------------------------------------
# 4. Pruebas de ServicioDatosContingencia
# ---------------------------------------------------------------------------

def test_servicio_datos_contingencia(tmp_path, datos_prueba):
    """Verifica que el servicio de contingencia cargue datos desde el Excel de respaldo y encole cambios."""
    ruta_excel = tmp_path / "RESPALDO_2026-10.xlsx"
    ruta_cola = tmp_path / "cola_pendiente.json"

    respaldo_excel.generar_respaldo_excel(
        config=datos_prueba["config"],
        usuarios=datos_prueba["usuarios"],
        mes_docs=datos_prueba["mes_docs"],
        periodo="2026-10",
        ruta_archivo=ruta_excel,
    )

    with patch("servicios.cola_offline._ruta_cola", return_value=ruta_cola):
        servicio = ServicioDatosContingencia(ruta_archivo_excel=ruta_excel)
        assert servicio.es_contingencia is True

        # Consultas de lectura
        cfg = servicio.cargar_config()
        assert cfg["ultimo_recibo"] == 4200

        usrs = servicio.cargar_usuarios()
        assert len(usrs) == 3

        usr = servicio.obtener_usuario("30770349")
        assert usr["nombre"] == "MONTALVO TORRES, MANUELA"

        # Siguiente ID SD y conexión
        assert servicio.obtener_siguiente_id_sd() == "SD-002"
        assert servicio.obtener_siguiente_conexion_libre() == "000104"

        # Registrar pago fuera de línea
        res_pago = servicio.registrar_pago("2026-10", "41829304", 23.00, "2026-10-13")
        assert res_pago["monto_pagado"] == 23.00
        assert res_pago["fecha_pago"] == "2026-10-13"

        # Verificar que se encoló
        cola = cargar_cola()
        assert len(cola) == 1
        assert cola[0]["tipo"] == "pago"
        assert cola[0]["payload"]["id_usuario"] == "41829304"

        # Anular pago fuera de línea
        servicio.anular_pago("2026-10", "41829304")
        doc_usr = servicio.mes.get("41829304")
        assert doc_usr["monto_pagado"] == 0.0
        assert doc_usr["fecha_pago"] is None
        assert len(cargar_cola()) == 2

        # Guardar lectura fuera de línea
        servicio.guardar_lectura_medidor(
            periodo="2026-10",
            id_usuario="SD-001",
            nro_medidor="MED-04",
            lectura_actual=45,
            novedad="NORMAL",
        )
        assert len(cargar_cola()) == 3

        # Operaciones restringidas en contingencia
        with pytest.raises(RuntimeError, match="No se permite abrir mes"):
            servicio.abrir_mes("2026-11")

        with pytest.raises(RuntimeError, match="No se pueden gestionar lectores"):
            servicio.crear_lector("lector@test.com", "pass", "Juan")

        puede_abrir, motivo, _ = servicio.verificar_puede_abrir_mes()
        assert puede_abrir is False
        assert "Contingencia" in motivo


# ---------------------------------------------------------------------------
# 5. Pruebas de Rotación de Historial y Metadatos de Respaldo
# ---------------------------------------------------------------------------

def test_rotacion_historial_respaldos(tmp_path):
    """Verifica que la rotación conserve únicamente hasta 30 archivos en el historial."""
    dir_hist = tmp_path / "historial"
    dir_hist.mkdir()

    # Crear 35 archivos simulando días anteriores
    for i in range(1, 36):
        p = dir_hist / f"RESPALDO_2026-10_2026-10-{i:02d}.xlsx"
        p.write_text("dummy")

    archivos_antes = list(dir_hist.glob("RESPALDO_*.xlsx"))
    assert len(archivos_antes) == 35

    # Rotar conservando máximo 30
    respaldo.rotar_historial(dir_hist, max_archivos=30)

    archivos_despues = list(dir_hist.glob("RESPALDO_*.xlsx"))
    assert len(archivos_despues) == 30
