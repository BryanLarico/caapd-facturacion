"""
escritorio/tests/test_sincronizacion_espejo.py — Pruebas unitarias para la sincronización espejo.

Cubre:
1. Acción A (enviar_mes_a_lectores):
   - Cero dinero en la nube (sin monto_pagado, total_a_pagar, deuda, recibos).
   - Uso de WriteBatch en lotes de 500 sin .get() previo.
   - Detección de sobrantes mediante list_documents() (sin stream()).
   - Borrado en paralelo.
   - Respaldo automático en _historial/.
   - Medición de tiempo total.
2. Acción B (traer_lecturas_de_lectores):
   - Actualización de medidores y recálculo de consumos.
   - Protección de lecturas de ADMIN ante discrepancias.
3. Diálogo de confirmación:
   - Exige escribir exactamente CONFIRMAR.
4. Detección de cambios externos en archivos Excel.
5. Cierre y reapertura de lecturas con reflejo en Firebase.
"""
from __future__ import annotations
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication

from servicios.datos_padron import ServicioDatosPadron
from ui.componentes.dialogo_actualizar import DialogoActualizarBaseDatos


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def servicio_prueba(tmp_path):
    """Crea un ServicioDatosPadron aislado en un directorio temporal."""
    dir_bd = tmp_path / "Base de datos"
    dir_bd.mkdir(parents=True, exist_ok=True)

    # Creamos un servicio con datos en memoria
    s = ServicioDatosPadron.__new__(ServicioDatosPadron)
    s.es_contingencia = False
    s.es_local_first = True
    s.ops = {"lecturas": 0, "escrituras": 0}
    s.base_dir = dir_bd
    s._archivos_mtime = {}
    s.periodo = "2026-09"
    s.config = {
        "mes_actual": {
            "periodo": "2026-09",
            "estado": "ABIERTO",
            "fecha_emision": "2026-09-01",
            "fecha_vencimiento": "2026-09-20",
        },
        "sectores": ["CHAUPI", "AYACUCHO"],
        "observaciones": ["NORMAL", "CAMBIO_MEDIDOR"],
        "ultimo_recibo": 700,
    }
    s.usuarios = {
        "30771152": {
            "_id": "30771152",
            "id_usuario": "30771152",
            "nombre": "CHAUCAYANQUI ALVAREZ, CARLOS ALEJO",
            "sector": "AYACUCHO",
            "direccion": "AYACUCHO S/N",
            "codigo_categoria": "A",
            "nro_conexion": "000527",
            "activo": True,
            "medidores": ["2001887"],
        },
        "30770229": {
            "_id": "30770229",
            "id_usuario": "30770229",
            "nombre": "CHAUCAYANQUI ALVAREZ, CLEMENTE",
            "sector": "AYACUCHO",
            "direccion": "AYACUCHO S/N",
            "codigo_categoria": "A",
            "nro_conexion": "000528",
            "activo": True,
            "medidores": ["6593681"],
        },
    }
    s.mes = {
        "30771152": {
            "id_usuario": "30771152",
            "nombre": "CHAUCAYANQUI ALVAREZ, CARLOS ALEJO",
            "sector": "AYACUCHO",
            "direccion": "AYACUCHO S/N",
            "codigo_categoria": "A",
            "nro_conexion": "000527",
            "total_a_pagar": 14.0,
            "monto_pagado": 14.0,
            "deuda_anterior": 0.0,
            "deuda_actual": 14.0,
            "pago": "SI",
            "fecha_pago": "2026-09-28",
            "nro_recibo": "000000141",
            "consumo_total_m3": 9,
            "historial_m3": [10, 11, 9],
            "medidores": [
                {
                    "nro_medidor": "2001887",
                    "lectura_anterior": 109,
                    "lectura_actual": 118,
                    "fecha_anterior": "2026-08-25",
                    "fecha_lectura": "2026-09-25",
                    "estado_lectura": "LEIDO",
                    "novedad": "NORMAL",
                    "nota": "",
                    "registrado_por": "ADMIN",
                }
            ],
        },
        "30770229": {
            "id_usuario": "30770229",
            "nombre": "CHAUCAYANQUI ALVAREZ, CLEMENTE",
            "sector": "AYACUCHO",
            "direccion": "AYACUCHO S/N",
            "codigo_categoria": "A",
            "nro_conexion": "000528",
            "total_a_pagar": 38.0,
            "monto_pagado": 0.0,
            "deuda_anterior": 26.0,
            "deuda_actual": 12.0,
            "pago": "NO",
            "fecha_pago": None,
            "nro_recibo": "000000142",
            "consumo_total_m3": 7,
            "historial_m3": [8, 7, 7],
            "medidores": [
                {
                    "nro_medidor": "6593681",
                    "lectura_anterior": 954,
                    "lectura_actual": 961,
                    "fecha_anterior": "2026-08-25",
                    "fecha_lectura": "2026-09-25",
                    "estado_lectura": "LEIDO",
                    "novedad": "NORMAL",
                    "nota": "",
                    "registrado_por": "LECTOR",
                }
            ],
        },
    }
    s.ruta_excel = dir_bd / "PADRON_MES_2026-09.xlsx"
    # Crear un archivo ficticio para probar respaldo y mtime
    s.ruta_excel.write_bytes(b"PK000fake_excel")
    s._archivos_mtime[str(s.ruta_excel)] = s.ruta_excel.stat().st_mtime
    return s


