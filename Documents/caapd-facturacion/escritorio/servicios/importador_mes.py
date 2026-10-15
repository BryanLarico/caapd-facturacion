"""
servicios/importador_mes.py — Servicio de importación de padrones y lecturas mensuales desde Excel.

Permite:
1. Importar archivos Excel (.xlsx) con lecturas históricas (ej. meses anteriores) para
   poblar el historial de consumos que alimenta el histograma de 6 meses en los recibos.
2. Modo contingencia/restauración: volver a cargar un mes exportado o corregido externamente.
3. Actualiza automáticamente el padrón de usuarios maestro con cualquier cliente nuevo.
"""
from __future__ import annotations
import datetime
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openpyxl

import calculos
import codigos
import firebase_client as fb
from respaldo import on_datos_cambiados


def normalizar_cabecera(cab: str) -> str:
    """Normaliza texto de cabecera a minúsculas sin acentos ni espacios extra."""
    s = str(cab or "").lower().strip()
    s = s.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    s = re.sub(r"[^a-z0-9]", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def mapear_columnas(fila_cabeceras: List[Any]) -> Dict[str, int]:
    """Identifica las columnas del Excel por coincidencia EXACTA de encabezado normalizado.

    Evita colisiones entre Lect. Anterior / Fecha Anterior / Consumo Anterior / Deuda Ant.
    y entre Lect. Actual / Deuda Actual.
    """
    mapeo = {}
    for idx, cell in enumerate(fila_cabeceras):
        k = normalizar_cabecera(cell)
        if not k:
            continue

        if k in ("conexion", "nro_conexion", "n_conexion", "cod_con", "nro_con"):
            mapeo["conexion"] = idx
        elif k in ("dni", "id_usuario", "dni_id", "documento"):
            mapeo["dni"] = idx
        elif k in ("nombre", "titular_beneficiario", "titular", "usuario", "abonado", "persona"):
            mapeo["nombre"] = idx
        elif k in ("sector", "barrio"):
            mapeo["sector"] = idx
        elif k in ("direccion", "calle", "lugar"):
            mapeo["direccion"] = idx
        elif k in ("categoria", "codigo_categoria", "cat"):
            mapeo["categoria"] = idx
        elif k in ("n_medidor", "nro_medidor", "medidor", "num_med"):
            mapeo["medidor"] = idx
        elif k in ("lect_anterior", "lectura_anterior", "lec_ant", "anterior"):
            mapeo["anterior"] = idx
            mapeo["lectura_anterior"] = idx
        elif k in ("lect_actual", "lectura_actual", "lec_act", "actual"):
            mapeo["actual"] = idx
            mapeo["lectura_actual"] = idx
        elif k in ("consumo_m3", "consumo"):
            mapeo["consumo"] = idx
        elif k in ("observacion", "novedad", "estado_med"):
            mapeo["novedad"] = idx
        elif k in ("nota", "detalle", "comentario"):
            mapeo["nota"] = idx
        elif k in ("n_recibo", "nro_recibo", "recibo"):
            mapeo["nro_recibo"] = idx
        elif k in ("deuda_ant_s", "deuda_ant", "deuda_anterior"):
            mapeo["deuda_ant"] = idx
            mapeo["deuda_anterior"] = idx
        elif k in ("deuda_actual_s", "deuda_actual"):
            mapeo["deuda_actual"] = idx
        elif k in ("total_pagar_s", "total_pagar", "total_a_pagar"):
            mapeo["total_pagar"] = idx
            mapeo["total_a_pagar"] = idx
        elif k in ("meses", "meses_adeudados"):
            mapeo["meses"] = idx
        elif k == "pago":
            mapeo["pago"] = idx
        elif k in ("pagado", "monto_pagado_s", "monto_pagado"):
            mapeo["monto_pagado"] = idx
        elif k in ("fecha_pago", "f_pago"):
            mapeo["fecha_pago"] = idx
        elif k in ("fecha_anterior", "f_anterior"):
            mapeo["fecha_anterior"] = idx
        elif k in ("consumo_anterior", "c_anterior"):
            mapeo["consumo_anterior"] = idx
        elif k in ("estado_lectura",):
            mapeo["estado_lectura"] = idx
        elif k in ("registrado_por", "lector"):
            mapeo["registrado_por"] = idx
        elif k in ("historial_m3", "historial"):
            mapeo["historial_m3"] = idx
        elif k in ("consumo_total_m3", "consumo_total"):
            mapeo["consumo_total_m3"] = idx
    return mapeo


def importar_mes_desde_excel(
    ruta_excel: str | Path,
    periodo: str,
    es_mes_activo: bool = False,
    fecha_emision: Optional[str] = None,
    fecha_vencimiento: Optional[str] = None,
) -> Dict[str, Any]:
    """Lee un Excel y genera/actualiza la colección mes_aaaa-mm en Firestore."""
    periodo = periodo.strip()
    ruta_path = Path(ruta_excel)
    if not ruta_path.exists():
        raise FileNotFoundError(f"No se encontró el archivo: {ruta_excel}")

    wb = openpyxl.load_workbook(str(ruta_path), data_only=True)
    ws = wb.active

    filas = list(ws.iter_rows(values_only=True))
    if len(filas) < 2:
        raise ValueError("El archivo Excel no contiene filas de datos.")

    cabeceras = filas[0]
    mapa = mapear_columnas(list(cabeceras))

    if "conexion" not in mapa and "dni" not in mapa:
        raise ValueError("El Excel debe tener al menos la columna 'Conexión' o 'DNI/ID'.")

    # Cargar usuarios existentes de Firestore
    usuarios_maestro = fb.cargar_usuarios(forzar=True)
    nuevos_usuarios_a_guardar: Dict[str, Dict[str, Any]] = {}

    # Agrupar registros por usuario
    usuarios_mes: Dict[str, Dict[str, Any]] = {}
    total_medidores = 0

    hoy_str = datetime.date.today().isoformat()
    emision_str = fecha_emision or hoy_str
    venc_str = fecha_vencimiento or (datetime.date.today() + datetime.timedelta(days=15)).isoformat()

    for idx, fila in enumerate(filas[1:], start=2):
        # Ignorar filas completamente vacías
        if not any(fila):
            continue

        raw_con = fila[mapa["conexion"]] if "conexion" in mapa and mapa["conexion"] < len(fila) else ""
        raw_dni = fila[mapa["dni"]] if "dni" in mapa and mapa["dni"] < len(fila) else ""
        raw_nom = fila[mapa["nombre"]] if "nombre" in mapa and mapa["nombre"] < len(fila) else ""
        raw_sec = fila[mapa["sector"]] if "sector" in mapa and mapa["sector"] < len(fila) else "BARRIO DE CHAUPI"
        raw_dir = fila[mapa["direccion"]] if "direccion" in mapa and mapa["direccion"] < len(fila) else "S/N"
        raw_cat = fila[mapa["categoria"]] if "categoria" in mapa and mapa["categoria"] < len(fila) else "A"
        raw_med = fila[mapa["medidor"]] if "medidor" in mapa and mapa["medidor"] < len(fila) else ""
        raw_ant = fila[mapa["anterior"]] if "anterior" in mapa and mapa["anterior"] < len(fila) else 0
        raw_act = fila[mapa["actual"]] if "actual" in mapa and mapa["actual"] < len(fila) else None
        raw_nov = fila[mapa["novedad"]] if "novedad" in mapa and mapa["novedad"] < len(fila) else "NORMAL"
        raw_not = fila[mapa["nota"]] if "nota" in mapa and mapa["nota"] < len(fila) else ""

        # Normalizaciones
        con_norm = codigos.normalizar_conexion(raw_con) if raw_con else "000000"
        med_norm = codigos.normalizar_medidor(raw_med) if raw_med else ""

        # Identificar DNI / ID
        if raw_dni:
            dni_str = str(raw_dni).strip()
            if dni_str.startswith("SD-") or "-" in dni_str:
                uid = dni_str
            else:
                uid = codigos.normalizar_dni(dni_str)
        else:
            # Buscar en usuarios_maestro por conexion
            u_match = next((u for u in usuarios_maestro.values() if u.get("nro_conexion") == con_norm), None)
            if u_match:
                uid = str(u_match.get("_id") or u_match.get("id_usuario"))
            else:
                uid = f"SD-{int(con_norm):03d}" if con_norm.isdigit() else f"SD-{idx:03d}"

        # Lecturas
        try:
            ant_val = int(raw_ant) if raw_ant is not None and str(raw_ant).strip() != "" else 0
        except Exception:
            ant_val = 0

        act_val = None
        if raw_act is not None and str(raw_act).strip() != "":
            try:
                act_val = int(raw_act)
            except Exception:
                act_val = None

        nov_val = str(raw_nov or "NORMAL").strip().upper()
        if not nov_val:
            nov_val = "NORMAL"

        nota_val = str(raw_not or "").strip()

        # Determinar estado
        est_val = "LEIDO" if act_val is not None else "PENDIENTE"
        if "CERRADA" in nov_val or "SIN_ACCESO" in nov_val:
            est_val = "SIN_ACCESO"

        consumo_ant = None
        if act_val is not None:
            try:
                c = calculos.consumo_medidor(ant_val, act_val, nov_val)
                consumo_ant = c
            except Exception:
                consumo_ant = max(0, act_val - ant_val)

        item_medidor = {
            "nro_medidor": med_norm or f"M-{con_norm}",
            "lectura_anterior": ant_val,
            "fecha_anterior": None,
            "consumo_anterior": consumo_ant,
            "lectura_actual": act_val,
            "fecha_lectura": hoy_str if act_val is not None else None,
            "estado_lectura": est_val,
            "novedad": nov_val,
            "nota": nota_val,
            "registrado_por": "EXCEL_IMPORT",
        }

        nombre_limpio = str(raw_nom or "").strip().upper() or "ABONADO SIN NOMBRE"
        sector_limpio = str(raw_sec or "BARRIO DE CHAUPI").strip().upper()
        dir_limpia = str(raw_dir or "S/N").strip()
        cat_limpia = str(raw_cat or "A").strip().upper()

        # Deudas y pagos
        raw_rec = fila[mapa["nro_recibo"]] if "nro_recibo" in mapa and mapa["nro_recibo"] < len(fila) else None
        rec_str = str(raw_rec).strip() if raw_rec else None

        raw_d_ant = fila[mapa["deuda_ant"]] if "deuda_ant" in mapa and mapa["deuda_ant"] < len(fila) else 0.0
        try:
            d_ant_f = float(raw_d_ant or 0.0)
        except Exception:
            d_ant_f = 0.0

        d_act_f = 0.0
        tot_pagar_f = None
        if "deuda_actual" in mapa and mapa["deuda_actual"] < len(fila):
            try:
                d_act_f = float(fila[mapa["deuda_actual"]] or 0.0)
                tot_pagar_f = round(d_ant_f + d_act_f, 2)
            except Exception:
                tot_pagar_f = d_ant_f
        elif "total_pagar" in mapa and mapa["total_pagar"] < len(fila):
            try:
                tot_pagar_f = float(fila[mapa["total_pagar"]] or 0.0)
                d_act_f = max(0.0, round(tot_pagar_f - d_ant_f, 2))
            except Exception:
                tot_pagar_f = None

        raw_meses = fila[mapa["meses"]] if "meses" in mapa and mapa["meses"] < len(fila) else 1
        try:
            meses_int = int(raw_meses or 1)
        except Exception:
            meses_int = 1

        m_pagado_f = 0.0
        if "pago" in mapa and mapa["pago"] < len(fila):
            p_val = str(fila[mapa["pago"]] or "").strip().upper()
            if p_val in ("SI", "1", "TRUE", "PAGADO"):
                m_pagado_f = tot_pagar_f or 0.0
        elif "monto_pagado" in mapa and mapa["monto_pagado"] < len(fila):
            raw_mp = fila[mapa["monto_pagado"]]
            if str(raw_mp).strip().upper() in ("SI", "PAGADO"):
                m_pagado_f = tot_pagar_f or 0.0
            else:
                try:
                    m_pagado_f = float(raw_mp or 0.0)
                except Exception:
                    m_pagado_f = 0.0

        f_pago_str = str(fila[mapa["fecha_pago"]]).strip() if "fecha_pago" in mapa and mapa["fecha_pago"] < len(fila) and fila[mapa["fecha_pago"]] else None

        if uid not in usuarios_mes:
            usuarios_mes[uid] = {
                "nro_conexion": con_norm,
                "nombre": nombre_limpio,
                "sector": sector_limpio,
                "direccion": dir_limpia,
                "codigo_categoria": cat_limpia,
                "medidores": [item_medidor],
                "consumo_total_m3": consumo_ant if consumo_ant is not None else None,
                "historial_m3": [consumo_ant] if consumo_ant is not None else [],
                "nro_recibo": rec_str,
                "monto_agua": None,
                "monto_desague": None,
                "cargo_fijo": None,
                "deuda_anterior": d_ant_f,
                "deuda_actual": d_act_f,
                "igv": 0.0,
                "redondeo": 0.0,
                "total_a_pagar": tot_pagar_f,
                "meses_adeudados": meses_int,
                "monto_pagado": m_pagado_f,
                "fecha_pago": f_pago_str,
            }
        else:
            # Usuario con varios medidores en filas separadas
            usuarios_mes[uid]["medidores"].append(item_medidor)
            if consumo_ant is not None:
                curr_tot = usuarios_mes[uid]["consumo_total_m3"] or 0
                usuarios_mes[uid]["consumo_total_m3"] = curr_tot + consumo_ant

        total_medidores += 1

        # Si el usuario no existe en el padrón maestro, registrarlo
        if uid not in usuarios_maestro and uid not in nuevos_usuarios_a_guardar:
            nuevos_usuarios_a_guardar[uid] = {
                "nro_conexion": con_norm,
                "nombre": nombre_limpio,
                "sector": sector_limpio,
                "direccion": dir_limpia,
                "codigo_categoria": cat_limpia,
                "activo": True,
                "medidores": [med_norm] if med_norm else [],
            }
        elif uid in usuarios_maestro:
            # Asegurar que el medidor esté en su lista de medidores del padrón
            meds_user = usuarios_maestro[uid].get("medidores") or []
            if med_norm and med_norm not in meds_user:
                meds_user.append(med_norm)
                fb.actualizar_usuario(uid, {"medidores": meds_user})

    # Guardar nuevos usuarios en el padrón si los hay
    if nuevos_usuarios_a_guardar:
        fb.guardar_usuarios_lote(nuevos_usuarios_a_guardar)

    # Guardar colección mes_aaaa-mm en Firestore
    fb.guardar_mes_lote(periodo, usuarios_mes)

    # Si se marca como el mes activo del sistema
    if es_mes_activo:
        fb.actualizar_config_campo("mes_actual", {
            "periodo": periodo,
            "estado": "ABIERTO",
            "fecha_emision": emision_str,
            "fecha_vencimiento": venc_str,
        })

    fb.limpiar_cache(limpiar_config=True)

    try:
        on_datos_cambiados("importar_excel_mes", {
            "periodo": periodo,
            "usuarios": len(usuarios_mes),
            "medidores": total_medidores,
        })
    except Exception:
        pass

    return {
        "periodo": periodo,
        "usuarios_procesados": len(usuarios_mes),
        "medidores_procesados": total_medidores,
        "usuarios_nuevos_padron": len(nuevos_usuarios_a_guardar),
    }
