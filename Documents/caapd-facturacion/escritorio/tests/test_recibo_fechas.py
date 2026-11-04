from copy import deepcopy
from datetime import date, datetime

import pytest

from servicios import generador_pdf as g
from servicios.datos_padron import ServicioDatosPadron


@pytest.mark.parametrize("periodo, fin", [
    ("2026-10", "31/10/2026"), ("2024-02", "29/02/2024"),
    ("2025-02", "28/02/2025"), ("2026-12", "31/12/2026"),
])
def test_limites_del_mes(periodo, fin):
    assert g._fechas_periodo(periodo) == (f"01/{periodo[5:]}/{periodo[:4]}", fin)


@pytest.mark.parametrize("valor", [None, "", "—", "-", "2026-02-30", "sin fecha"])
def test_fechas_ausentes_o_invalidas_usan_periodo(valor):
    doc = {"medidores": [{"fecha_anterior": valor, "fecha_lectura": valor}]}
    datos = g.preparar_datos_recibo_desde_doc(doc, {}, "2026-10")
    assert datos["medidores"][0]["fecha_anterior"] == "01/10/2026"
    assert datos["medidores"][0]["fecha_actual"] == "31/10/2026"


@pytest.mark.parametrize("anterior, actual", [
    ("2026-09-25", "2026-10-24"),
    ("25/09/2026", "24/10/2026"),
    (date(2026, 9, 25), datetime(2026, 10, 24, 12, 30)),
])
def test_conserva_fechas_reales(anterior, actual):
    doc = {"medidores": [{"fecha_anterior": anterior, "fecha_lectura": actual}]}
    datos = g.preparar_datos_recibo_desde_doc(doc, {}, "2026-10")
    assert datos["medidores"][0]["fecha_anterior"] == "25/09/2026"
    assert datos["medidores"][0]["fecha_actual"] == "24/10/2026"


def test_fecha_actual_alternativa_y_fallback_parcial():
    datos = g.preparar_datos_recibo_desde_doc(
        {"medidores": [{"fecha_actual": "2026-10-20"}]}, {}, "2026-10")
    assert datos["medidores"][0]["fecha_anterior"] == "01/10/2026"
    assert datos["medidores"][0]["fecha_actual"] == "20/10/2026"


def test_fecha_anterior_desde_mes_previo_por_numero_sin_mutar():
    servicio = ServicioDatosPadron.__new__(ServicioDatosPadron)
    servicio.meses_encontrados = {"2025-12": {"u": {"medidores": [
        {"nro_medidor": "B", "fecha_lectura": "2025-12-24"},
        {"nro_medidor": "A", "fecha_lectura": "2025-12-25"},
    ]}}}
    doc = {"historial_m3": [1], "medidores": [
        {"nro_medidor": "A"}, {"nro_medidor": "B", "fecha_anterior": "2025-12-23"},
        {"nro_medidor": "NUEVO"},
    ]}
    antes = deepcopy(doc)
    preparado = servicio._doc_para_pdf(doc, "u", "2026-01")
    assert [m.get("fecha_anterior") for m in preparado["medidores"]] == [
        "2025-12-25", "2025-12-23", None]
    assert doc == antes


@pytest.mark.parametrize("medidores", [[], [{}], [{"fecha_anterior": "—", "fecha_actual": "—"}]])
def test_pdf_sin_lecturas_dibuja_fechas_y_ciclo(tmp_path, monkeypatch, medidores):
    textos = []
    original = g._Lienzo.drawString

    def registrar(self, x, y, texto, **kwargs):
        textos.append(texto)
        return original(self, x, y, texto, **kwargs)

    monkeypatch.setattr(g._Lienzo, "drawString", registrar)
    g.generar_recibo_pdf({"periodo": "2026-10", "medidores": medidores}, tmp_path / "recibo.pdf")
    assert "01/10/2026" in textos
    assert "31/10/2026" in textos
    assert "Periodo / Ciclo del 01/10/2026 al 31/10/2026" in textos


def test_periodo_invalido_no_inventa_fechas():
    with pytest.raises(ValueError):
        g.preparar_datos_recibo_desde_doc({}, {}, "2026-13")


def test_no_toma_fecha_de_otro_mes_o_usuario():
    servicio = ServicioDatosPadron.__new__(ServicioDatosPadron)
    servicio.meses_encontrados = {
        "2026-08": {"u": {"medidores": [{"nro_medidor": "A", "fecha_lectura": "2026-08-25"}]}},
        "2026-09": {"otro": {"medidores": [{"nro_medidor": "A", "fecha_lectura": "2026-09-25"}]}},
    }
    preparado = servicio._doc_para_pdf(
        {"historial_m3": [1], "medidores": [{"nro_medidor": "A"}]}, "u", "2026-10")
    assert preparado["medidores"][0]["fecha_anterior"] is None


def test_pdf_dibuja_fechas_reales_y_ciclo(tmp_path, monkeypatch):
    textos = []
    original = g._Lienzo.drawString

    def registrar(self, x, y, texto, **kwargs):
        textos.append(texto)
        return original(self, x, y, texto, **kwargs)

    monkeypatch.setattr(g._Lienzo, "drawString", registrar)
    g.generar_recibo_pdf_para_usuario({"medidores": [{
        "nro_medidor": "A", "fecha_anterior": "2026-09-25", "fecha_lectura": "2026-10-24",
    }]}, {}, "2026-10", tmp_path / "recibo.pdf")
    assert "25/09/2026" in textos
    assert "24/10/2026" in textos
    assert "Periodo / Ciclo del 25/09/2026 al 24/10/2026" in textos
