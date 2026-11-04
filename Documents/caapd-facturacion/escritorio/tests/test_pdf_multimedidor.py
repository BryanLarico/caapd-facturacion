import pytest
from reportlab.lib.units import cm

from servicios import generador_pdf as g


def dibujar(tmp_path, monkeypatch, medidores):
    textos = []
    original = g._Lienzo.drawString

    def registrar(self, x, y, texto, **kwargs):
        textos.append((texto, x / cm, y / cm))
        return original(self, x, y, texto, **kwargs)

    monkeypatch.setattr(g._Lienzo, "drawString", registrar)
    g.generar_recibo_pdf({
        "periodo": "2026-10", "medidores": medidores,
        "consumos_historicos": {"SET": 20, "OCT": 25},
    }, tmp_path / "recibo.pdf")
    return textos


@pytest.mark.parametrize("n", [1, 2, 3, 5])
def test_filas_completas_y_bloques_sin_solapamiento(tmp_path, monkeypatch, n):
    textos = dibujar(tmp_path, monkeypatch, [
        {"nro_medidor": str(100000 + i), "lectura_anterior": 100,
         "lectura_actual": 125} for i in range(n)])
    filas = [y for texto, x, y in textos if texto in {str(100000 + i) for i in range(n)}]
    assert len(filas) == n
    if n > 1:
        assert all(0.30 <= filas[i] - filas[i + 1] <= 0.35 + 1e-8 for i in range(n - 1))
    por_texto = {t: y for t, _, y in textos}
    ciclo = next(y for t, _, y in textos if t.startswith("Periodo / Ciclo"))
    conceptos = por_texto["DESCRIPCIÓN DE CONCEPTOS"]
    deuda = next(y for t, _, y in textos if t.startswith("DEUDA ANTERIOR"))
    assert filas[-1] - ciclo >= 0.35
    assert ciclo - conceptos >= (0.69 if n == 1 else 0.449)
    assert conceptos - por_texto["SERVICIO DE AGUA"] == pytest.approx(0.4)
    assert por_texto["SERVICIO DE AGUA"] - por_texto["CARGO FIJO"] == pytest.approx(0.8)
    assert deuda - por_texto["HISTORIAL DE CONSUMO (m3)"] >= 0.44
    assert por_texto["Subtotal"] == pytest.approx(7.8)
    assert [y for t, _, y in textos if t == "TOTAL A PAGAR S/."] == pytest.approx([5.9, 1.5])
    if n == 1:
        assert por_texto["Medidor"] == pytest.approx(13.3)
        assert filas == pytest.approx([13.0])
        assert ciclo == pytest.approx(12.6)
        assert conceptos == pytest.approx(11.9)
        assert deuda == pytest.approx(10.3)


def test_ciclo_rango_cronologico_y_fallbacks(tmp_path, monkeypatch):
    textos = dibujar(tmp_path, monkeypatch, [
        {"fecha_anterior": "2026-09-30", "fecha_actual": "2026-10-24"},
        {"fecha_anterior": "2026-08-31", "fecha_lectura": "2026-10-28"},
        {"fecha_anterior": None, "fecha_actual": None},
    ])
    assert any(t == "Periodo / Ciclo del 31/08/2026 al 31/10/2026" for t, _, _ in textos)


def test_mas_de_cinco_no_omite_medidores_silenciosamente(tmp_path):
    with pytest.raises(ValueError, match="hasta 5 medidores"):
        g.generar_recibo_pdf({"medidores": [{}] * 6}, tmp_path / "invalido.pdf")
    assert not (tmp_path / "invalido.pdf").exists()
