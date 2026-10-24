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


def test_pie_de_pagina_se_actualiza_al_instante(qtbot):
    from servicios.datos_padron import ServicioDatosPadron
    from ui.ventana_principal import VentanaPrincipal
    import tempfile
    from pathlib import Path
    serv = ServicioDatosPadron(base_dir=Path(tempfile.mkdtemp()))
    ventana = VentanaPrincipal(serv)
    qtbot.addWidget(ventana)
    assert ventana.lbl_lecturas.text().startswith("Lecturas: 0")
    serv._contar_op("lecturas", 1234)
    serv._contar_op("escrituras", 2)
    qtbot.waitUntil(lambda: ventana.lbl_lecturas.text().startswith("Lecturas: 1 234"), timeout=2000)
    assert ventana.lbl_escrituras.text() == "Escrituras: 2"


def test_pie_muestra_total_exacto_de_google_cuando_esta_disponible(qtbot):
    from servicios.datos_padron import ServicioDatosPadron
    from ui.ventana_principal import VentanaPrincipal
    import tempfile
    from pathlib import Path
    serv = ServicioDatosPadron(base_dir=Path(tempfile.mkdtemp()))
    ventana = VentanaPrincipal(serv)
    qtbot.addWidget(ventana)
    ventana._timer_metricas.stop(); ventana._timer_refresco_metricas.stop()
    serv._contar_op("lecturas", 10)
    qtbot.waitUntil(lambda: ventana.lbl_lecturas.text().startswith("Lecturas: 10"), timeout=2000)
    # Llega la respuesta de Cloud Monitoring: manda el total exacto del proyecto
    ventana._metricas_nube = {"disponible": True, "lecturas": 3812, "escrituras": 847,
                              "desde_pacifico": "2026-10-24 00:00 PDT", "error": None}
    ventana._pintar_contadores_locales()
    assert ventana.lbl_lecturas.text() == "Lecturas: 3 812"
    assert ventana.lbl_escrituras.text() == "Escrituras: 847"
    assert "Solo esta PC hoy: 10 lecturas" in ventana.lbl_lecturas.toolTip()
    # Si Google no responde (sin permiso), vuelve al contador local con el motivo
    ventana._metricas_nube = {"disponible": False, "lecturas": 0, "escrituras": 0,
                              "error": "Requiere rol 'Monitoring Viewer' en Google Cloud Console"}
    ventana._pintar_contadores_locales()
    assert ventana.lbl_lecturas.text() == "Lecturas: 10 (esta PC)"
    assert "Monitoring Viewer" in ventana.lbl_lecturas.toolTip()
