"""
servicios/generador_pdf.py — Generador de recibos en PDF para CAAPD Ispacas.

Basado en las coordenadas exactas de datos/codepdf.py y las especificaciones
de docs/FASE_4_RECIBOS_PDF.md.

Soporta:
- Selección automática del fondo según nivel de mora:
    * 1 mes de deuda o al día  -> recursos/fondo_azul.png
    * 2 meses de deuda         -> recursos/fondo_naranja.png
    * 3 a más meses (corte)    -> recursos/fondo_rojo.png
- Dimensiones MEDIA CARTA: 13.97 cm de ancho x 21.59 cm de alto (5.5 x 8.5 pulgadas).
- El fondo se dibuja a pagina completa ANTES del ajuste de impresion (sin borde blanco).
- Dibujo de histograma de 6 meses vectorial.
- QR dinámico de atención / WhatsApp en el talón troquelado.
- Conversión a letras en español con calculos.numero_a_letras().
"""
from __future__ import annotations
import io
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import qrcode
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

import rutas
from calculos import calcular_nivel_mora, numero_a_letras, periodo_a_temporada

ANCHO_RECIBO = 13.97 * cm
ALTO_RECIBO = 21.59 * cm

DESPLAZAMIENTO_X_CM = 0.0
DESPLAZAMIENTO_Y_CM = 0.6

AJUSTE_TALON_Y_CM = -0.1

X_DERECHA = 13.3 * cm

PALETA_HISTOGRAMA = {
    "AZUL":    {"barra": "#0284c7", "actual": "#0c4a6e", "texto": "#1e293b"},
    "NARANJA": {"barra": "#ea7a1a", "actual": "#9a3412", "texto": "#431407"},
    "ROJO":    {"barra": "#c0392b", "actual": "#7f1d1d", "texto": "#450a0a"},
}

MESES_ABREV = [
    "ENE", "FEB", "MAR", "ABR", "MAY", "JUN",
    "JUL", "AGO", "SET", "OCT", "NOV", "DIC"
]


CONFIG_MORA_DEFAULT = [
    {"meses_min": 3, "color": "ROJO", "nombre": "Mora grave", "corte": True},
    {"meses_min": 2, "color": "NARANJA", "nombre": "Mora moderada", "corte": False},
    {"meses_min": 1, "color": "AZUL", "nombre": "Al día", "corte": False},
]