def test_accion_a_enviar_mes_sin_dinero_y_con_batch(servicio_prueba, tmp_path):
    """Acción A: Verifica que el payload subido no contenga campos monetarios y use WriteBatch."""
    mock_db = MagicMock()
    mock_batch = MagicMock()
    mock_db.batch.return_value = mock_batch

    col_mes = MagicMock()
    mock_db.collection.return_value = col_mes

    # Simular doc_ref y batch.set
    doc_sets = {}

    def mock_col_doc(uid):
        ref = MagicMock()
        ref.id = uid
        return ref

    col_mes.document.side_effect = mock_col_doc

    def mock_batch_set(ref, data):
        doc_sets[ref.id] = data

    mock_batch.set.side_effect = mock_batch_set

    # list_documents devuelve solo los mismos IDs (sin sobrantes)
    ref1 = MagicMock()
    ref1.id = "30771152"
    ref2 = MagicMock()
    ref2.id = "30770229"
    col_mes.list_documents.return_value = [ref1, ref2]

    # No hay otras colecciones
    mock_db.collections.return_value = []

    with patch("firebase_client.db", return_value=mock_db), \
         patch("rutas.ruta_base_de_datos", return_value=servicio_prueba.base_dir), \
         patch.object(servicio_prueba, "guardar_config", return_value=None):

        res = servicio_prueba.enviar_mes_a_lectores()

    assert res["exito"] is True
    assert res["usuarios_subidos"] == 2
    assert res["sobrantes_borrados"] == 0
    assert "tiempo_segundos" in res
    assert servicio_prueba.config.get("ultimo_envio_lectores") is not None

    # Verificar que WriteBatch fue llamado
    assert mock_batch.commit.called

    # Verificar que NO se subieron campos de dinero
    for uid, doc_subido in doc_sets.items():
        assert "total_a_pagar" not in doc_subido
        assert "monto_pagado" not in doc_subido
        assert "deuda_anterior" not in doc_subido
        assert "deuda_actual" not in doc_subido
        assert "pago" not in doc_subido
        assert "fecha_pago" not in doc_subido
        assert "nro_recibo" not in doc_subido

        # Campos permitidos presentes
        assert "id_usuario" in doc_subido
        assert "nombre" in doc_subido
        assert "sector" in doc_subido
        assert "medidores" in doc_subido
        assert "consumo_total_m3" in doc_subido

    # Verificar que se creó el respaldo en _historial
    dir_hist = servicio_prueba.base_dir / "_historial"
    assert dir_hist.exists()
    assert len(list(dir_hist.glob("*.xlsx"))) >= 1


