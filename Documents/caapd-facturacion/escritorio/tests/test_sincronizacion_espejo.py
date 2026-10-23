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
import json
import io
import os
import subprocess
import threading
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


def test_actualizar_deuda_guarda_los_importes_en_el_padron(
    servicio_prueba, tmp_path, monkeypatch
):
    import openpyxl

    ruta_padron = tmp_path / "Base de datos" / "PADRON_MES_2026-09.xlsx"
    monkeypatch.setattr(
        "servicios.datos_padron.rutas.ruta_base_de_datos",
        lambda nombre: ruta_padron,
    )

    doc = servicio_prueba.actualizar_deuda(
        "2026-09", "30770229", "deuda_actual", 9.5
    )
    assert doc["deuda_anterior"] == 26.0
    assert doc["deuda_actual"] == 9.5
    assert doc["total_a_pagar"] == 35.5
    assert ruta_padron.exists()

    wb = openpyxl.load_workbook(ruta_padron, read_only=True, data_only=True)
    try:
        ws = wb["AYACUCHO"]
        fila = next(
            row
            for row in ws.iter_rows(min_row=4, values_only=True)
            if str(row[1]).zfill(6) == "000528"
        )
        assert fila[11] == 26.0
        assert fila[12] == 9.5
    finally:
        wb.close()


def test_guardar_en_respaldo_local_solo_genera_padron_en_base_de_datos(
    tmp_path, monkeypatch
):
    servicio = ServicioDatosPadron.__new__(ServicioDatosPadron)
    servicio.periodo = "2026-10"
    servicio.config = {"mes_actual": {"periodo": "2026-10"}}
    servicio.usuarios = {}
    servicio.mes = {}
    servicio._archivos_mtime = {}

    ruta_padron = tmp_path / "Base de datos" / "PADRON_MES_2026-10.xlsx"
    monkeypatch.setattr(
        "servicios.datos_padron.rutas.ruta_base_de_datos",
        lambda nombre: ruta_padron,
    )
    monkeypatch.setattr(
        "servicios.datos_padron.rutas.ruta_respaldos",
        lambda *args: pytest.fail("No debe generarse un archivo redundante en Respaldos"),
    )

    def generar_padron(**kwargs):
        ruta = kwargs["ruta_archivo"]
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(b"padron")
        return ruta

    monkeypatch.setattr(
        "servicios.datos_padron.respaldo_excel.generar_respaldo_excel",
        generar_padron,
    )

    resultado = servicio.guardar_en_respaldo_local()

    assert resultado == ruta_padron
    assert servicio.ruta_excel == ruta_padron
    assert ruta_padron.exists()
    assert str(ruta_padron) in servicio._archivos_mtime


def test_cargar_padron_desde_excel_no_sobrescribe_archivo_origen(servicio_prueba):
    datos_excel = {
        "usuarios": servicio_prueba.usuarios,
        "mes_docs": servicio_prueba.mes,
        "periodo": "2026-09",
        "config": {},
    }
    with patch.object(
        servicio_prueba, "_extraer_datos_archivo_excel", return_value=datos_excel
    ), patch.object(
        servicio_prueba,
        "guardar_en_respaldo_local",
        side_effect=AssertionError("La carga no debe sobrescribir el Excel"),
    ) as guardar_excel:
        resultado = servicio_prueba.cargar_desde_carpeta_base_datos(
            dir_bd=servicio_prueba.base_dir
        )

    assert resultado["exito"] is True
    guardar_excel.assert_not_called()


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


