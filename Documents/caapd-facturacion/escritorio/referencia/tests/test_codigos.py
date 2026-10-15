"""
tests/test_codigos.py — Pruebas unitarias para codigos.py.

Verifica:
  - normalizar_medidor: 100 → 000100, 3200 → 003200, 990991 → 990991, 123456 → 123456, 22392996 → 22392996
  - normalizar_conexion: 796 → 000796
  - normalizar_dni: 7654321 → 07654321, 30771072 → 30771072
  - normalizar_recibo: 58391 → 000058391
  - es_id_pendiente: '07654321-1' → True, 'SD-001' → True, '30771072' → False
  - completar_ceros
  - buscar: tabla completa de la sección 4 de CONTEXTO.md
"""

import pytest
from codigos import (
    completar_ceros,
    normalizar_medidor,
    normalizar_conexion,
    normalizar_dni,
    normalizar_recibo,
    generar_id_usuario,
    es_id_pendiente,
    buscar,
)


def test_completar_ceros():
    assert completar_ceros("100", 6) == "000100"
    assert completar_ceros(100, 6) == "000100"
    assert completar_ceros("123456", 6) == "123456"
    assert completar_ceros("22392996", 6) == "22392996"
    assert completar_ceros("ABC", 6) == "ABC"
    assert completar_ceros("", 6) == ""
    assert completar_ceros(None, 6) == ""


def test_normalizar_medidor():
    assert normalizar_medidor(100) == "000100"
    assert normalizar_medidor("3200") == "003200"
    assert normalizar_medidor(990991) == "990991"
    assert normalizar_medidor("123456") == "123456"
    assert normalizar_medidor("22392996") == "22392996"
    assert normalizar_medidor(9174) == "009174"
    assert normalizar_medidor("10085") == "010085"
    assert normalizar_medidor(3386) == "003386"


def test_normalizar_conexion():
    assert normalizar_conexion(796) == "000796"
    assert normalizar_conexion("2") == "000002"
    assert normalizar_conexion("000527") == "000527"
    assert normalizar_conexion("1234567") == "1234567"


def test_normalizar_dni():
    assert normalizar_dni(7654321) == "07654321"
    assert normalizar_dni("30771072") == "30771072"
    assert normalizar_dni("123456789") == "123456789"


def test_normalizar_recibo():
    assert normalizar_recibo(58391) == "000058391"
    assert normalizar_recibo("1") == "000000001"
    assert normalizar_recibo("123456789") == "123456789"


def test_generar_id_usuario():
    assert generar_id_usuario("7654321") == "07654321"
    assert generar_id_usuario("30771072", sufijo=1) == "30771072-1"
    assert generar_id_usuario("30771072", sufijo=2) == "30771072-2"
    assert generar_id_usuario(None, contador_sin_dni=1) == "SD-001"
    assert generar_id_usuario("", contador_sin_dni=25) == "SD-025"
    with pytest.raises(ValueError):
        generar_id_usuario(None)


def test_es_id_pendiente():
    assert es_id_pendiente("07654321-1") is True
    assert es_id_pendiente("SD-001") is True
    assert es_id_pendiente("30771072") is False
    assert es_id_pendiente("00000000") is False


# ---------------------------------------------------------------------------
# Pruebas de búsqueda inteligente (según tabla de sección 4 CONTEXTO.md)
# ---------------------------------------------------------------------------

REGISTROS_PRUEBA = [
    {
        "_id": "76807817",
        "nro_conexion": "000796",
        "nombre": "ALVAREZ CHUQUIYANQUI, MARIBEL NAYELI",
        "sector": "BARRIO DE LUCMANI",
        "medidores": ["22392996"],
    },
    {
        "_id": "07654321",
        "nro_conexion": "000100",
        "nombre": "CASTRO VERA, CARLOS",
        "sector": "BARRIO DE CHAUPI",
        "medidores": ["003386", "123456"],
    },
    {
        "_id": "07654321-1",
        "nro_conexion": "000101",
        "nombre": "QUISPE MONTALVO, JUAN",
        "sector": "BARRIO DE CHAUPI",
        "medidores": ["133860"],  # Contiene '3386' pero no es exacto '003386'
    },
    {
        "_id": "SD-001",
        "nro_conexion": "000102",
        "nombre": "MAMANI FLORES, ROSA",
        "sector": "HUAQUILLO",
        "medidores": ["009174"],
    },
]


def test_buscar_medidor_con_ceros():
    """'3386' busca medidor: primero 003386, luego los que contengan 3386."""
    res = buscar("3386", REGISTROS_PRUEBA)
    assert len(res) == 2
    # El primero debe ser el que tiene medidor exacto 003386
    assert res[0]["_id"] == "07654321"
    # El segundo es el que contiene 3386 en 133860
    assert res[1]["_id"] == "07654321-1"


def test_buscar_medidor_completo():
    """'123456' busca medidor tal cual (no agrega ceros adicionales)."""
    res = buscar("123456", REGISTROS_PRUEBA)
    assert len(res) == 1
    assert res[0]["_id"] == "07654321"


def test_buscar_conexion_con_ceros():
    """'796' busca conexion: primero 000796."""
    res = buscar("796", REGISTROS_PRUEBA)
    assert len(res) == 1
    assert res[0]["nro_conexion"] == "000796"
    assert res[0]["_id"] == "76807817"


def test_buscar_dni_con_ceros():
    """'7654321' busca DNI: primero 07654321."""
    res = buscar("7654321", REGISTROS_PRUEBA)
    assert len(res) >= 1
    assert res[0]["_id"] == "07654321"


def test_buscar_nombre_palabras_desordenadas_sin_tildes():
    """'alvarez maribel' encuentra 'ALVAREZ CHUQUIYANQUI, MARIBEL NAYELI'."""
    res1 = buscar("alvarez maribel", REGISTROS_PRUEBA)
    assert len(res1) == 1
    assert res1[0]["_id"] == "76807817"

    # En orden inverso y con tildes ficticias
    res2 = buscar("maribel álvarez", REGISTROS_PRUEBA)
    assert len(res2) == 1
    assert res2[0]["_id"] == "76807817"


def test_buscar_id_pendiente():
    """Buscar por código SD-001 o ID con guion."""
    res = buscar("SD-001", REGISTROS_PRUEBA)
    assert len(res) == 1
    assert res[0]["_id"] == "SD-001"