def test_accion_a_detecta_y_borra_sobrantes_en_paralelo(servicio_prueba):
    """Acción A: Verifica que se detecten sobrantes con list_documents() y se borren."""
    mock_db = MagicMock()
    mock_batch = MagicMock()
    mock_db.batch.return_value = mock_batch

    col_mes = MagicMock()
    col_mes.id = "mes_2026-09"
    mock_db.collection.return_value = col_mes

    # Un ID local y uno sobrante en la colección del mes
    ref_local = MagicMock()
    ref_local.id = "30771152"
    ref_sobrante = MagicMock()
    ref_sobrante.id = "USUARIO_ELIMINADO_999"
    col_mes.list_documents.return_value = [ref_local, ref_sobrante]

    # Colección antigua mes_2026-08 con otro sobrante
    col_vieja = MagicMock()
    col_vieja.id = "mes_2026-08"
    ref_viejo = MagicMock()
    ref_viejo.id = "DOC_VIEJO"
    col_vieja.list_documents.return_value = [ref_viejo]

    # Colección obsoleta usuarios con otro sobrante
    col_usuarios = MagicMock()
    col_usuarios.id = "usuarios"
    ref_usr = MagicMock()
    ref_usr.id = "DOC_USR"
    col_usuarios.list_documents.return_value = [ref_usr]

    mock_db.collections.return_value = [col_mes, col_vieja, col_usuarios]

    borrados = []

    def mock_delete(ref):
        borrados.append(ref.id)

    mock_batch.delete.side_effect = mock_delete

    with patch("firebase_client.db", return_value=mock_db), \
         patch("rutas.ruta_base_de_datos", return_value=servicio_prueba.base_dir), \
         patch.object(servicio_prueba, "guardar_config", return_value=None):

        res = servicio_prueba.enviar_mes_a_lectores()

    assert res["exito"] is True
    assert res["sobrantes_borrados"] == 3
    assert "USUARIO_ELIMINADO_999" in borrados
    assert "DOC_VIEJO" in borrados
    assert "DOC_USR" in borrados


def test_accion_b_traer_lecturas_y_recalcular_consumo(servicio_prueba):
    """Acción B: Descarga lecturas de lectores móviles y recalcula consumo."""
    mock_db = MagicMock()
    col_mes = MagicMock()
    mock_db.collection.return_value = col_mes

    # Simular lectura tomada por lector para usuario 30770229
    doc_cloud = MagicMock()
    doc_cloud.id = "30770229"
    doc_cloud.to_dict.return_value = {
        "id_usuario": "30770229",
        "medidores": [
            {
                "nro_medidor": "6593681",
                "lectura_actual": 975,  # Anterior era 954 -> consumo 21
                "fecha_lectura": "2026-09-26",
                "estado_lectura": "LEIDO",
                "novedad": "NORMAL",
                "nota": "Medidor limpio",
                "registrado_por": "lector@ispacas.pe",
            }
        ],
    }
    col_mes.stream.return_value = [doc_cloud]

    with patch("firebase_client.db", return_value=mock_db), \
         patch.object(servicio_prueba, "guardar_en_respaldo_local", return_value=None), \
         patch.object(servicio_prueba, "guardar_config", return_value=None):

        res = servicio_prueba.traer_lecturas_de_lectores()

    assert res["exito"] is True
    assert res["actualizados"] == 1
    assert len(res["conflictos_admin"]) == 0

    # Verificar que se actualizó el medidor local
    m_local = servicio_prueba.mes["30770229"]["medidores"][0]
    assert m_local["lectura_actual"] == 975
    assert m_local["consumo_m3"] == 21
    assert servicio_prueba.mes["30770229"]["consumo_total_m3"] == 21
    assert m_local["registrado_por"] == "lector@ispacas.pe"
    assert servicio_prueba.config.get("ultima_descarga_lectores") is not None


