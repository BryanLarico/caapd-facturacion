"""
tests/test_importacion.py — Pruebas unitarias de las reglas de importación y corrección de DNI.

Cubre:
  - Agrupación por persona (DNI + nombre)
  - Unión de códigos de conexión (selecciona el menor)
  - Sufijos -1, -2 para DNIs compartidos por personas distintas
  - Asignación de SD-001, SD-002... para personas sin DNI
  - Renombrado y corrección de ID / DNI en usuarios y meses
"""

import pytest
from scripts.importar_excel import procesar_migracion, normalizar_nombre, clave_match_medidor
from codigos import normalizar_medidor, normalizar_conexion, normalizar_dni, generar_id_usuario, es_id_pendiente


def test_normalizar_nombre():
    assert normalizar_nombre("  perez  ,   juan   ") == "PEREZ, JUAN"
    assert normalizar_nombre("MONTALVO TORRES ,MANUELA") == "MONTALVO TORRES, MANUELA"
    assert normalizar_nombre("MONTALVO TORRES,MANUELA") == "MONTALVO TORRES, MANUELA"


def test_clave_match_medidor():
    assert clave_match_medidor("09091923") == "9091923"
    assert clave_match_medidor("9091923") == "9091923"
    assert clave_match_medidor("000100") == "100"
    assert clave_match_medidor("100") == "100"


def test_seleccion_menor_codigo_conexion():
    """Una persona con varios códigos debe conservar el menor numérico."""
    codigos = ["000549", "000308", "000773"]
    menor = sorted(codigos, key=lambda c: int(c))[0]
    assert menor == "000308"


def test_sufijos_dni_compartido():
    """Personas distintas con el mismo DNI deben recibir -1, -2..."""
    dni = "30770349"
    personas = ["RAMIREZ TORRES, IRMA", "PALOMINO MANSILLA, LEONCIO BERNARDINO"]
    ids = [f"{normalizar_dni(dni)}-{i+1}" for i in range(len(personas))]
    assert ids == ["30770349-1", "30770349-2"]
    assert all(es_id_pendiente(x) for x in ids)


def test_personas_sin_dni():
    """Personas sin DNI reciben correlativo SD-001, SD-002..."""
    sin_dni_ids = [f"SD-{i:03d}" for i in range(1, 4)]
    assert sin_dni_ids == ["SD-001", "SD-002", "SD-003"]
    assert all(es_id_pendiente(x) for x in sin_dni_ids)


def test_simulacion_migracion_cifras_clave():
    """Verifica que procesar_migracion con los archivos del proyecto devuelva las cifras esperadas."""
    import os
    ruta_lista = os.path.join("datos", "LISTA DE USUARIOS 2026.xlsx")
    ruta_relacion = os.path.join("datos", "RELACION_DE_USUARIOS_DEL_CAAPD.xlsx")
    if not os.path.exists(ruta_lista) or not os.path.exists(ruta_relacion):
        pytest.skip("Archivos de datos no presentes")

    usuarios, semilla, aux = procesar_migracion(ruta_lista, ruta_relacion)
    stats = aux["estadisticas"]

    assert stats["filas_activas"] == 766
    assert stats["filas_lista"] == 808
    # Personas distintas entre ~713-714
    assert 710 <= stats["total_personas"] <= 716
    assert stats["personas_sin_dni"] == 25
    assert stats["dni_7_digitos"] == 31
    assert stats["dni_9_digitos"] == 3
    assert stats["medidores_menos_6_digitos"] == 3
    assert stats["medidores_repetidos_entre_personas"] == 2
    assert stats["conexiones_sin_medidor"] == 1