def resolver_color_mora(
    meses_adeudados: int = 1,
    pagado: bool = False,
    config_mora: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Devuelve la clave de color del recibo segun la mora: 'AZUL', 'NARANJA' o 'ROJO'."""
    cfg_mora = config_mora or CONFIG_MORA_DEFAULT
    monto_pagado = 100.0 if pagado else 0.0
    total_a_pagar = 100.0
    mora = calcular_nivel_mora(
        meses_adeudados, monto_pagado, total_a_pagar, cfg_mora)

    nombre = str(mora.get("nombre") or "").upper()
    color_val = str(mora.get("color") or "").upper()

    if "ROJO" in nombre or "#E53935" in color_val or "CORTE" in nombre or mora.get("corte"):
        color = "ROJO"
    elif "NARANJA" in nombre or "#FB8C00" in color_val or meses_adeudados == 2:
        color = "NARANJA"
    elif "AZUL" in nombre or "#1E88E5" in color_val or pagado or meses_adeudados <= 1:
        color = "AZUL"
    else:
        if meses_adeudados >= 3:
            color = "ROJO"
        elif meses_adeudados == 2:
            color = "NARANJA"
        else:
            color = "AZUL"
    return color


def resolver_fondo(
    meses_adeudados: int = 1,
    pagado: bool = False,
    config_mora: Optional[List[Dict[str, Any]]] = None,
) -> Path:
    """
    Determina la ruta de la plantilla de fondo (azul, naranja, rojo) según la mora.
    Prioriza escritorio/recursos/ y recurre a escritorio/datos/ como fallback.
    """
    color = resolver_color_mora(meses_adeudados, pagado, config_mora)

    mapeo_recursos = {
        "AZUL": rutas.ruta_recurso("recursos", "fondo_azul.png"),
        "NARANJA": rutas.ruta_recurso("recursos", "fondo_naranja.png"),
        "ROJO": rutas.ruta_recurso("recursos", "fondo_rojo.png"),
    }
    mapeo_datos = {
        "AZUL": rutas.ruta_datos("fondo.png"),
        "NARANJA": rutas.ruta_datos("fondo naranja.png"),
        "ROJO": rutas.ruta_datos("fondo rojo.png"),
    }

    p = mapeo_recursos.get(color, mapeo_recursos["AZUL"])
    if p.exists():
        return p
    p_fallback = mapeo_datos.get(color, mapeo_datos["AZUL"])
    if p_fallback.exists():
        return p_fallback

    # Si ninguno existe, buscar cualquier fondo disponible
    for alt in [mapeo_recursos["AZUL"], mapeo_datos["AZUL"]]:
        if alt.exists():
            return alt
    raise FileNotFoundError(f"No se encontró el molde de fondo para {color}.")


def dibujar_histograma(
    pdf: canvas.Canvas,
    historico: Dict[str, Optional[float]] | List[Tuple[str, Optional[float]]],
    x: float,
    y: float,
    ancho: float,
    alto: float,
    columnas: int = 6,
    paleta: Optional[Dict[str, str]] = None,
) -> None:
    """
    Dibuja un histograma de barras con los consumos (m3) de los ultimos meses.

    - SIEMPRE reserva `columnas` (6) espacios: si el usuario tiene menos meses,
      las barras quedan del mismo ancho y alineadas a la derecha (mes actual al final).
    - Un valor None significa "sin dato": se dibuja el mes y un guion, sin barra.
    - Escala Y DINAMICA con tope "bonito" (5, 10, 20, 50...) para que las barras
      siempre se vean grandes, y lineas guia con su valor.
    - La barra del mes actual (ultima) se resalta en color mas oscuro.
    - `paleta` define los colores (ver PALETA_HISTOGRAMA); por defecto la azul.
    """
    pal = paleta or PALETA_HISTOGRAMA["AZUL"]
    c_barra = colors.HexColor(pal["barra"])
    c_actual = colors.HexColor(pal["actual"])
    c_texto = colors.HexColor(pal["texto"])

    items: List[Tuple[str, Optional[float]]] = []
    if isinstance(historico, dict):
        items = list(historico.items())
    elif isinstance(historico, list):
        items = list(historico)
    if not items:
        return

    items = items[-columnas:]
    valores: List[Optional[float]] = []
    for _, v in items:
        try:
            valores.append(None if v is None or v ==
                           "" else max(0.0, float(v)))
        except (TypeError, ValueError):
            valores.append(None)
    con_dato = [v for v in valores if v is not None]
    max_consumo = max(con_dato) if con_dato else 0.0

    def _tope_bonito(v: float) -> float:
        import math
        if v <= 0:
            return 10.0
        for paso in (5, 10, 20, 25, 50, 100, 200, 500, 1000):
            tope = math.ceil(v / paso) * paso
            if tope / paso <= 5:
                return float(max(tope, 10))
        return float(math.ceil(v / 1000) * 1000)

    tope_y = _tope_bonito(max_consumo)
    n_div = 4
    paso_div = tope_y / n_div

    margen_izq = 0.75 * cm
    margen_inf = 0.45 * cm
    margen_sup = 0.35 * cm
    ancho_util = ancho - margen_izq
    alto_util = alto - margen_inf - margen_sup
    x0 = x + margen_izq
    y0 = y + margen_inf

    # Titulo
    pdf.setFont("Helvetica-Bold", 6.5)
    pdf.setFillColor(c_texto)
    pdf.drawString(x, y + alto + 0.1 * cm, "HISTORIAL DE CONSUMO (m3)")

    # Lineas guia + eje Y
    pdf.setLineWidth(0.4)
    pdf.setFont("Helvetica", 5.5)
    for i in range(n_div + 1):
        val = paso_div * i
        yy = y0 + (val / tope_y) * alto_util
        pdf.setStrokeColor(colors.HexColor("#94a3b8") if i ==
                           0 else colors.HexColor("#cbd5e1"))
        pdf.line(x0, yy, x0 + ancho_util, yy)
        pdf.setFillColor(colors.HexColor("#475569"))
        pdf.drawRightString(
            x0 - 2, yy - 1.5, f"{int(val)}" if val == int(val) else f"{val:.1f}")

    # Barras (alineadas a la derecha dentro de `columnas` espacios)
    n = len(items)
    espacio = ancho_util / columnas
    ancho_barra = espacio * 0.62
    desfase = (columnas - n) * espacio
    for idx, ((etiqueta, _), val) in enumerate(zip(items, valores)):
        es_actual = (idx == n - 1)
        bx = x0 + desfase + idx * espacio + (espacio - ancho_barra) / 2
        cx = bx + ancho_barra / 2

        if val is None:
            pdf.setFillColor(colors.HexColor("#94a3b8"))
            pdf.setFont("Helvetica", 6)
            pdf.drawCentredString(cx, y0 + 3, "–")
        else:
            h = (val / tope_y) * alto_util if tope_y > 0 else 0
            pdf.setFillColor(c_actual if es_actual else c_barra)
            pdf.rect(bx, y0, ancho_barra, h, fill=1, stroke=0)
            pdf.setFillColor(colors.black)
            pdf.setFont("Helvetica-Bold", 6.5)
            pdf.drawCentredString(
                cx, y0 + h + 2, f"{int(val)}" if val == int(val) else f"{val:.1f}")

        pdf.setFont("Helvetica-Bold" if es_actual else "Helvetica", 6)
        pdf.setFillColor(c_texto if es_actual else colors.HexColor("#334155"))
        pdf.drawCentredString(cx, y0 - 8, str(etiqueta)[:3].upper())


def generar_qr_imagen(texto: str) -> Image.Image:
    """Genera una imagen PIL del código QR."""
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(texto)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="transparent").convert("RGBA")


def generar_recibo_pdf(
    datos: Dict[str, Any],
    ruta_salida: str | Path,
    molde_png: Optional[str | Path] = None,
) -> Path:
    """
    Genera un archivo PDF para un recibo individual siguiendo las coordenadas de codepdf.py.

    datos espera las siguientes claves:
        - numero_recibo (int|str)
        - periodo (str 'AAAA-MM' o 'AAAA/MM')
        - fecha_emision (str)
        - ultimo_dia_pago (str)
        - conexion (str)
        - nombre (str)
        - dni_ruc (str)
        - zona (str)
        - direccion (str)
        - categoria (str)
        - medidores (list[dict]: medidor, lectura_anterior, fecha_anterior, lectura_actual, fecha_actual, consumo)
        - servicio_agua (float)
        - servicio_desague (float)
        - cargo_fijo (float)
        - deuda_anterior (float)
        - meses_adeudados (int)
        - subtotal (float)
        - igv (float)
        - redondeo (float)
        - total_a_pagar (float)
        - consumos_historicos (dict[mes, m3] o list)
        - resolucion (str, opcional)
        - whatsapp_url (str, opcional)
    """
    salida_path = Path(ruta_salida)
    salida_path.parent.mkdir(parents=True, exist_ok=True)

    meses_adeudados = int(datos.get("meses_adeudados") or 1)
    pagado = bool(datos.get("pagado", False))

    # Color del recibo (AZUL / NARANJA / ROJO): decide el fondo Y la paleta del histograma
    color_mora = resolver_color_mora(
        meses_adeudados, pagado, datos.get("config_mora"))
    if molde_png is None:
        fondo_path = resolver_fondo(
            meses_adeudados, pagado, datos.get("config_mora"))
    else:
        fondo_path = Path(molde_png)
    paleta = PALETA_HISTOGRAMA.get(color_mora, PALETA_HISTOGRAMA["AZUL"])

    pdf = canvas.Canvas(str(salida_path), pagesize=(ANCHO_RECIBO, ALTO_RECIBO))

    # ------------------------------------------------------------------
    # 1. FONDO: se dibuja PRIMERO, a pagina completa y SIN desplazamiento.
    #    Asi nunca aparece borde blanco aunque se ajuste la posicion del texto.
    DIBUJAR_FONDO = True
    # ------------------------------------------------------------------
    if DIBUJAR_FONDO:
        pdf.drawImage(
            str(fondo_path), 0, 0,
            width=ANCHO_RECIBO, height=ALTO_RECIBO,
            preserveAspectRatio=False, mask="auto",
        )

    # ------------------------------------------------------------------
    # 2. Ajuste de impresion: a partir de aqui TODO lo que se dibuja
    #    (textos, tablas, histograma, QR) se mueve con el desplazamiento.
    # ------------------------------------------------------------------
    pdf.translate(DESPLAZAMIENTO_X_CM * cm, DESPLAZAMIENTO_Y_CM * cm)

    # 3. Encabezado institucional
    resolucion = datos.get("resolucion") or "RESOLUCION 192-2017"
    pdf.setFont("Helvetica", 12)
    pdf.setFillColor(colors.black)
    pdf.drawString(0.5 * cm, 17.2 * cm, resolucion)

    # 4. Bloque superior derecho: Ultimo dia de pago y Monto
    ultimo_pago = str(datos.get("ultimo_dia_pago") or "—")
    total_pagar = float(datos.get("total_a_pagar") or 0.0)

    pdf.setFont("Helvetica", 9)
    pdf.drawString(7.0 * cm, 17.45 * cm, "Ultimo día de pago:")
    pdf.drawString(9.9 * cm, 17.45 * cm, ultimo_pago)
    pdf.drawString(7.0 * cm, 17.0 * cm, "Monto a pagar: S/.")
    pdf.drawString(9.9 * cm, 17.0 * cm, f"{total_pagar:.2f}")

    # 5. Numero de recibo y Temporada
    nro_recibo = str(datos.get("numero_recibo") or "0").zfill(9)
    periodo_str = str(datos.get("periodo") or "")
    temporada_str = periodo_a_temporada(
        periodo_str) if periodo_str else str(datos.get("temporada") or "")

    pdf.setFont("Helvetica", 7)
    pdf.drawString(0.5 * cm, 16.4 * cm, "Recibo Nro: ")
    pdf.drawString(1.9 * cm, 16.4 * cm, nro_recibo)

    pdf.setFont("Helvetica", 9)
    pdf.drawString(7.0 * cm, 16.4 * cm, "Temporada:")
    pdf.drawString(9.9 * cm, 16.4 * cm, temporada_str)

    # 6. Emision y Conexion
    emision_str = str(datos.get("fecha_emision") or "—")
    conexion_str = str(datos.get("conexion") or "—").zfill(6)

    pdf.setFont("Helvetica", 11)
    pdf.drawString(0.5 * cm, 15.9 * cm, f"Fecha emisión:  {emision_str}")

    pdf.setFont("Helvetica", 12)
    pdf.drawString(9.3 * cm, 15.7 * cm, f"Conexión: 000{conexion_str}")

    # 7. Datos del Titular
    nombre_str = str(datos.get("nombre") or "").upper()
    dni_str = str(datos.get("dni_ruc") or "")
    dni_impresion = "" if (
        "-" in dni_str or dni_str.startswith("SD")) else dni_str

    zona_str = str(datos.get("zona") or "").upper()
    direccion_str = str(datos.get("direccion") or "S/N").upper()
    categoria_str = str(datos.get("categoria") or "DOMESTICO").upper()

    pdf.setFont("Helvetica", 8)
    pdf.drawString(0.5 * cm, 15.45 * cm, f"Nombre: {nombre_str}")
    pdf.drawString(0.5 * cm, 15.1 * cm, f"DNI/RUC: {dni_impresion}")
    pdf.drawString(0.5 * cm, 14.4 * cm, f"Zona: {zona_str}")
    pdf.drawString(0.5 * cm, 14.0 * cm, f"Dirección: {direccion_str}")
    pdf.drawString(8.0 * cm, 14.3 * cm, f"Categoría: {categoria_str}")

    # 8. Tabla 1: Medidores y Lecturas
    medidores = datos.get("medidores") or []
    if not medidores:
        medidores = [{
            "medidor": "S/M",
            "lectura_anterior": 0.0,
            "fecha_anterior": "—",
            "lectura_actual": float(datos.get("consumo_total_m3") or 0.0),
            "fecha_actual": "—",
            "consumo": float(datos.get("consumo_total_m3") or 0.0),
        }]

    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(0.8 * cm, 13.3 * cm, "Medidor")
    pdf.drawString(2.8 * cm, 13.3 * cm, "L. Anterior")
    pdf.drawString(4.8 * cm, 13.3 * cm, "Fecha")
    pdf.drawString(6.8 * cm, 13.3 * cm, "L. Actual")
    pdf.drawString(8.8 * cm, 13.3 * cm, "Fecha")
    pdf.drawString(10.8 * cm, 13.3 * cm, "Consumo")

    y_medidor = 13.0 * cm
    pdf.setFont("Helvetica", 8)
    f_ant_global = "—"
    f_act_global = "—"
    for m in medidores[:3]:
        n_med = str(m.get("medidor") or m.get("nro_medidor") or "—")
        l_ant = float(m.get("lectura_anterior") or 0.0)
        f_ant = str(m.get("fecha_anterior") or "—")
        l_act = float(m.get("lectura_actual") or 0.0)
        f_act = str(m.get("fecha_actual") or m.get("fecha_lectura") or "—")
        c_m3 = float(m.get("consumo") or (l_act - l_ant))
        f_ant_global = f_ant if f_ant != "—" else f_ant_global
        f_act_global = f_act if f_act != "—" else f_act_global

        pdf.drawString(0.8 * cm, y_medidor, n_med)
        pdf.drawString(2.8 * cm, y_medidor, f"{l_ant:.2f}")
        pdf.drawString(4.8 * cm, y_medidor, f_ant)
        pdf.drawString(6.8 * cm, y_medidor, f"{l_act:.2f}")
        pdf.drawString(8.8 * cm, y_medidor, f_act)
        pdf.drawString(10.8 * cm, y_medidor, f"{c_m3:.2f}")
        y_medidor -= 0.35 * cm

    pdf.drawString(0.5 * cm, 12.6 * cm,
                   f"Periodo / Ciclo del {f_ant_global} al {f_act_global}")

    # 9. Conceptos de Cobro
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(0.6 * cm, 11.9 * cm, "DESCRIPCIÓN DE CONCEPTOS")
    pdf.drawString(8.6 * cm, 11.9 * cm, "INAFECTOS")
    pdf.drawRightString(X_DERECHA, 11.9 * cm, "AFECTOS")

    s_agua = float(datos.get("servicio_agua") or 0.0)
    s_desague = float(datos.get("servicio_desague") or 0.0)
    c_fijo = float(datos.get("cargo_fijo") or 0.0)
    deuda_ant = float(datos.get("deuda_anterior") or 0.0)

    pdf.setFont("Helvetica", 8)
    pdf.drawString(0.6 * cm, 11.5 * cm, "001")
    pdf.drawString(1.6 * cm, 11.5 * cm, "SERVICIO DE AGUA")
    pdf.drawRightString(X_DERECHA, 11.5 * cm, f"{s_agua:.2f}")
    pdf.drawString(0.6 * cm, 11.1 * cm, "008")
    pdf.drawString(1.6 * cm, 11.1 * cm, "SERVICIO DE DESAGUE")
    pdf.drawRightString(X_DERECHA, 11.1 * cm, f"{s_desague:.2f}")
    pdf.drawString(0.6 * cm, 10.7 * cm, "407")
    pdf.drawString(1.6 * cm, 10.7 * cm, "CARGO FIJO")
    pdf.drawRightString(X_DERECHA, 10.7 * cm, f"{c_fijo:.2f}")

    leyenda_deuda = "(SIN DEUDA)" if deuda_ant == 0 else "(CON DEUDA)"
    pdf.drawString(1.6 * cm, 10.3 * cm, f"DEUDA ANTERIOR {leyenda_deuda}")
    pdf.drawString(8.6 * cm, 10.3 * cm, f"S/. {deuda_ant:.2f}")

    # 10. Histograma de 6 meses (colores segun el fondo)
    dibujar_histograma(
        pdf,
        datos.get("consumos_historicos") or {},
        x=0.6 * cm, y=5.0 * cm, ancho=6.0 * cm, alto=4.0 * cm,
        paleta=paleta,
    )

    # 11. Totales
    subtotal = float(datos.get("subtotal") or (
        s_agua + s_desague + c_fijo + deuda_ant))
    igv = float(datos.get("igv") or 0.0)
    redondeo = float(datos.get("redondeo") or 0.0)

    pdf.setFont("Helvetica", 8)
    pdf.drawString(8.6 * cm, 7.8 * cm, "Subtotal")
    pdf.drawString(8.6 * cm, 7.4 * cm, "IGV")
    pdf.drawString(8.6 * cm, 7.0 * cm, "Redondeo")
    pdf.drawString(8.6 * cm, 6.6 * cm, "TOTAL MES")
    pdf.drawRightString(X_DERECHA, 7.8 * cm, f"{subtotal:.2f}")
    pdf.drawRightString(X_DERECHA, 7.4 * cm, f"{igv:.2f}")
    pdf.drawRightString(
        X_DERECHA, 7.0 * cm, f"-{redondeo:.2f}" if redondeo > 0 else f"{redondeo:.2f}")
    pdf.drawRightString(X_DERECHA, 6.6 * cm, f"{total_pagar:.2f}")

    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(8.6 * cm, 5.9 * cm, "TOTAL A PAGAR S/.")
    pdf.drawRightString(X_DERECHA, 5.9 * cm, f"{total_pagar:.2f}")

    # 12. Monto en letras
    pdf.setFont("Helvetica", 8)
    pdf.drawString(0.5 * cm, 4.7 * cm, f"Son: {numero_a_letras(total_pagar)}")

    # ------------------------------------------------------------------
    # TALON INFERIOR: tiene su propio ajuste vertical independiente.
    # ------------------------------------------------------------------
    pdf.saveState()
    pdf.translate(0, AJUSTE_TALON_Y_CM * cm)

    # 13. Codigo QR (WhatsApp) con fondo transparente
    whatsapp_url = datos.get("whatsapp_url") or (
        "https://api.whatsapp.com/send?phone=51983365260&text=Hola%20buenos%20dias%20quisiera%20mi%20boleta%20de%20agua"
    )
    img_qr = generar_qr_imagen(whatsapp_url)
    qr_buffer = io.BytesIO()
    img_qr.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)
    from reportlab.lib.utils import ImageReader
    pdf.drawImage(ImageReader(qr_buffer), 0.5 * cm, 1.0 * cm,
                  width=2.0 * cm, height=2.0 * cm, mask="auto")

    # 14. Talon inferior
    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(3.0 * cm, 2.6 * cm, "Conexión:")
    pdf.drawString(4.3 * cm, 2.6 * cm, f"000{conexion_str}")
    pdf.drawString(3.0 * cm, 2.3 * cm, "Nombre:")
    pdf.drawString(4.3 * cm, 2.3 * cm, nombre_str[:40])
    pdf.drawString(0.7 * cm, 0.7 * cm, "Recibo Nro:")
    pdf.drawString(2.4 * cm, 0.7 * cm, nro_recibo)
    pdf.drawString(0.7 * cm, 0.4 * cm, "Emisión:")
    pdf.drawString(2.4 * cm, 0.4 * cm, emision_str)
    pdf.drawString(0.7 * cm, 0.1 * cm, "Vencimiento:")
    pdf.drawString(2.4 * cm, 0.1 * cm, ultimo_pago)

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(4.4 * cm, 1.5 * cm, "TOTAL A PAGAR S/.")
    pdf.drawString(8.8 * cm, 1.5 * cm, f"{total_pagar:.2f}")

    pdf.restoreState()
    pdf.save()
    return salida_path


def preparar_datos_recibo_desde_doc(
    doc: Dict[str, Any],
    config: Dict[str, Any],
    periodo: str,
) -> Dict[str, Any]:
    """Adapta un documento de Firestore mes_aaaa-mm al diccionario esperado por generar_recibo_pdf."""
    mes_act = config.get("mes_actual") or {}
    emision = mes_act.get("fecha_emision") or doc.get("fecha_emision") or "—"
    vencimiento = mes_act.get("fecha_vencimiento") or doc.get(
        "fecha_vencimiento") or "—"

    # Formatear fechas si vienen en formato ISO AAAA-MM-DD
    def formatear_fecha(f_str: str) -> str:
        if not f_str or f_str == "—":
            return "—"
        partes = f_str.split("-")
        if len(partes) == 3:
            return f"{partes[2]}/{partes[1]}/{partes[0]}"
        return f_str

    emision_fmt = formatear_fecha(emision)
    vencimiento_fmt = formatear_fecha(vencimiento)

    # Medidores del usuario
    medidores_doc = doc.get("medidores") or []
    medidores_formateados = []
    for m in medidores_doc:
        n_med = m.get("nro_medidor") or "—"
        l_ant = float(m.get("lectura_anterior") or 0.0)
        f_ant = formatear_fecha(m.get("fecha_anterior") or "—")
        l_act = float(m.get("lectura_actual") if m.get(
            "lectura_actual") is not None else l_ant)
        f_act = formatear_fecha(m.get("fecha_lectura") or "—")
        c_m3 = max(0.0, l_act - l_ant)
        medidores_formateados.append({
            "medidor": n_med,
            "lectura_anterior": l_ant,
            "fecha_anterior": f_ant,
            "lectura_actual": l_act,
            "fecha_actual": f_act,
            "consumo": c_m3,
        })

    # Conceptos monetarios
    s_agua = float(doc.get("monto_agua") or 0.0)
    s_desague = float(doc.get("monto_desague") or 0.0)
    c_fijo = float(doc.get("cargo_fijo") or 0.0)
    deuda_ant = float(doc.get("deuda_anterior") or 0.0)
    subtotal = round(s_agua + s_desague + c_fijo + deuda_ant, 2)
    igv = float(doc.get("igv") or 0.0)
    redondeo = float(doc.get("redondeo") or 0.0)
    total_a_pagar = float(doc.get("total_a_pagar") or subtotal)
    meses_adeudados = int(doc.get("meses_adeudados") or 1)
    monto_pagado = float(doc.get("monto_pagado") or 0.0)
    pagado = (monto_pagado >= total_a_pagar and total_a_pagar > 0)

    # Consumos históricos (últimos 5 + mes actual)
    hist_prev = list(doc.get("historial_m3") or [])
    consumo_actual = float(doc.get("consumo_total_m3") or 0.0)
    serie_completa = (hist_prev + [consumo_actual])[-6:]
    # Siempre 6 columnas: los meses sin dato (usuario nuevo) van como None
    serie_completa = [None] * (6 - len(serie_completa)) + serie_completa

    # Asignar nombres de mes a las barras
    import datetime
    try:
        y, m_num = [int(p) for p in periodo.split("-")]
    except Exception:
        y, m_num = 2026, 10

    etiquetas = []
    for offset in range(len(serie_completa) - 1, -1, -1):
        mes_idx = (m_num - 1 - offset) % 12
        etiquetas.append(MESES_ABREV[mes_idx])

    consumos_hist_dict = {etiquetas[i]: serie_completa[i]
                          for i in range(len(serie_completa))}

    empresa = config.get("empresa") or {}
    whatsapp_val = empresa.get("whatsapp")
    if not whatsapp_val:
        whatsapp_url = "https://api.whatsapp.com/send?phone=51983365260&text=Hola%20buenos%20dias%20quisiera%20mi%20boleta%20de%20agua"
    elif str(whatsapp_val).startswith("http"):
        whatsapp_url = str(whatsapp_val)
    else:
        phone = str(whatsapp_val).replace("+", "").replace(" ", "").strip()
        if not phone.startswith("51") and len(phone) == 9:
            phone = f"51{phone}"
        whatsapp_url = f"https://api.whatsapp.com/send?phone={phone}&text=Hola%20buenos%20dias%20quisiera%20mi%20boleta%20de%20agua"

    res_val = str(empresa.get("resolucion") or "192-2017").strip()
    resolucion = res_val if res_val.upper().startswith(
        "RESOLUCION") else f"RESOLUCION {res_val}"

    return {
        "numero_recibo": doc.get("nro_recibo") or "0",
        "nro_recibo": doc.get("nro_recibo") or "0",
        "conexion": doc.get("nro_conexion") or "—",
        "nombre": doc.get("nombre") or "",
        "dni_ruc": doc.get("_id") or doc.get("id_usuario") or "",
        "zona": doc.get("sector") or "",
        "direccion": doc.get("direccion") or "S/N",
        "categoria": doc.get("codigo_categoria") or "A",
        "periodo": periodo,
        "fecha_emision": emision_fmt,
        "ultimo_dia_pago": vencimiento_fmt,
        "medidores": medidores_formateados,
        "servicio_agua": s_agua,
        "servicio_desague": s_desague,
        "cargo_fijo": c_fijo,
        "deuda_anterior": deuda_ant,
        "meses_adeudados": meses_adeudados,
        "subtotal": subtotal,
        "igv": igv,
        "redondeo": redondeo,
        "total_a_pagar": total_a_pagar,
        "pagado": pagado,
        "consumos_historicos": consumos_hist_dict,
        "config_mora": config.get("mora"),
        "resolucion": resolucion,
        "whatsapp_url": whatsapp_url,
    }


def generar_recibo_pdf_para_usuario(
    doc: Dict[str, Any],
    config: Dict[str, Any],
    periodo: str,
    ruta_salida: Optional[Path | str] = None,
) -> Path:
    """Genera el PDF del recibo para un documento de usuario de Firestore."""
    datos = preparar_datos_recibo_desde_doc(doc, config, periodo)
    if ruta_salida is None:
        sector_raw = str(doc.get("sector") or "GENERAL").strip()
        import re
        sector_limpio = re.sub(r"[^\w\s-]", "", sector_raw).strip()
        conexion = str(doc.get("nro_conexion") or "000000").zfill(6)
        nombre_raw = str(doc.get("nombre") or "USUARIO").strip()
        nombre_limpio = re.sub(r"[^\w\s-]", "", nombre_raw)[:30].strip()
        nombre_archivo = f"recibo_{conexion}_{nombre_limpio}.pdf"

        # Guardar en <Escritorio>/recibos/aaaa-mm/<sector>/
        dir_sector = rutas.ruta_recibos(periodo, sector_limpio)
        ruta_salida = dir_sector / nombre_archivo

    return generar_recibo_pdf(datos, ruta_salida=ruta_salida)


def empaquetar_recibos_en_zip(
    periodo: str,
    sector: Optional[str] = None,
    ruta_destino_zip: Optional[Path | str] = None,
) -> Optional[Path]:
    """Empaqueta todos los PDFs de recibos en un archivo .ZIP."""
    import zipfile
    dir_recibos = rutas.ruta_recibos(periodo)
    if not dir_recibos.exists():
        return None

    if sector:
        import re
        sec_limpio = re.sub(r"[^\w\s-]", "", sector).strip()
        archivos_pdf = list((dir_recibos / sec_limpio).glob("*.pdf"))
        nombre_zip = f"recibos_{periodo}_{sec_limpio}.zip"
    else:
        archivos_pdf = list(dir_recibos.rglob("*.pdf"))
        nombre_zip = f"recibos_{periodo}_TODOS.zip"

    if not archivos_pdf:
        return None

    if ruta_destino_zip is None:
        ruta_zip = dir_recibos / nombre_zip
    else:
        ruta_zip = Path(ruta_destino_zip)

    ruta_zip.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(ruta_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for pdf_file in archivos_pdf:
            arcname = pdf_file.relative_to(dir_recibos)
            zf.write(pdf_file, arcname=str(arcname))

    return ruta_zip