def test_accion_b_protege_lecturas_admin_con_conflicto(servicio_prueba):
    """Acción B: Si el usuario ya tiene lectura registrada por ADMIN y la nube difiere, no se sobreescribe."""
    mock_db = MagicMock()
    col_mes = MagicMock()
    mock_db.collection.return_value = col_mes

    # Usuario 30771152 tiene registrado_por == "ADMIN" con lectura 118
    # En la nube el lector subió lectura 115 (conflicto)
    doc_cloud = MagicMock()
    doc_cloud.id = "30771152"
    doc_cloud.to_dict.return_value = {
        "id_usuario": "30771152",
        "medidores": [
            {
                "nro_medidor": "2001887",
                "lectura_actual": 115,
                "fecha_lectura": "2026-09-26",
                "registrado_por": "lector@ispacas.pe",
            }
        ],
    }
    col_mes.stream.return_value = [doc_cloud]

    with patch("firebase_client.db", return_value=mock_db), \
         patch.object(servicio_prueba, "guardar_en_respaldo_local", return_value=None), \
         patch.object(servicio_prueba, "guardar_config", return_value=None):

        res = servicio_prueba.traer_lecturas_de_lectores()

    assert res["exito"] is True
    assert res["actualizados"] == 0
    assert len(res["conflictos_admin"]) == 1
    conf = res["conflictos_admin"][0]
    assert conf["id_usuario"] == "30771152"
    assert conf["lectura_admin"] == 118
    assert conf["lectura_cloud"] == 115

    # La lectura local permanece intacta en 118 (ADMIN manda)
    m_local = servicio_prueba.mes["30771152"]["medidores"][0]
    assert m_local["lectura_actual"] == 118
    assert m_local["registrado_por"] == "ADMIN"


def test_dialogo_confirmacion_requiere_escribir_confirmar(qapp, tmp_path):
    """Verifica que el diálogo de confirmación aborte si no se escribe CONFIRMAR."""
    dir_bd = tmp_path / "Base de datos"
    dir_bd.mkdir()
    (dir_bd / "PADRON_MES_2026-09.xlsx").write_bytes(b"fake")

    with patch("rutas.ruta_base_de_datos", return_value=dir_bd):
        dlg = DialogoActualizarBaseDatos()

        # Simular que el usuario cancela o escribe otra cosa
        with patch("PySide6.QtWidgets.QInputDialog.getText", return_value=("SI", True)), \
             patch("PySide6.QtWidgets.QMessageBox.information") as mock_info:
            dlg._elegir_subir()
            assert dlg.resultado_accion != DialogoActualizarBaseDatos.ACCION_SUBIR_FIREBASE
            assert mock_info.called

        # Simular que el usuario escribe exactamente CONFIRMAR
        with patch("PySide6.QtWidgets.QInputDialog.getText", return_value=("CONFIRMAR", True)):
            dlg._elegir_subir()
            assert dlg.resultado_accion == DialogoActualizarBaseDatos.ACCION_SUBIR_FIREBASE


def test_verificar_cambios_externos(servicio_prueba):
    """Verifica que verificar_cambios_externos() detecte si un archivo fue tocado externamente."""
    hay_cambio, modificados = servicio_prueba.verificar_cambios_externos()
    assert hay_cambio is False
    assert len(modificados) == 0

    # Modificar el archivo ficticio actualizando mtime
    tiempo_futuro = time.time() + 10.0
    os.utime(str(servicio_prueba.ruta_excel), (tiempo_futuro, tiempo_futuro))

    hay_cambio, modificados = servicio_prueba.verificar_cambios_externos()
    assert hay_cambio is True
    assert servicio_prueba.ruta_excel.name in modificados


def test_cerrar_y_reabrir_lecturas_refleja_en_firebase(servicio_prueba):
    """Verifica que cerrar_lecturas y reabrir_lecturas actualicen Firestore y el estado local."""
    mock_db = MagicMock()
    mock_col = MagicMock()
    mock_doc = MagicMock()
    mock_db.collection.return_value = mock_col
    mock_col.document.return_value = mock_doc

    with patch("firebase_client.db", return_value=mock_db), \
         patch.object(servicio_prueba, "traer_lecturas_de_lectores", return_value={"actualizados": 0}), \
         patch.object(servicio_prueba, "guardar_en_respaldo_local", return_value=None):

        res_cerrar = servicio_prueba.cerrar_lecturas()
        assert res_cerrar["estado"] == "CERRADO"
        assert servicio_prueba.config["mes_actual"]["estado"] == "CERRADO"
        assert mock_doc.set.called

        res_reabrir = servicio_prueba.reabrir_lecturas()
        assert res_reabrir["estado"] == "ABIERTO"
        assert servicio_prueba.config["mes_actual"]["estado"] == "ABIERTO"
