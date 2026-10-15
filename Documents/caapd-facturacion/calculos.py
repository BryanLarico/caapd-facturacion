"""
calculos.py — Cálculos puros del sistema CAAPD Ispacas.

Sin dependencias de Firebase ni Flask.
Todas las funciones son deterministas y testeables con pytest.
"""

from __future__ import annotations
import math
import re
from decimal import Decimal, ROUND_HALF_UP


# ---------------------------------------------------------------------------
# Normalización de códigos (delegado a codigos.py)
# ---------------------------------------------------------------------------

from codigos import (
    normalizar_medidor,
    normalizar_conexion,
    normalizar_recibo,
    normalizar_dni,
    generar_id_usuario,
    es_id_pendiente,
)


# ---------------------------------------------------------------------------
# Cálculo del precio de agua según rangos (precio único)
# ---------------------------------------------------------------------------

def calcular_monto_agua(consumo_m3: float,
                         rangos: list[dict]) -> float:
    """Calcula el monto de agua usando precio único por rango.

    El consumo total se cobra al precio del rango donde cae.
    Si no hay rangos o el consumo es 0, devuelve 0.0.

    Parámetros de cada rango (dict):
        m3_desde  — inicio del rango (inclusive)
        m3_hasta  — fin del rango (inclusive); None = sin tope
        precio_m3 — precio por m³ en ese rango
    """
    if consumo_m3 <= 0 or not rangos:
        return 0.0

    def parse_hasta(r: dict) -> float:
        h = r.get("m3_hasta")
        if h is None or str(h).strip() == "" or str(h).lower() == "none":
            return float("inf")
        try:
            return float(h)
        except (ValueError, TypeError):
            return float("inf")

    rangos_ord = sorted(rangos, key=parse_hasta)
    precio = None
    for rango in rangos_ord:
        p = rango.get("precio_m3")
        if p is None:
            continue
        limite = parse_hasta(rango)
        if consumo_m3 <= limite:
            precio = float(p)
            break

    if precio is None:
        return 0.0

    return round(consumo_m3 * precio, 2)


# ---------------------------------------------------------------------------
# Cálculo completo del recibo
# ---------------------------------------------------------------------------

def calcular_recibo(
    *,
    medidores: list[dict],
    categoria: dict,
    igv_activo: bool,
    igv_porcentaje: float,
    recibo_anterior: dict | None,
) -> dict:
    """Calcula todos los campos del recibo.

    Parámetros:
        medidores       — lista de dicts con lectura_anterior y lectura_actual
        categoria       — dict con tarifa_desague, cargo_fijo y rangos
        igv_activo      — bool
        igv_porcentaje  — float (ej. 0.18)
        recibo_anterior — dict con total_a_pagar, monto_pagado, meses_adeudados
                          (puede ser None si es el primer recibo)

    Devuelve dict con todos los campos calculados.
    """
    # --- Consumo total ---
    consumo_total_m3 = 0.0
    for m in medidores:
        la = m.get("lectura_anterior", 0) or 0
        la_act = m.get("lectura_actual")
        if la_act is None:
            raise ValueError(
                f"Medidor {m.get('nro_medidor')} sin lectura_actual."
            )
        consumo_total_m3 += max(0.0, float(la_act) - float(la))

    consumo_total_m3 = round(consumo_total_m3, 2)

    # --- Conceptos ---
    rangos = categoria.get("rangos", [])
    monto_agua = calcular_monto_agua(consumo_total_m3, rangos)
    monto_desague = float(categoria.get("tarifa_desague") or 0.0)
    cargo_fijo = float(categoria.get("cargo_fijo") or 0.0)

    # --- Deuda anterior ---
    if recibo_anterior:
        tap = float(recibo_anterior.get("total_a_pagar") or 0.0)
        mp = float(recibo_anterior.get("monto_pagado") or 0.0)
        deuda_anterior = max(0.0, round(tap - mp, 2))
    else:
        deuda_anterior = 0.0

    # --- IGV (solo sobre lo afecto: agua + desagüe + cargo fijo) ---
    subtotal_afecto = round(monto_agua + monto_desague + cargo_fijo, 2)
    igv = round(subtotal_afecto * igv_porcentaje, 2) if igv_activo else 0.0

    # --- Redondeo y total ---
    total_antes = round(subtotal_afecto + deuda_anterior + igv, 2)
    # Usar Decimal para evitar errores de punto flotante en el módulo
    from decimal import Decimal, ROUND_DOWN
    d_total = Decimal(str(total_antes))
    d_diez = Decimal("0.10")
    # Centésimas sobrantes para llegar al múltiplo de 0.10 inferior
    centesimas = float(d_total % d_diez)
    redondeo = round(centesimas, 2)
    total_a_pagar = round(total_antes - redondeo, 2)

    # --- Mora ---
    if recibo_anterior is None:
        meses_adeudados = 1
    else:
        tap_ant = float(recibo_anterior.get("total_a_pagar") or 0.0)
        mp_ant = float(recibo_anterior.get("monto_pagado") or 0.0)
        m_ant = int(recibo_anterior.get("meses_adeudados") or 1)
        if mp_ant >= tap_ant:  # pagado
            meses_adeudados = 1
        else:
            meses_adeudados = m_ant + 1

    return {
        "consumo_total_m3": consumo_total_m3,
        "monto_agua": monto_agua,
        "monto_desague": monto_desague,
        "cargo_fijo": cargo_fijo,
        "deuda_anterior": deuda_anterior,
        "igv": igv,
        "redondeo": redondeo,
        "total_a_pagar": total_a_pagar,
        "meses_adeudados": meses_adeudados,
        "monto_pagado": 0.0,
        "fecha_pago": None,
    }