def test_publicar_mes_actual_solo_crea_mes_nuevo_y_preserva_periodos(servicio_prueba):
    mock_db = MagicMock()
    batch = MagicMock()
    mock_db.batch.return_value = batch

    col_mes = MagicMock()
    config_ref = MagicMock()
    config_snapshot = MagicMock()
    config_snapshot.to_dict.return_value = {
        "mes_actual": {"periodo": "2026-08", "estado": "CERRADO"},
        "periodos_disponibles": ["2026-07", "2026-08"],
        "sectores": ["AYACUCHO"],
    }
    config_ref.get.return_value = config_snapshot

    def obtener_coleccion(nombre):
        if nombre == "mes_2026-09":
            return col_mes
        if nombre == "config":
            config_collection = MagicMock()
            config_collection.document.return_value = config_ref
            return config_collection
        pytest.fail(f"No debía acceder a la colección {nombre}")

    mock_db.collection.side_effect = obtener_coleccion

    with patch("firebase_client.db", return_value=mock_db):
        resultado = servicio_prueba.publicar_mes_actual_a_lectores()

    assert resultado["exito"] is True
    assert resultado["periodo"] == "2026-09"
    assert resultado["usuarios_subidos"] == len(servicio_prueba.mes)
    assert batch.create.call_count == len(servicio_prueba.mes)
    payload = batch.create.call_args_list[0].args[1]
    medidor = payload["medidores"][0]
    assert payload["id_usuario"] == "30771152"
    assert payload["codigo_categoria"] == "A"
    assert payload["direccion"] == "AYACUCHO S/N"
    assert payload["consumo_total_m3"] == 9
    assert payload["historial_m3"] == [10, 11, 9]
    assert medidor["lectura_actual"] == 118
    assert medidor["lectura_anterior"] == 109
    assert medidor["nro_medidor"] == "2001887"
    assert batch.set.call_args.args[0] is config_ref
    datos_config = batch.set.call_args.args[1]
    assert datos_config["mes_actual"]["periodo"] == "2026-09"
    assert datos_config["periodos_disponibles"] == ["2026-07", "2026-08", "2026-09"]
    batch.commit.assert_called_once()
    mock_db.collections.assert_not_called()
    batch.delete.assert_not_called()


def test_publicar_mes_actual_se_detiene_si_ya_hay_documentos(servicio_prueba):
    mock_db = MagicMock()
    col_mes = MagicMock()
    col_mes.list_documents.return_value = [MagicMock()]
    mock_db.collection.return_value = col_mes

    with patch("firebase_client.db", return_value=mock_db):
        with pytest.raises(ValueError, match="ya contiene documentos"):
            servicio_prueba.publicar_mes_actual_a_lectores()

    mock_db.batch.assert_not_called()
    mock_db.collections.assert_not_called()


def test_publicar_mes_actual_lotes_de_300_con_786_usuarios(servicio_prueba):
    mock_db = MagicMock()
    batches_creados = []

    def crear_batch():
        b = MagicMock()
        batches_creados.append(b)
        return b

    mock_db.batch.side_effect = crear_batch

    col_mes = MagicMock()
    config_ref = MagicMock()
    config_snapshot = MagicMock()
    config_snapshot.to_dict.return_value = {
        "mes_actual": {"periodo": "2026-08", "estado": "CERRADO"},
        "periodos_disponibles": ["2026-08"],
    }
    config_ref.get.return_value = config_snapshot

    def obtener_coleccion(nombre):
        if nombre == "mes_2026-09":
            return col_mes
        if nombre == "config":
            c = MagicMock()
            c.document.return_value = config_ref
            return c
        pytest.fail(f"Colección no esperada: {nombre}")

    mock_db.collection.side_effect = obtener_coleccion

    # Simulamos 786 usuarios
    servicio_prueba.mes = {
        f"USR_{i:04d}": {
            "id_usuario": f"USR_{i:04d}",
            "nombre": f"USUARIO {i}",
            "medidores": [{"nro_medidor": f"MED_{i}", "lectura_anterior": 100}],
        }
        for i in range(786)
    }

    reportes_progreso = []

    def callback_prog(pct, txt):
        reportes_progreso.append((pct, txt))

    with patch("firebase_client.db", return_value=mock_db):
        res = servicio_prueba.publicar_mes_actual_a_lectores(
            callback_progreso=callback_prog
        )

    assert res["exito"] is True
    assert res["usuarios_subidos"] == 786
    # 786 usuarios en lotes de 300 -> 3 lotes: 300, 300, 186
    assert len(batches_creados) == 3
    assert batches_creados[0].create.call_count == 300
    assert batches_creados[1].create.call_count == 300
    assert batches_creados[2].create.call_count == 186
    # El último lote debe haber configurado config_ref
    assert batches_creados[0].set.call_count == 0
    assert batches_creados[1].set.call_count == 0
    assert batches_creados[2].set.call_count == 1
    # Todos los lotes deben haber llamado commit()
    for b in batches_creados:
        b.commit.assert_called_once()
    # Verificamos que los reportes de progreso informaron los 3 lotes
    assert any("1/3" in txt for _, txt in reportes_progreso)
    assert any("2/3" in txt for _, txt in reportes_progreso)
    assert any("3/3" in txt for _, txt in reportes_progreso)
    assert reportes_progreso[-1][0] == 100



