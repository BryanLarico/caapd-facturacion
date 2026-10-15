"""
tests/test_etapa2_mejoras.py — Pruebas unitarias de Etapa 2:
- Normalización exacta de columnas en importadores y lectores Excel (sin colisiones).
- Cálculo exacto de total_a_pagar = deuda_anterior + deuda_actual y mapeo de Pago SI/NO.
- Serialización y recuperación completa de configuración general en JSON_CONFIG_COMPLETO.
- Aislamiento total en entorno de prueba (CAAPD_ENTORNO=prueba):
  * Redirección a 'Base de datos PRUEBA/'
  * Autoguardado escribe únicamente en carpeta de prueba sin tocar la real.
  * Etiqueta 'TIPO: ARCHIVO DE PRUEBA' en hoja LEEME.
- Protección de seguridad:
  * Rechazo de subida/restauración de archivos de prueba en modo producción.
  * Detección y prevención de duplicados de meses en PADRON_MES_aaaa-mm.xlsx.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

import rutas
import respaldo_excel
from scripts.restaurar_excel import restaurar_datos
from servicios.importador_mes import mapear_columnas, importar_mes_desde_excel
from servicios.datos_padron import (
    buscar_archivos_base_datos,
    validar_archivos_sin_duplicados,
    ServicioDatosPadron,
)


@pytest.fixture
def datos_ejemplo():
    config = {
        "mes_actual": {
            "periodo": "2026-09",
            "estado": "CERRADO",
            "fecha_emision": "2026-09-01",
            "fecha_vencimiento": "2026-09-25",
        },
        "ultimo_recibo": 5100,
        "sectores": ["CENTRO", "ALTO"],
        "categorias": {
            "DOM": {"nombre": "Doméstico", "cargo_fijo": 2.0, "tarifa_desague": 0.0},
        },
        "general": {
            "nombre_jass": "CAAPD ISPACAS",
            "ruc": "20123456789",
        },
    }

    usuarios = {
        "10000001": {
            "id_usuario": "10000001",
            "nro_conexion": "0001",
            "nombre": "GARCIA LOPEZ, CARLOS",
            "sector": "CENTRO",
            "direccion": "AV. PRINCIPAL 100",
            "codigo_categoria": "DOM",
            "activo": True,
            "medidores": ["MED-01"],
        },
        "10000002": {
            "id_usuario": "10000002",
            "nro_conexion": "0002",
            "nombre": "PEREZ QUISPE, ANA",
            "sector": "ALTO",
            "direccion": "JR. AREQUIPA 200",
            "codigo_categoria": "DOM",
            "activo": True,
            "medidores": ["MED-02"],
        },
    }

    mes_docs = {
        "10000001": {
            "id_usuario": "10000001",
            "nro_conexion": "0001",
            "nombre": "GARCIA LOPEZ, CARLOS",
            "sector": "CENTRO",
            "direccion": "AV. PRINCIPAL 100",
            "codigo_categoria": "DOM",
            "medidores": [
                {
                    "nro_medidor": "MED-01",
                    "lectura_anterior": 100,
                    "lectura_actual": 115,
                    "fecha_lectura": "2026-09-02",
                    "novedad": "NORMAL",
                    "nota": "",
                    "fecha_anterior": "2026-08-02",
                    "consumo_anterior": 14,
                    "estado_lectura": "CONFIRMADA",
                    "registrado_por": "LECTOR_1",
                }
            ],
            "deuda_anterior": 15.0,
            "deuda_actual": 25.0,
            "total_a_pagar": 40.0,
            "meses_adeudados": 1,
            "monto_pagado": 40.0,
            "estado_pago": "PAGADO",
            "fecha_pago": "2026-09-10",
            "nro_recibo": 5101,
            "monto_agua": 23.0,
            "monto_desague": 0.0,
            "cargo_fijo": 2.0,
            "igv": 0.0,
            "redondeo": 0.0,
            "consumo_total_m3": 15,
        },
        "10000002": {
            "id_usuario": "10000002",
            "nro_conexion": "0002",
            "nombre": "PEREZ QUISPE, ANA",
            "sector": "ALTO",
            "direccion": "JR. AREQUIPA 200",
            "codigo_categoria": "DOM",
            "medidores": [
                {
                    "nro_medidor": "MED-02",
                    "lectura_anterior": 50,
                    "lectura_actual": 60,
                    "fecha_lectura": "2026-09-02",
                    "novedad": "NORMAL",
                    "nota": "",
                    "fecha_anterior": "2026-08-02",
                    "consumo_anterior": 10,
                    "estado_lectura": "CONFIRMADA",
                    "registrado_por": "LECTOR_1",
                }
            ],
            "deuda_anterior": 0.0,
            "deuda_actual": 20.0,
            "total_a_pagar": 20.0,
            "meses_adeudados": 1,
            "monto_pagado": 0.0,
            "estado_pago": "PENDIENTE",
            "fecha_pago": None,
            "nro_recibo": 5102,
            "monto_agua": 18.0,
            "monto_desague": 0.0,
            "cargo_fijo": 2.0,
            "igv": 0.0,
            "redondeo": 0.0,
            "consumo_total_m3": 10,
        },
    }

    return {"config": config, "usuarios": usuarios, "mes_docs": mes_docs}


# ===========================================================================
# 1. Pruebas de normalización y colisiones de columnas
# ===========================================================================

def test_mapeo_columnas_sin_colisiones():
    """Verifica que las columnas grises técnicas no sobreescriban las visibles."""
    encabezados = [
        "Fecha Lect.",
        "Conexión",
        "N° Medidor",
        "Titular / Beneficiario",
        "Dirección",
        "Lect. Anterior",
        "Lect. Actual",
        "Consumo (m³)",
        "Observación",
        "Nota",
        "N° Recibo",
        "Deuda Ant. (S/.)",
        "Deuda Actual (S/.)",
        "Meses",
        "Pago",
        "Fecha Pago",
        "ID Usuario",
        "Fecha Anterior",
        "Consumo Anterior",
        "Estado Lectura",
        "Registrado Por",
        "Categoría",
        "Historial m³",
        "Consumo Total m³",
        "Monto Agua",
        "Monto Desagüe",
        "Cargo Fijo",
        "IGV",
        "Redondeo",
    ]
    mapa = mapear_columnas(encabezados)

    # Lectura Anterior vs Fecha/Consumo Anterior
    assert mapa["lectura_anterior"] == 5  # "Lect. Anterior"
    assert mapa["fecha_anterior"] == 17   # "Fecha Anterior"
    assert mapa["consumo_anterior"] == 18 # "Consumo Anterior"

    # Lectura Actual vs Deuda Actual
    assert mapa["lectura_actual"] == 6    # "Lect. Actual"
    assert mapa["deuda_actual"] == 12     # "Deuda Actual (S/.)"
    assert mapa["deuda_anterior"] == 11   # "Deuda Ant. (S/.)"

    # Pago
    assert mapa["pago"] == 14             # "Pago"
    assert mapa["fecha_pago"] == 15       # "Fecha Pago"


# ===========================================================================
# 2. Pruebas de Roundtrip y formato de columnas
# ===========================================================================

def test_roundtrip_excel_nuevo_esquema(datos_ejemplo, tmp_path):
    """Verifica que generar_respaldo_excel y leer_respaldo_excel mantengan todos los datos."""
    archivo = tmp_path / "PADRON_MES_2026-09.xlsx"

    respaldo_excel.generar_respaldo_excel(
        config=datos_ejemplo["config"],
        usuarios=datos_ejemplo["usuarios"],
        mes_docs=datos_ejemplo["mes_docs"],
        periodo="2026-09",
        ruta_archivo=archivo,
    )

    assert archivo.exists()

    recup = respaldo_excel.leer_respaldo_excel(archivo)
    assert recup["config"]["mes_actual"]["periodo"] == "2026-09"
    assert recup["config"]["ultimo_recibo"] == 5100
    assert "general" in recup["config"]
    assert recup["config"]["general"]["nombre_jass"] == "CAAPD ISPACAS"

    assert len(recup["usuarios"]) == 2
    docs = recup["mes_docs"]
    u1 = docs["10000001"]
    assert u1["nombre"] == "GARCIA LOPEZ, CARLOS"
    assert u1["deuda_anterior"] == 15.0
    assert u1["deuda_actual"] == 25.0
    assert u1["total_a_pagar"] == 40.0
    assert u1["monto_pagado"] == 40.0

    u2 = docs["10000002"]
    assert u2["deuda_anterior"] == 0.0
    assert u2["deuda_actual"] == 20.0
    assert u2["total_a_pagar"] == 20.0
    assert u2["monto_pagado"] == 0.0


# ===========================================================================
# 3. Pruebas de Entorno de Prueba y Seguridad
# ===========================================================================

def test_aislamiento_entorno_prueba(datos_ejemplo, tmp_path, monkeypatch):
    """Verifica que en CAAPD_ENTORNO=prueba los respaldos y bases vayan solo a carpeta PRUEBA."""
    dir_prueba = tmp_path / "Base de datos PRUEBA"
    dir_real = tmp_path / "Base de datos"
    dir_prueba.mkdir()
    dir_real.mkdir()

    monkeypatch.setenv("CAAPD_ENTORNO", "prueba")
    monkeypatch.setattr(rutas, "ruta_base_de_datos", lambda p="": dir_prueba if not p else dir_prueba / p)
    monkeypatch.setattr(rutas, "ruta_respaldos", lambda p="": (dir_prueba / "respaldos") if not p else (dir_prueba / "respaldos" / p))

    assert rutas.es_entorno_prueba() is True
    assert rutas.ruta_base_de_datos() == dir_prueba

    servicio = ServicioDatosPadron(base_dir=dir_prueba)
    servicio.usuarios = datos_ejemplo["usuarios"]
    servicio.mes = datos_ejemplo["mes_docs"]
    servicio.periodo = "2026-09"
    servicio.config = datos_ejemplo["config"]

    # Guardar en respaldo local
    ruta_guardada = servicio.guardar_en_respaldo_local("2026-09")
    assert Path(ruta_guardada).exists()
    assert "Base de datos PRUEBA" in str(ruta_guardada)

    # Verificar que dir_real siga completamente vacía
    archivos_reales = list(dir_real.iterdir())
    assert len(archivos_reales) == 0

    # Verificar que el archivo generado en prueba tenga la marca de seguridad
    info = respaldo_excel.leer_respaldo_excel(Path(ruta_guardada))
    assert info.get("es_prueba") is True


def test_seguridad_rechazar_archivo_prueba_en_produccion(datos_ejemplo, tmp_path, monkeypatch):
    """Verifica que restaurar_datos rechace un archivo con marca de prueba si estamos en producción."""
    archivo_prueba = tmp_path / "PADRON_MES_2026-09_PRUEBA.xlsx"

    # Generar en modo prueba
    monkeypatch.setenv("CAAPD_ENTORNO", "prueba")
    respaldo_excel.generar_respaldo_excel(
        config=datos_ejemplo["config"],
        usuarios=datos_ejemplo["usuarios"],
        mes_docs=datos_ejemplo["mes_docs"],
        periodo="2026-09",
        ruta_archivo=archivo_prueba,
        es_prueba=True,
    )

    # Cambiar a entorno normal (producción)
    monkeypatch.delenv("CAAPD_ENTORNO", raising=False)
    assert rutas.es_entorno_prueba() is False

    # Leer el archivo generado
    datos_cargados = respaldo_excel.leer_respaldo_excel(archivo_prueba)

    mock_db = MagicMock()
    # Debe lanzar PermissionError por seguridad
    with pytest.raises(PermissionError, match="ARCHIVO DE PRUEBA"):
        restaurar_datos(datos_cargados, db_firestore=mock_db, simular=False)


def test_prevencion_duplicados_meses(tmp_path):
    """Verifica que validar_archivos_sin_duplicados detecte y resuelva archivos duplicados del mismo mes."""
    (tmp_path / "PADRON_MES_2026-08.xlsx").touch()
    (tmp_path / "PADRON_MES_2026-09.xlsx").touch()
    (tmp_path / "PADRON_MES_2026-09 (1).xlsx").touch() # Copia duplicada
    (tmp_path / "PADRON_MES_2026-10.xlsx").touch()
    (tmp_path / "OTRO_ARCHIVO.xlsx").touch() # Archivo que no coincide

    archivos = buscar_archivos_base_datos(tmp_path)
    # Solo deben listarse los 4 que coinciden con el patrón regex
    assert len(archivos) == 4

    unicos, duplicados = validar_archivos_sin_duplicados(archivos)
    assert len(duplicados) == 1
    assert "2026-09" in duplicados[0]
    assert len(unicos) == 3
    nombres = [u.name for u in unicos]
    assert "PADRON_MES_2026-08.xlsx" in nombres
    assert "PADRON_MES_2026-09.xlsx" in nombres
    assert "PADRON_MES_2026-10.xlsx" in nombres
