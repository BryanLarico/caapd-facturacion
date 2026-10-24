"""Contador diario de operaciones Firestore: persiste, se reinicia por día y repinta el pie al instante."""
import json

import pytest

from servicios import contador_ops


@pytest.fixture(autouse=True)
def _aislar(tmp_path, monkeypatch):
    contador_ops.reiniciar_para_pruebas()
    monkeypatch.setattr(contador_ops, "_ruta_archivo", lambda: tmp_path / "ops_diarias.json")
    yield
    contador_ops.reiniciar_para_pruebas()


def test_registrar_acumula_persiste_y_notifica(tmp_path):
    avisos = []
    contador_ops.suscribir(lambda t: avisos.append(dict(t)))
    contador_ops.registrar("lecturas", 5)
    contador_ops.registrar("escrituras", 2)
    contador_ops.registrar("lecturas", 1)
    assert contador_ops.obtener() == {"lecturas": 6, "escrituras": 2}
    assert avisos[-1] == {"lecturas": 6, "escrituras": 2}
    datos = json.loads((tmp_path / "ops_diarias.json").read_text(encoding="utf-8"))
    assert datos["lecturas"] == 6 and datos["escrituras"] == 2
    assert datos["fecha"] == contador_ops.fecha_cuota_hoy()


def test_sobrevive_a_reiniciar_el_programa_y_se_reinicia_al_cambiar_de_dia(tmp_path, monkeypatch):
    contador_ops.registrar("escrituras", 7)
    # "Cerrar y abrir": nuevo estado en memoria, mismo archivo
    contador_ops.reiniciar_para_pruebas()
    assert contador_ops.obtener() == {"lecturas": 0, "escrituras": 7}
    # Cambia el día de cuota (Pacífico): vuelve a cero
    monkeypatch.setattr(contador_ops, "fecha_cuota_hoy", lambda: "2099-01-01")
    assert contador_ops.obtener() == {"lecturas": 0, "escrituras": 0}


def test_padron_y_firebase_client_alimentan_el_contador(tmp_path):
    from servicios.datos_padron import ServicioDatosPadron
    s = ServicioDatosPadron(base_dir=tmp_path)
    s._contar_op("escrituras", 3)
    import firebase_client as fb
    fb._contar("lecturas", 4)
    assert s.get_ops() == {"lecturas": 4, "escrituras": 3}