def test_accion_b_traer_lecturas_y_recalcular_consumo(servicio_prueba):
    """Acción B: Descarga lecturas de lectores móviles y recalcula consumo."""
    servicio_prueba.mes["30771152"]["medidores"][0]["lectura_actual"] = None
    docs_nube = {
        "30770229": {
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
    }

    progresos = []
    def descargar_falso(periodo, callback_progreso=None):
        if callback_progreso:
            callback_progreso(1, "1 documento(s) recibidos")
        return {"docs": docs_nube, "recibidos": 1}

    with patch.object(servicio_prueba, "_descargar_docs_en_subproceso", side_effect=descargar_falso), \
         patch.object(servicio_prueba, "_extraer_datos_archivo_excel", return_value={
             "periodo": "2026-09", "mes_docs": servicio_prueba.mes,
         }), \
         patch.object(servicio_prueba, "guardar_en_respaldo_local", return_value=None), \
         patch.object(servicio_prueba, "guardar_config", return_value=None):

        res = servicio_prueba.traer_lecturas_de_lectores(
            callback_progreso=lambda pct, texto: progresos.append((pct, texto))
        )

    assert res["exito"] is True
    assert res["documentos_descargados"] == 1
    assert res["actualizados"] == 1
    assert len(res["conflictos_admin"]) == 0

    # Verificar que se actualizó el medidor local
    m_local = servicio_prueba.mes["30770229"]["medidores"][0]
    assert m_local["lectura_actual"] == 975
    assert m_local["consumo_m3"] == 21
    assert servicio_prueba.mes["30770229"]["consumo_total_m3"] == 21
    assert m_local["registrado_por"] == "lector@ispacas.pe"
    assert servicio_prueba.config.get("ultima_descarga_lectores") is not None
    assert any("1 documento(s)" in texto for _, texto in progresos)
    assert progresos[-1][0] == 100


def test_accion_b_protege_lecturas_admin_con_conflicto(servicio_prueba):
    """Acción B: Si el usuario ya tiene lectura registrada por ADMIN y la nube difiere, no se sobreescribe."""
    servicio_prueba.mes["30770229"]["medidores"][0]["lectura_actual"] = None
    # Usuario 30771152 tiene registrado_por == "ADMIN" con lectura 118
    # En la nube el lector subió lectura 115 (conflicto)
    docs_nube = {
        "30771152": {
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
    }

    with patch.object(
        servicio_prueba,
        "_descargar_docs_en_subproceso",
        return_value={"docs": docs_nube, "recibidos": 1},
    ), \
         patch.object(servicio_prueba, "_extraer_datos_archivo_excel", return_value={
             "periodo": "2026-09", "mes_docs": servicio_prueba.mes,
         }), \
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


def test_accion_b_no_descarga_si_todas_las_lecturas_actuales_estan_completas(
    servicio_prueba,
):
    ruta_ultimo_padron = servicio_prueba.ruta_excel.with_name("PADRON_MES_2026-10.xlsx")
    ruta_ultimo_padron.write_bytes(b"PK000fake_excel")
    with patch.object(
        servicio_prueba,
        "_descargar_docs_en_subproceso",
        side_effect=AssertionError("No debe consultar Firebase"),
    ), patch.object(
        servicio_prueba,
        "_extraer_datos_archivo_excel",
        return_value={"periodo": "2026-10", "mes_docs": servicio_prueba.mes},
    ) as leer_excel, patch.object(
        servicio_prueba, "guardar_en_respaldo_local"
    ) as guardar_excel:
        resultado = servicio_prueba.traer_lecturas_de_lectores()

    leer_excel.assert_called_once_with(ruta_ultimo_padron)
    assert resultado["periodo"] == "2026-10"
    assert resultado["omitida"] is True
    assert resultado["actualizados"] == 0
    guardar_excel.assert_not_called()


def test_descarga_en_subproceso_procesa_eventos_y_limpia_temporal(
    servicio_prueba, monkeypatch
):
    resultado_esperado = {
        "exito": True,
        "docs": {"30771152": {"medidores": []}},
        "recibidos": 1,
    }

    temporales = []

    class ProcesoFalso:
        def __init__(self, comando, **kwargs):
            self.stdout = io.StringIO(
                "".join(
                    [
                        '{"t":"fase","msg":"Leyendo lecturas"}\n',
                        '{"t":"prog","n":1}\n',
                        '{"t":"fin","n":1}\n',
                    ]
                )
            )
            ruta_salida = Path(comando[comando.index("--salida") + 1])
            temporales.append(ruta_salida.parent)
            ruta_salida.write_text(json.dumps(resultado_esperado), encoding="utf-8")

        def poll(self):
            return 0

        def wait(self, timeout):
            return 0

        def kill(self):
            raise AssertionError("No se debe terminar un proceso ya finalizado")

    monkeypatch.setattr(subprocess, "Popen", ProcesoFalso)
    progresos = []

    resultado = ServicioDatosPadron._descargar_docs_en_subproceso(
        servicio_prueba,
        "2026-09",
        lambda porcentaje, texto: progresos.append((porcentaje, texto)),
    )

    assert resultado == {
        "docs": resultado_esperado["docs"],
        "recibidos": 1,
    }
    assert any("Leyendo lecturas" in texto for _, texto in progresos)
    assert any("1 documento(s)" in texto for _, texto in progresos)
    assert temporales
    assert all(not ruta.exists() for ruta in temporales)


def test_descarga_en_subproceso_timeout_limpia_y_termina_proceso(
    servicio_prueba, monkeypatch
):
    rutas_temporales = []

    class ProcesoColgado:
        def __init__(self, comando, **kwargs):
            self.evento_terminacion = threading.Event()
            self.stdout = self.SalidaBloqueante(self.evento_terminacion)
            rutas_temporales.append(Path(comando[comando.index("--salida") + 1]).parent)
            self.terminado = False

        class SalidaBloqueante:
            def __init__(self, evento_terminacion):
                self.evento_terminacion = evento_terminacion

            def __iter__(self):
                self.evento_terminacion.wait()
                if False:
                    yield ""

            def close(self):
                self.evento_terminacion.set()

        def poll(self):
            return 0 if self.terminado else None

        def wait(self, timeout):
            if not self.terminado:
                raise subprocess.TimeoutExpired("descarga", timeout)
            return 0

        def kill(self):
            self.terminado = True
            self.evento_terminacion.set()

    monkeypatch.setattr(subprocess, "Popen", ProcesoColgado)
    servicio_prueba.TIMEOUT_DESCARGA_TOTAL = 0

    with pytest.raises(TimeoutError, match="tiempo máximo"):
        ServicioDatosPadron._descargar_docs_en_subproceso(
            servicio_prueba, "2026-09", lambda *_: None
        )

    assert rutas_temporales
    assert all(not ruta.exists() for ruta in rutas_temporales)


def test_descarga_en_subproceso_no_confunde_heartbeat_con_avance(
    servicio_prueba, monkeypatch
):
    rutas_temporales = []

    class ProcesoConLatidosSinAvance:
        def __init__(self, comando, **kwargs):
            self.terminado = threading.Event()
            self.stdout = self.Salida(self.terminado)
            rutas_temporales.append(Path(comando[comando.index("--salida") + 1]).parent)

        class Salida:
            def __init__(self, terminado):
                self.terminado = terminado

            def __iter__(self):
                while not self.terminado.wait(0.005):
                    yield '{"t":"hb"}\n'

            def close(self):
                self.terminado.set()

        def poll(self):
            return 0 if self.terminado.is_set() else None

        def wait(self, timeout):
            return 0

        def kill(self):
            self.terminado.set()

    monkeypatch.setattr(subprocess, "Popen", ProcesoConLatidosSinAvance)
    servicio_prueba.TIMEOUT_DESCARGA_SIN_SENAL = 0.05
    servicio_prueba.TIMEOUT_DESCARGA_TOTAL = 2

    with pytest.raises(TimeoutError, match="no recibió avances"):
        ServicioDatosPadron._descargar_docs_en_subproceso(
            servicio_prueba, "2026-09", lambda *_: None
        )

    assert rutas_temporales
    assert all(not ruta.exists() for ruta in rutas_temporales)


def test_descarga_en_subproceso_cancela_hijo_al_cerrar_aplicacion(
    servicio_prueba, monkeypatch
):
    procesos = []

    class ProcesoCancelado:
        def __init__(self, _comando, **_kwargs):
            self.stdout = io.StringIO("")
            self.terminado = False
            procesos.append(self)

        def kill(self):
            self.terminado = True

        def wait(self, timeout):
            return -9

    monkeypatch.setattr(subprocess, "Popen", ProcesoCancelado)
    monkeypatch.setattr("servicios.cancelacion.cierre_solicitado", lambda: True)

    with pytest.raises(InterruptedError, match="aplicación se está cerrando"):
        ServicioDatosPadron._descargar_docs_en_subproceso(
            servicio_prueba, "2026-09", lambda *_: None
        )

    assert procesos and procesos[0].terminado


def test_dialogo_confirmacion_requiere_escribir_confirmar(qapp, tmp_path):
    """Verifica que el paso '¿Está seguro?' solo habilite el envío si se escribe CONFIRMAR."""
    dir_bd = tmp_path / "Base de datos"
    dir_bd.mkdir()
    (dir_bd / "PADRON_MES_2026-09.xlsx").write_bytes(b"fake")

    with patch("rutas.ruta_base_de_datos", return_value=dir_bd):
        dlg = DialogoActualizarBaseDatos()

        # Al elegir "Sobreescribe Nube" se muestra el paso 2 (¿Está seguro?) con el botón deshabilitado
        dlg._mostrar_confirmacion(DialogoActualizarBaseDatos.ACCION_SUBIR_FIREBASE)
        assert dlg.pila.currentIndex() == 1
        assert not dlg.btn_si.isEnabled()

        # Simular que el usuario escribe otra cosa: no procede y muestra error en línea
        dlg.txt_confirmar.setText("SI")
        assert not dlg.btn_si.isEnabled()
        assert dlg._elegir_subir() is False
        assert dlg.resultado_accion != DialogoActualizarBaseDatos.ACCION_SUBIR_FIREBASE
        assert not dlg.lbl_error_confirmar.isHidden()

        # Simular que el usuario escribe exactamente CONFIRMAR
        dlg.txt_confirmar.setText("CONFIRMAR")
        assert dlg.btn_si.isEnabled()
        assert dlg._elegir_subir() is True
        assert dlg.resultado_accion == DialogoActualizarBaseDatos.ACCION_SUBIR_FIREBASE

        # "Descarga Espejo" no exige palabra clave, pero sí pasa por ¿Está seguro?
        dlg2 = DialogoActualizarBaseDatos()
        dlg2._mostrar_confirmacion(DialogoActualizarBaseDatos.ACCION_DESCARGAR_FIREBASE)
        assert dlg2.pila.currentIndex() == 1
        assert dlg2.btn_si.isEnabled()
        dlg2._confirmar_accion()
        assert dlg2.resultado_accion == DialogoActualizarBaseDatos.ACCION_DESCARGAR_FIREBASE

        dlg3 = DialogoActualizarBaseDatos()
        dlg3._mostrar_confirmacion(DialogoActualizarBaseDatos.ACCION_PUBLICAR_MES_ACTUAL)
        assert dlg3.pila.currentIndex() == 1
        assert dlg3.btn_si.isEnabled()
        dlg3._confirmar_accion()
        assert dlg3.resultado_accion == DialogoActualizarBaseDatos.ACCION_PUBLICAR_MES_ACTUAL


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

def test_accion_a_sube_dos_ultimos_meses(servicio_prueba):
    """Acción A: sube el mes activo y el anterior; conserva ambas colecciones y borra las más antiguas."""
    doc_prev = {
        "id_usuario": "30771152", "nro_conexion": "000527", "nombre": "CARLOS", "sector": "AYACUCHO",
        "direccion": "S/N", "codigo_categoria": "A", "consumo_total_m3": 7, "historial_m3": [5, 6, 7],
        "medidores": [{"nro_medidor": "2001887", "lectura_anterior": 100, "lectura_actual": 107}],
        "monto_pagado": 15.0, "total_a_pagar": 15.0,  # dinero: NO debe subir
    }
    servicio_prueba.meses_encontrados = {
        "2026-07": {"30771152": dict(doc_prev)},
        "2026-08": {"30771152": dict(doc_prev)},
        "2026-09": servicio_prueba.mes,
    }
    assert servicio_prueba._periodos_para_nube() == ["2026-09", "2026-08"]

    mock_db = MagicMock()
    mock_batch = MagicMock()
    mock_db.batch.return_value = mock_batch

    colecciones = {}
    def _collection(nombre):
        if nombre not in colecciones:
            c = MagicMock(); c.id = nombre
            c.list_documents.return_value = []
            colecciones[nombre] = c
        return colecciones[nombre]
    mock_db.collection.side_effect = _collection

    col_vieja = MagicMock(); col_vieja.id = "mes_2026-07"
    ref_viejo = MagicMock(); ref_viejo.id = "DOC_VIEJO"
    col_vieja.list_documents.return_value = [ref_viejo]
    mock_db.collections.return_value = [col_vieja]

    escritos = []
    mock_batch.set.side_effect = lambda ref, data, **kw: escritos.append((ref, data))
    borrados = []
    mock_batch.delete.side_effect = lambda ref: borrados.append(ref.id)

    with patch("firebase_client.db", return_value=mock_db), \
         patch("rutas.ruta_base_de_datos", return_value=servicio_prueba.base_dir), \
         patch.object(servicio_prueba, "guardar_config", return_value=None):
        res = servicio_prueba.enviar_mes_a_lectores()

    assert res["exito"] is True
    assert res["periodo"] == "2026-09"
    assert res["periodos_subidos"] == ["2026-09", "2026-08"]
    assert res["subidos_por_periodo"]["2026-08"] == 1
    assert res["usuarios_subidos"] == len(servicio_prueba.mes) + 1
    assert "mes_2026-09" in colecciones and "mes_2026-08" in colecciones
    assert borrados == ["DOC_VIEJO"]
    assert res["sobrantes_borrados"] == 1
    for _ref, data in escritos:
        assert "monto_pagado" not in data and "total_a_pagar" not in data
    args, kwargs = colecciones["config"].document.return_value.set.call_args
    assert args[0]["periodos_disponibles"] == ["2026-09", "2026-08"]