# ---------------------------------------------------------------------------
# Nivel de mora
# ---------------------------------------------------------------------------

def calcular_nivel_mora(meses_adeudados: int,
                         monto_pagado: float,
                         total_a_pagar: float,
                         config_mora: list[dict]) -> dict:
    """Devuelve el nivel de mora (dict con nombre, color, corte).

    Si el recibo está pagado, devuelve nivel neutro (color base).

    config_mora — lista de dicts ordenada por meses_min ascendente:
        [{"meses_min": 1, "nombre": "AZUL", "color": "#1E88E5", "corte": false}, ...]
    """
    pagado = float(monto_pagado or 0) >= float(total_a_pagar or 0)
    if pagado:
        return {"nombre": "PAGADO", "color": "#4CAF50", "corte": False}

    mora_ord = sorted(config_mora, key=lambda m: m["meses_min"], reverse=True)
    for nivel in mora_ord:
        if meses_adeudados >= nivel["meses_min"]:
            return {
                "nombre": nivel["nombre"],
                "color": nivel["color"],
                "corte": nivel.get("corte", False),
            }
    # Por defecto el primero
    return {
        "nombre": mora_ord[-1]["nombre"],
        "color": mora_ord[-1]["color"],
        "corte": False,
    }


# ---------------------------------------------------------------------------
# Número en letras (español, para el "Son: ... SOLES")
# ---------------------------------------------------------------------------

_UNIDADES = [
    "", "UN", "DOS", "TRES", "CUATRO", "CINCO",
    "SEIS", "SIETE", "OCHO", "NUEVE", "DIEZ",
    "ONCE", "DOCE", "TRECE", "CATORCE", "QUINCE",
    "DIECISÉIS", "DIECISIETE", "DIECIOCHO", "DIECINUEVE", "VEINTE",
]
_DECENAS = [
    "", "DIEZ", "VEINTE", "TREINTA", "CUARENTA", "CINCUENTA",
    "SESENTA", "SETENTA", "OCHENTA", "NOVENTA",
]
_CENTENAS = [
    "", "CIEN", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS",
    "QUINIENTOS", "SEISCIENTOS", "SETECIENTOS", "OCHOCIENTOS", "NOVECIENTOS",
]


def _menos_de_mil(n: int) -> str:
    if n == 0:
        return ""
    if n <= 20:
        return _UNIDADES[n]
    if n < 100:
        d, u = divmod(n, 10)
        if u == 0:
            return _DECENAS[d]
        if 21 <= n <= 29:
            # Compuestos del veinte: veintiuno, veintidós, veintitrés...
            _VEINTI = ["", "VEINTIUNO", "VEINTIDÓS", "VEINTITRÉS",
                       "VEINTICUATRO", "VEINTICINCO", "VEINTISÉIS",
                       "VEINTISIETE", "VEINTIOCHO", "VEINTINUEVE"]
            return _VEINTI[u]
        return _DECENAS[d] + " Y " + _UNIDADES[u]
    c, resto = divmod(n, 100)
    if n == 100:
        return "CIEN"
    base = _CENTENAS[c]
    if c == 1:
        base = "CIENTO"
    if resto == 0:
        return base
    return base + " " + _menos_de_mil(resto)


def numero_a_letras(monto: float) -> str:
    """Convierte un monto en soles a texto en mayúsculas.

    Ejemplos:
        17.50 → 'DIECISIETE 50/100 SOLES'
        47.40 → 'CUARENTA Y SIETE 40/100 SOLES'
        0.00  → 'CERO 00/100 SOLES'
    """
    if monto < 0:
        prefijo = "MENOS "
        monto = abs(monto)
    else:
        prefijo = ""

    entero = int(monto)
    centavos = round((monto - entero) * 100)

    if entero == 0:
        parte_entera = "CERO"
    elif entero == 1:
        parte_entera = "UNO"
    else:
        miles, resto = divmod(entero, 1000)
        if miles == 0:
            parte_entera = _menos_de_mil(resto)
        elif miles == 1:
            if resto == 0:
                parte_entera = "MIL"
            else:
                parte_entera = "MIL " + _menos_de_mil(resto)
        else:
            if resto == 0:
                parte_entera = _menos_de_mil(miles) + " MIL"
            else:
                parte_entera = _menos_de_mil(miles) + " MIL " + _menos_de_mil(resto)

    return f"{prefijo}{parte_entera} {centavos:02d}/100 SOLES"


# ---------------------------------------------------------------------------
# Temporada (para el encabezado del recibo)
# ---------------------------------------------------------------------------

_MESES_ES = [
    "", "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
    "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE",
]


def periodo_a_temporada(periodo: str) -> str:
    """Convierte '2026-08' → 'AGOSTO 2026'."""
    anio, mes = periodo.split("-")
    return f"{_MESES_ES[int(mes)]} {anio}"


def fecha_a_es(fecha: str) -> str:
    """Convierte 'AAAA-MM-DD' → 'DD-MM-AAAA' para el recibo."""
    if not fecha:
        return ""
    partes = str(fecha).split("-")
    if len(partes) == 3:
        return f"{partes[2]}-{partes[1]}-{partes[0]}"
    return fecha
