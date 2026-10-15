"""
servicios/generador_pdf.py — Generador de recibos en PDF para CAAPD Ispacas.

Basado en las coordenadas exactas de datos/codepdf.py y las especificaciones
de docs/FASE_4_RECIBOS_PDF.md.

Soporta:
- Selección automática del fondo según nivel de mora:
    * 1 mes de deuda o al día  -> recursos/fondo_azul.png
    * 2 meses de deuda         -> recursos/fondo_naranja.png
    * 3 a más meses (corte)    -> recursos/fondo_rojo.png
- Dimensiones media hoja: 14.7 cm de ancho x 20.8 cm de alto.
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


# Dimensiones oficiales del recibo (media hoja)
ANCHO_RECIBO = 14.7 * cm
ALTO_RECIBO = 20.8 * cm

MESES_ABREV = [
    "ENE", "FEB", "MAR", "ABR", "MAY", "JUN",
    "JUL", "AGO", "SET", "OCT", "NOV", "DIC"
]


CONFIG_MORA_DEFAULT = [
    {"meses_min": 3, "color": "ROJO", "nombre": "Mora grave", "corte": True},
    {"meses_min": 2, "color": "NARANJA", "nombre": "Mora moderada", "corte": False},
    {"meses_min": 1, "color": "AZUL", "nombre": "Al día", "corte": False},
]


def resolver_fondo(
    meses_adeudados: int = 1,
    pagado: bool = False,
    config_mora: Optional[List[Dict[str, Any]]] = None,
) -> Path:
    """
    Determina la ruta de la plantilla de fondo (azul, naranja, rojo) según la mora.
    Prioriza escritorio/recursos/ y recurre a escritorio/datos/ como fallback.
    """
    cfg_mora = config_mora or CONFIG_MORA_DEFAULT
    monto_pagado = 100.0 if pagado else 0.0
    total_a_pagar = 100.0
    mora = calcular_nivel_mora(meses_adeudados, monto_pagado, total_a_pagar, cfg_mora)

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
    historico: Dict[str, float] | List[Tuple[str, float]],
    x: float,
    y: float,
    ancho: float,
    alto: float,
) -> None:
    """
    Dibuja un histograma de barras con los consumos de los últimos meses.
    Escala Y con tope de 100 m³, dinámico si se supera.
    """
    items: List[Tuple[str, float]] = []
    if isinstance(historico, dict):
        items = list(historico.items())
    elif isinstance(historico, list):
        items = historico

    if not items:
        return

    # Limitar a máximo 6 meses
    items = items[-6:]

    valores = [float(v or 0) for _, v in items]
    max_consumo = max(valores) if valores else 0
    tope_y = max(100.0, max_consumo)  # Fijo hasta 100, dinámico si supera

    margen_izq = 0.4 * cm
    margen_inf = 0.5 * cm
    ancho_util = ancho - margen_izq
    alto_util = alto - margen_inf

    # Eje base sutil
    pdf.setStrokeColor(colors.HexColor("#94a3b8"))
    pdf.setLineWidth(0.6)
    pdf.line(x + margen_izq, y + margen_inf, x + ancho, y + margen_inf)

    n_barras = len(items)
    ancho_barra = (ancho_util / n_barras) * 0.65
    espacio = ancho_util / n_barras

    for idx, (etiqueta, val) in enumerate(items):
        pos_x = x + margen_izq + (idx * espacio) + (espacio - ancho_barra) / 2
        val_seguro = max(0.0, float(val or 0))
        h_barra = (val_seguro / tope_y) * (alto_util - 0.4 * cm) if tope_y > 0 else 0

        # Barra azul
        pdf.setFillColor(colors.HexColor("#0284c7"))
        pdf.rect(pos_x, y + margen_inf, ancho_barra, h_barra, fill=1, stroke=0)

        # Cifra sobre la barra
        pdf.setFillColor(colors.black)
        pdf.setFont("Helvetica-Bold", 6)
        txt_val = f"{int(val_seguro)}" if val_seguro == int(val_seguro) else f"{val_seguro:.1f}"
        pdf.drawCentredString(pos_x + ancho_barra / 2, y + margen_inf + h_barra + 2, txt_val)

        # Nombre del mes debajo
        pdf.setFont("Helvetica", 6)
        pdf.setFillColor(colors.HexColor("#334155"))
        etiqueta_corta = str(etiqueta)[:3].upper()
        pdf.drawCentredString(pos_x + ancho_barra / 2, y + margen_inf - 8, etiqueta_corta)


def generar_qr_imagen(texto: str) -> Image.Image:
    """Genera una imagen PIL del código QR."""
    qr = qrcode.QRCode(box_size=10, border=1)
    qr.add_data(texto)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


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

    if molde_png is None:
        fondo_path = resolver_fondo(meses_adeudados, pagado, datos.get("config_mora"))
    else:
        fondo_path = Path(molde_png)

    pdf = canvas.Canvas(str(salida_path), pagesize=(ANCHO_RECIBO, ALTO_RECIBO))

    # 1. Dibujar imagen de fondo en toda la hoja
    pdf.drawImage(str(fondo_path), 0, 0, width=ANCHO_RECIBO, height=ALTO_RECIBO)

    # 2. Encabezado institucional
    resolucion = datos.get("resolucion") or "RESOLUCION 192-2017"
    pdf.setFont("Helvetica", 11)
    pdf.setFillColor(colors.black)
    pdf.drawString(0.5 * cm, 17.2 * cm, resolucion)

    # 3. Bloque superior derecho: Último día de pago y Monto
    ultimo_pago = str(datos.get("ultimo_dia_pago") or "—")
    total_pagar = float(datos.get("total_a_pagar") or 0.0)

    pdf.setFont("Helvetica", 9)
    pdf.drawString(7.0 * cm, 17.45 * cm, "Ultimo día de pago:")
    pdf.drawString(9.9 * cm, 17.45 * cm, ultimo_pago)
    pdf.drawString(7.0 * cm, 17.0 * cm, "Monto a pagar: S/.")
    pdf.drawString(9.9 * cm, 17.0 * cm, f"{total_pagar:.2f}")

    # 4. Número de recibo y Temporada
    nro_recibo = str(datos.get("numero_recibo") or "0").zfill(9)
    periodo_str = str(datos.get("periodo") or "")
    temporada_str = periodo_a_temporada(periodo_str) if periodo_str else str(datos.get("temporada") or "")

    pdf.setFont("Helvetica", 7)
    pdf.drawString(0.5 * cm, 16.4 * cm, "Recibo Nro: ")
    pdf.drawString(1.9 * cm, 16.4 * cm, nro_recibo)

    pdf.setFont("Helvetica", 9)
    pdf.drawString(7.0 * cm, 16.4 * cm, "Temporada:")
    pdf.drawString(9.9 * cm, 16.4 * cm, temporada_str)

    # 5. Emisión y Conexión
    emision_str = str(datos.get("fecha_emision") or "—")
    conexion_str = str(datos.get("conexion") or "—").zfill(6)

    pdf.setFont("Helvetica", 10)
    pdf.drawString(0.5 * cm, 15.9 * cm, f"Fecha emisión:  {emision_str}")

    pdf.setFont("Helvetica", 11)
    pdf.drawString(9.6 * cm, 15.7 * cm, f"Conexión: {conexion_str}")

    # 6. Datos del Titular
    nombre_str = str(datos.get("nombre") or "").upper()
    dni_str = str(datos.get("dni_ruc") or "")
    # Ocultar IDs provisionales o con guion según regla de negocio
    if "-" in dni_str or dni_str.startswith("SD"):
        dni_impresion = ""
    else:
        dni_impresion = dni_str

    zona_str = str(datos.get("zona") or "").upper()
    direccion_str = str(datos.get("direccion") or "S/N").upper()
    categoria_str = str(datos.get("categoria") or "DOMESTICO").upper()

    pdf.setFont("Helvetica", 8)
    pdf.drawString(0.5 * cm, 15.45 * cm, f"Nombre: {nombre_str}")
    pdf.drawString(0.5 * cm, 15.1 * cm, f"DNI/RUC: {dni_impresion}")

    pdf.drawString(0.5 * cm, 14.4 * cm, f"Zona: {zona_str}")
    pdf.drawString(0.5 * cm, 14.0 * cm, f"Dirección: {direccion_str}")
    pdf.drawString(8.0 * cm, 14.3 * cm, f"Categoría: {categoria_str}")

    # 7. Tabla 1: Medidores y Lecturas
    medidores = datos.get("medidores") or []
    if not medidores:
        # Medidor por defecto si no tiene asignado
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

    for m in medidores[:3]:  # Hasta 3 medidores en el recuadro
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

    # Leyenda de Periodo / Ciclo
    pdf.drawString(
        0.5 * cm,
        12.6 * cm,
        f"Periodo / Ciclo del {f_ant_global} al {f_act_global}",
    )

    # 8. Conceptos de Cobro
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(0.6 * cm, 11.9 * cm, "DESCRIPCIÓN DE CONCEPTOS")
    pdf.drawString(9.0 * cm, 11.9 * cm, "INAFECTOS")
    pdf.drawString(12.0 * cm, 11.9 * cm, "AFECTOS")

    s_agua = float(datos.get("servicio_agua") or 0.0)
    s_desague = float(datos.get("servicio_desague") or 0.0)
    c_fijo = float(datos.get("cargo_fijo") or 0.0)
    deuda_ant = float(datos.get("deuda_anterior") or 0.0)

    pdf.setFont("Helvetica", 8)
    # 001 SERVICIO DE AGUA
    pdf.drawString(0.6 * cm, 11.5 * cm, "001")
    pdf.drawString(1.6 * cm, 11.5 * cm, "SERVICIO DE AGUA")
    pdf.drawRightString(13.65 * cm, 11.5 * cm, f"{s_agua:.2f}")

    # 008 SERVICIO DE DESAGÜE
    pdf.drawString(0.6 * cm, 11.1 * cm, "008")
    pdf.drawString(1.6 * cm, 11.1 * cm, "SERVICIO DE DESAGUE")
    pdf.drawRightString(13.65 * cm, 11.1 * cm, f"{s_desague:.2f}")

    # 407 CARGO FIJO
    pdf.drawString(0.6 * cm, 10.7 * cm, "407")
    pdf.drawString(1.6 * cm, 10.7 * cm, "CARGO FIJO")
    pdf.drawRightString(13.65 * cm, 10.7 * cm, f"{c_fijo:.2f}")

    # DEUDA ANTERIOR
    leyenda_deuda = "(SIN DEUDA)" if deuda_ant == 0 else "(CON DEUDA)"
    pdf.drawString(1.6 * cm, 10.3 * cm, f"DEUDA ANTERIOR {leyenda_deuda}")
    pdf.drawString(9.0 * cm, 10.3 * cm, f"S/. {deuda_ant:.2f}")

    # 9. Histograma de 6 meses
    consumos_hist = datos.get("consumos_historicos") or {}
    dibujar_histograma(
        pdf,
        consumos_hist,
        x=0.6 * cm,
        y=5.0 * cm,
        ancho=6.0 * cm,
        alto=4.0 * cm,
    )

    # 10. Totales
    subtotal = float(datos.get("subtotal") or (s_agua + s_desague + c_fijo + deuda_ant))
    igv = float(datos.get("igv") or 0.0)
    redondeo = float(datos.get("redondeo") or 0.0)

    pdf.setFont("Helvetica", 8)
    pdf.drawString(9.0 * cm, 7.8 * cm, "Subtotal")
    pdf.drawString(9.0 * cm, 7.4 * cm, "IGV")
    pdf.drawString(9.0 * cm, 7.0 * cm, "Redondeo")
    pdf.drawString(9.0 * cm, 6.6 * cm, "TOTAL MES")

    pdf.drawRightString(13.65 * cm, 7.8 * cm, f"{subtotal:.2f}")
    pdf.drawRightString(13.65 * cm, 7.4 * cm, f"{igv:.2f}")
    txt_redondeo = f"-{redondeo:.2f}" if redondeo > 0 else f"{redondeo:.2f}"
    pdf.drawRightString(13.65 * cm, 7.0 * cm, txt_redondeo)
    pdf.drawRightString(13.65 * cm, 6.6 * cm, f"{total_pagar:.2f}")

    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(9.0 * cm, 5.9 * cm, "TOTAL A PAGAR S/.")
    pdf.drawRightString(13.65 * cm, 5.9 * cm, f"{total_pagar:.2f}")

    # 11. Monto en letras (Son: ...)
    letras_total = numero_a_letras(total_pagar)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(0.5 * cm, 4.7 * cm, f"Son: {letras_total}")

    # 12. Línea de corte / Talón
    pdf.setDash(5, 2)
    pdf.setStrokeColor(colors.HexColor("#64748b"))
    pdf.line(0 * cm, 4.1 * cm, ANCHO_RECIBO, 4.1 * cm)
    pdf.setDash()  # Restaurar línea sólida

    # 13. Código QR (WhatsApp de consultas)
    whatsapp_url = datos.get("whatsapp_url") or (
        "https://api.whatsapp.com/send?phone=51983365260&text=Hola%20buenos%20dias%20quisiera%20mi%20boleta%20de%20agua"
    )
    img_qr = generar_qr_imagen(whatsapp_url)
    qr_buffer = io.BytesIO()
    img_qr.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)

    from reportlab.lib.utils import ImageReader
    pdf.drawImage(
        ImageReader(qr_buffer),
        0.5 * cm,
        1.5 * cm,
        width=2.0 * cm,
        height=2.0 * cm,
        mask="auto",
    )

    # 14. Datos del Talón inferior
    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(3.0 * cm, 3.0 * cm, "Conexión:")
    pdf.drawString(4.3 * cm, 3.0 * cm, conexion_str)
    pdf.drawString(3.0 * cm, 2.6 * cm, "Nombre:")
    pdf.drawString(4.3 * cm, 2.6 * cm, nombre_str[:38])

    pdf.drawString(0.7 * cm, 1.2 * cm, "Recibo Nro:")
    pdf.drawString(2.4 * cm, 1.2 * cm, nro_recibo)
    pdf.drawString(0.7 * cm, 0.9 * cm, "Emisión:")
    pdf.drawString(2.4 * cm, 0.9 * cm, emision_str)
    pdf.drawString(0.7 * cm, 0.6 * cm, "Vencimiento:")
    pdf.drawString(2.4 * cm, 0.6 * cm, ultimo_pago)

    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(4.4 * cm, 1.7 * cm, "TOTAL A PAGAR S/.")
    pdf.drawString(8.8 * cm, 1.7 * cm, f"{total_pagar:.2f}")

    # Finalizar y guardar
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
    vencimiento = mes_act.get("fecha_vencimiento") or doc.get("fecha_vencimiento") or "—"

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
        l_act = float(m.get("lectura_actual") if m.get("lectura_actual") is not None else l_ant)
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

    consumos_hist_dict = {etiquetas[i]: serie_completa[i] for i in range(len(serie_completa))}

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
    resolucion = res_val if res_val.upper().startswith("RESOLUCION") else f"RESOLUCION {res_val}"

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

        # Guardar en recibos/aaaa-mm/<sector>/
        dir_sector = rutas.DIR_BASE.parent / "recibos" / periodo / sector_limpio
        dir_sector.mkdir(parents=True, exist_ok=True)
        ruta_salida = dir_sector / nombre_archivo

    return generar_recibo_pdf(datos, ruta_salida=ruta_salida)


def empaquetar_recibos_en_zip(
    periodo: str,
    sector: Optional[str] = None,
    ruta_destino_zip: Optional[Path | str] = None,
) -> Optional[Path]:
    """Empaqueta todos los PDFs de recibos en un archivo .ZIP."""
    import zipfile
    dir_recibos = rutas.DIR_BASE.parent / "recibos" / periodo
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
