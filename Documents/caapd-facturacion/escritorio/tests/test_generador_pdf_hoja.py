"""
tests/test_generador_pdf_hoja.py — El recibo debe quedar centrado en la hoja física 15.5 x 22 cm
con bordes blancos de 1.9 cm (laterales) y 0.5 cm (arriba/abajo).
"""
import re
from pathlib import Path

import pytest

from servicios import generador_pdf as g

CM_EN_PUNTOS = 72 / 2.54


def _datos_demo(meses: int) -> dict:
    return {
        "numero_recibo": 1234, "periodo": "2026-03",
        "fecha_emision": "01/03/2026", "ultimo_dia_pago": "20/03/2026",
        "conexion": "157", "nombre": "Juan Perez Quispe", "dni_ruc": "12345678",
        "zona": "Barrio Alto", "direccion": "Calle 5 de Agosto s/n", "categoria": "DOMESTICO",
        "medidores": [{"medidor": "M-0012", "lectura_anterior": 1200.0, "fecha_anterior": "01/02/2026",
                       "lectura_actual": 1218.0, "fecha_actual": "01/03/2026", "consumo": 18.0}],
        "servicio_agua": 12.5, "servicio_desague": 3.0, "cargo_fijo": 2.0,
        "deuda_anterior": 0.0 if meses <= 1 else 17.5 * (meses - 1),
        "meses_adeudados": meses, "igv": 0.0, "redondeo": 0.0,
        "total_a_pagar": 17.5 * meses,
        "consumos_historicos": {"OCT": 14, "NOV": 16, "DIC": None, "ENE": 20, "FEB": 15, "MAR": 18},
    }


def test_geometria_area_util_es_11_7_x_21():
    geo = g.calcular_geometria()
    assert g.ANCHO_HOJA == pytest.approx(15.5 * CM_EN_PUNTOS)
    assert g.ALTO_HOJA == pytest.approx(22.0 * CM_EN_PUNTOS)
    assert geo["ox"] == pytest.approx(1.9 * CM_EN_PUNTOS)
    assert geo["oy"] == pytest.approx(0.5 * CM_EN_PUNTOS)
    assert geo["ancho_fondo"] == pytest.approx(11.7 * CM_EN_PUNTOS)
    assert geo["alto_fondo"] == pytest.approx(21.0 * CM_EN_PUNTOS)
    # Los textos se escalan de forma uniforme por sx (no se deforman)
    assert geo["sx"] == pytest.approx(11.7 / 13.97, rel=1e-4)


def test_lienzo_proyecta_coordenadas_de_diseno():
    class _Falso:
        def __init__(self):
            self.llamadas = []

        def drawString(self, x, y, t, **kw):
            self.llamadas.append(("drawString", x, y, t))

        def setFont(self, n, s):
            self.llamadas.append(("setFont", n, s))

    falso = _Falso()
    lienzo = g._Lienzo(falso, ox=10.0, oy=20.0, sx=0.5, sy=2.0)
    lienzo.setFont("Helvetica", 8)
    lienzo.translate(2.0, 3.0)
    lienzo.drawString(4.0, 5.0, "hola")
    assert falso.llamadas[0] == ("setFont", "Helvetica", 4.0)
    assert falso.llamadas[1] == ("drawString", 10.0 + (4.0 + 2.0) * 0.5, 20.0 + (5.0 + 3.0) * 2.0, "hola")


@pytest.mark.parametrize("meses", [1, 2, 3])
def test_pdf_tiene_tamano_de_hoja_fisica(tmp_path: Path, meses: int):
    salida = tmp_path / f"recibo_{meses}.pdf"
    g.generar_recibo_pdf(_datos_demo(meses), salida)
    assert salida.exists() and salida.stat().st_size > 1000
    contenido = salida.read_bytes()
    m = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]", contenido)
    assert m, "El PDF no declara MediaBox"
    ancho_cm = float(m.group(1)) / CM_EN_PUNTOS
    alto_cm = float(m.group(2)) / CM_EN_PUNTOS
    assert ancho_cm == pytest.approx(15.5, abs=0.01)
    assert alto_cm == pytest.approx(22.0, abs=0.01)


def test_bordes_blancos_medidos_en_el_render(tmp_path: Path):
    fitz = pytest.importorskip("fitz", reason="PyMuPDF no instalado; se omite la medición por render")
    from PIL import Image

    salida = tmp_path / "recibo.pdf"
    g.generar_recibo_pdf(_datos_demo(2), salida)
    dpi = 150
    pix = fitz.open(salida)[0].get_pixmap(dpi=dpi)
    png = tmp_path / "recibo.png"
    pix.save(png)

    im = Image.open(png).convert("RGB")
    w, h = im.size
    px = im.load()

    def blanco(p):
        return p[0] > 245 and p[1] > 245 and p[2] > 245

    def col_blanca(x):
        return all(blanco(px[x, y]) for y in range(0, h, 4))

    def fila_blanca(y):
        return all(blanco(px[x, y]) for x in range(0, w, 4))

    a_cm = 2.54 / dpi
    izq = next(x for x in range(w) if not col_blanca(x)) * a_cm
    der = (w - 1 - next(x for x in range(w - 1, -1, -1) if not col_blanca(x))) * a_cm
    arr = next(y for y in range(h) if not fila_blanca(y)) * a_cm
    aba = (h - 1 - next(y for y in range(h - 1, -1, -1) if not fila_blanca(y))) * a_cm
    assert izq == pytest.approx(1.9, abs=0.05)
    assert der == pytest.approx(1.9, abs=0.05)
    assert arr == pytest.approx(0.5, abs=0.05)
    assert aba == pytest.approx(0.5, abs=0.05)
