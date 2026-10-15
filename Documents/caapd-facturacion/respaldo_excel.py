"""
respaldo_excel.py — Generador y lector de respaldo integral en Excel para CAAPD Ispacas.

Permite respaldar y reconstruir el 100% de la base de datos (configuración,
padrón de usuarios y documentos del mes con lecturas, novedades y recibos).
"""
from __future__ import annotations
import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

VERSION_FORMATO = "2.0"


def generar_respaldo_excel(
    config: Dict[str, Any],
    usuarios: Dict[str, Dict[str, Any]],
    mes_docs: Dict[str, Dict[str, Any]],
    periodo: Optional[str] = None,
    ruta_archivo: Optional[Path | str] = None,
) -> Path:
    """Genera un archivo Excel completo con todo lo necesario para reconstruir el sistema.

    Hojas:
    1. LEEME: metadatos, checksum numérico, versión e instrucciones.
    2. Una hoja por cada Sector: planilla con fórmulas y bloque gris técnico para restauración.
    3. USUARIOS: Padrón completo de usuarios.
    4. CONFIG: JSON crudo y tablas legibles de configuración general.
    """
    mes_act = config.get("mes_actual") or {}
    periodo_obj = periodo or mes_act.get("periodo") or datetime.date.today().strftime("%Y-%m")

    wb = openpyxl.Workbook()

    # Estilos compartidos
    fuente_titulo = Font(name="Arial", size=13, bold=True, color="0F172A")
    fuente_sub = Font(name="Arial", size=10, italic=True, color="475569")
    fuente_encabezado = Font(name="Arial", size=10, bold=True, color="FFFFFF")
    fuente_datos = Font(name="Arial", size=10, color="0F172A")
    fuente_gris = Font(name="Arial", size=9, color="334155")

    fill_azul = PatternFill(start_color="0369A1", end_color="0369A1", fill_type="solid")
    fill_verde = PatternFill(start_color="15803D", end_color="15803D", fill_type="solid")
    fill_gris = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
    fill_bloque_restaurar = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

    borde_fino = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )

    # -----------------------------------------------------------------------
    # 1. HOJA LEEME
    # -----------------------------------------------------------------------
    ws_leeme = wb.active
    ws_leeme.title = "LEEME"

    suma_total_pagar = sum(float(d.get("total_a_pagar") or 0.0) for d in mes_docs.values())
    total_usuarios = len(usuarios)
    total_docs_mes = len(mes_docs)
    fecha_generacion = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    ws_leeme["A1"] = "CAAPD ISPACAS — ARCHIVO DE RESPALDO INTEGRAL"
    ws_leeme["A1"].font = fuente_titulo
    ws_leeme["A2"] = "Este archivo contiene la copia completa de la base de datos para contingencia y restauración."
    ws_leeme["A2"].font = fuente_sub

    filas_leeme = [
        ("Versión del Formato", VERSION_FORMATO),
        ("Fecha de Generación", fecha_generacion),
        ("Periodo Respaldado", periodo_obj),
        ("Estado del Mes", (mes_act.get("estado") or "ABIERTO").upper()),
        ("Total Usuarios Padrón", total_usuarios),
        ("Total Documentos Mes", total_docs_mes),
        ("Suma Total a Pagar (S/.)", round(suma_total_pagar, 2)),
        ("Checksum Verificación", f"{total_docs_mes}_{round(suma_total_pagar, 2):.2f}"),
    ]

    ws_leeme.cell(row=4, column=1, value="PARÁMETRO").font = fuente_encabezado
    ws_leeme.cell(row=4, column=1).fill = fill_azul
    ws_leeme.cell(row=4, column=2, value="VALOR").font = fuente_encabezado
    ws_leeme.cell(row=4, column=2).fill = fill_azul

    for idx, (param, val) in enumerate(filas_leeme, start=5):
        c1 = ws_leeme.cell(row=idx, column=1, value=param)
        c1.font = Font(name="Arial", size=10, bold=True)
        c1.border = borde_fino
        c2 = ws_leeme.cell(row=idx, column=2, value=val)
        c2.font = fuente_datos
        c2.border = borde_fino
        if param == "Suma Total a Pagar (S/.)":
            c2.number_format = '"S/. "#,##0.00'

    ws_leeme.cell(row=15, column=1, value="INSTRUCCIONES DE RESTAURACIÓN:").font = Font(name="Arial", size=11, bold=True, color="1E3A8A")
    instrucciones = [
        "1. Para restaurar automáticamente ejecute:",
        f"   python scripts/restaurar_excel.py --archivo respaldos/RESPALDO_{periodo_obj}.xlsx",
        "2. El script valida los conteos y la suma de control de esta hoja antes y después de restaurar.",
        "3. Las hojas por sector contienen a la derecha un bloque gris con los datos técnicos para reconstrucción exacta.",
        "4. No altere los valores de ID Usuario ni las columnas del bloque gris para garantizar consistencia.",
    ]
    for i, inst in enumerate(instrucciones, start=16):
        ws_leeme.cell(row=i, column=1, value=inst).font = Font(name="Arial", size=10, color="334155")

    # -----------------------------------------------------------------------
    # 2. HOJAS POR SECTOR
    # -----------------------------------------------------------------------
    sectores_config = config.get("sectores") or []
    # Agrupar documentos por sector
    docs_por_sector: Dict[str, List[Dict[str, Any]]] = {}
    for uid, doc in mes_docs.items():
        sec = doc.get("sector") or "SIN SECTOR"
        d_copy = dict(doc)
        d_copy["id_usuario"] = uid
        docs_por_sector.setdefault(sec, []).append(d_copy)

    # Asegurar que aparezcan los sectores del config aunque estén vacíos
    todos_sectores = list(sectores_config)
    for s in docs_por_sector:
        if s not in todos_sectores:
            todos_sectores.append(s)

    encabezados_visibles = [
        "Fecha Lect.", "Conexión", "N° Medidor", "Titular / Beneficiario",
        "Dirección", "Lect. Anterior", "Lect. Actual", "Consumo (m³)",
        "Observación", "Nota", "N° Recibo", "Deuda Ant. (S/.)",
        "Total Pagar (S/.)", "Meses", "Monto Pagado (S/.)", "Fecha Pago",
    ]
    encabezados_restaurar = [
        "ID Usuario", "Fecha Anterior", "Consumo Anterior", "Estado Lectura",
        "Registrado Por", "Categoría", "Historial m³", "Consumo Total m³",
        "Monto Agua", "Monto Desagüe", "Cargo Fijo", "IGV", "Redondeo",
    ]

    for sec in todos_sectores:
        ws_sec = wb.create_sheet(title=sec[:31])  # Excel max sheet title 31 chars
        ws_sec["A1"] = f"CAAPD ISPACAS — PLANILLA SECTOR: {sec} — PERIODO {periodo_obj}"
        ws_sec["A1"].font = fuente_titulo

        # Fila 3: Encabezados Visibles
        for col_idx, enc in enumerate(encabezados_visibles, start=1):
            cell = ws_sec.cell(row=3, column=col_idx, value=enc)
            cell.font = fuente_encabezado
            cell.fill = fill_azul
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        # Fila 3: Encabezados Técnicos (Bloque Gris)
        inicio_gris = len(encabezados_visibles) + 1
        for col_idx, enc in enumerate(encabezados_restaurar, start=inicio_gris):
            cell = ws_sec.cell(row=3, column=col_idx, value=enc)
            cell.font = Font(name="Arial", size=9, bold=True, color="1E293B")
            cell.fill = fill_gris
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        items_sec = docs_por_sector.get(sec, [])
        items_sec.sort(key=lambda x: str(x.get("nombre") or "").upper())

        fila_act = 4
        for d in items_sec:
            meds = d.get("medidores") or []
            if not meds:
                meds = [{}]  # Al menos una fila

            tot_pagar = float(d.get("total_a_pagar") or 0.0)
            m_pagado = float(d.get("monto_pagado") or 0.0)
            deuda_ant = float(d.get("deuda_anterior") or 0.0)
            meses = int(d.get("meses_adeudados") or 1)
            rec_nro = d.get("nro_recibo")
            hist_str = ",".join(str(h) for h in d.get("historial_m3", []))

            for m_idx, m in enumerate(meds):
                l_ant = m.get("lectura_anterior")
                l_act = m.get("lectura_actual")

                ws_sec.cell(row=fila_act, column=1, value=m.get("fecha_lectura") or "").border = borde_fino
                ws_sec.cell(row=fila_act, column=2, value=str(d.get("nro_conexion") or "")).border = borde_fino
                ws_sec.cell(row=fila_act, column=3, value=str(m.get("nro_medidor") or "")).border = borde_fino
                ws_sec.cell(row=fila_act, column=4, value=str(d.get("nombre") or "")).border = borde_fino
                ws_sec.cell(row=fila_act, column=5, value=str(d.get("direccion") or "")).border = borde_fino
                
                c_ant = ws_sec.cell(row=fila_act, column=6, value=l_ant)
                c_ant.border = borde_fino
                c_act = ws_sec.cell(row=fila_act, column=7, value=l_act)
                c_act.border = borde_fino

                # Consumo con fórmula simple si ambos existen
                c_con = ws_sec.cell(row=fila_act, column=8)
                if l_act is not None and l_ant is not None:
                    c_con.value = f"=IF(ISBLANK(G{fila_act}),\"\",G{fila_act}-F{fila_act})"
                else:
                    c_con.value = ""
                c_con.border = borde_fino

                ws_sec.cell(row=fila_act, column=9, value=str(m.get("novedad") or "")).border = borde_fino
                ws_sec.cell(row=fila_act, column=10, value=str(m.get("nota") or "")).border = borde_fino

                # Campos de recibo y pago solo en la primera fila de la persona
                if m_idx == 0:
                    ws_sec.cell(row=fila_act, column=11, value=str(rec_nro) if rec_nro else "").border = borde_fino
                    c_d = ws_sec.cell(row=fila_act, column=12, value=deuda_ant)
                    c_d.number_format = '"S/. "#,##0.00'
                    c_d.border = borde_fino

                    c_tot = ws_sec.cell(row=fila_act, column=13, value=tot_pagar)
                    c_tot.number_format = '"S/. "#,##0.00'
                    c_tot.border = borde_fino

                    ws_sec.cell(row=fila_act, column=14, value=meses).border = borde_fino

                    c_pag = ws_sec.cell(row=fila_act, column=15, value=m_pagado)
                    c_pag.number_format = '"S/. "#,##0.00'
                    c_pag.border = borde_fino

                    ws_sec.cell(row=fila_act, column=16, value=str(d.get("fecha_pago") or "")).border = borde_fino
                else:
                    for col_c in range(11, 17):
                        ws_sec.cell(row=fila_act, column=col_c, value="").border = borde_fino

                # Bloque Gris para Restaurar
                ws_sec.cell(row=fila_act, column=inicio_gris, value=str(d.get("id_usuario") or "")).border = borde_fino
                ws_sec.cell(row=fila_act, column=inicio_gris + 1, value=str(m.get("fecha_anterior") or "")).border = borde_fino
                ws_sec.cell(row=fila_act, column=inicio_gris + 2, value=m.get("consumo_anterior")).border = borde_fino
                ws_sec.cell(row=fila_act, column=inicio_gris + 3, value=str(m.get("estado_lectura") or "")).border = borde_fino
                ws_sec.cell(row=fila_act, column=inicio_gris + 4, value=str(m.get("registrado_por") or "")).border = borde_fino
                ws_sec.cell(row=fila_act, column=inicio_gris + 5, value=str(d.get("codigo_categoria") or "A")).border = borde_fino
                ws_sec.cell(row=fila_act, column=inicio_gris + 6, value=hist_str).border = borde_fino
                ws_sec.cell(row=fila_act, column=inicio_gris + 7, value=d.get("consumo_total_m3")).border = borde_fino
                ws_sec.cell(row=fila_act, column=inicio_gris + 8, value=d.get("monto_agua")).border = borde_fino
                ws_sec.cell(row=fila_act, column=inicio_gris + 9, value=d.get("monto_desague")).border = borde_fino
                ws_sec.cell(row=fila_act, column=inicio_gris + 10, value=d.get("cargo_fijo")).border = borde_fino
                ws_sec.cell(row=fila_act, column=inicio_gris + 11, value=d.get("igv")).border = borde_fino
                ws_sec.cell(row=fila_act, column=inicio_gris + 12, value=d.get("redondeo")).border = borde_fino

                for col_c in range(inicio_gris, inicio_gris + len(encabezados_restaurar)):
                    ws_sec.cell(row=fila_act, column=col_c).fill = fill_bloque_restaurar

                fila_act += 1

    # -----------------------------------------------------------------------
    # 3. HOJA USUARIOS
    # -----------------------------------------------------------------------
    ws_usr = wb.create_sheet(title="USUARIOS")
    ws_usr["A1"] = "CAAPD ISPACAS — PADRÓN MAESTRO DE USUARIOS"
    ws_usr["A1"].font = fuente_titulo

    encabezados_usuarios = [
        "id_usuario", "nro_conexion", "nombre", "sector",
        "direccion", "codigo_categoria", "activo", "medidores"
    ]
    for col_idx, enc in enumerate(encabezados_usuarios, start=1):
        cell = ws_usr.cell(row=3, column=col_idx, value=enc)
        cell.font = fuente_encabezado
        cell.fill = fill_verde
        cell.alignment = Alignment(horizontal="center", vertical="center")

    usuarios_ordenados = sorted(usuarios.items(), key=lambda x: str(x[1].get("nombre") or "").upper())
    for r_idx, (uid, u) in enumerate(usuarios_ordenados, start=4):
        meds_lista = u.get("medidores") or []
        meds_str = ",".join(str(m) if isinstance(m, str) else str(m.get("nro_medidor", "")) for m in meds_lista)

        ws_usr.cell(row=r_idx, column=1, value=str(uid)).border = borde_fino
        ws_usr.cell(row=r_idx, column=2, value=str(u.get("nro_conexion") or "")).border = borde_fino
        ws_usr.cell(row=r_idx, column=3, value=str(u.get("nombre") or "")).border = borde_fino
        ws_usr.cell(row=r_idx, column=4, value=str(u.get("sector") or "")).border = borde_fino
        ws_usr.cell(row=r_idx, column=5, value=str(u.get("direccion") or "")).border = borde_fino
        ws_usr.cell(row=r_idx, column=6, value=str(u.get("codigo_categoria") or "A")).border = borde_fino
        ws_usr.cell(row=r_idx, column=7, value="SI" if u.get("activo", True) else "NO").border = borde_fino
        ws_usr.cell(row=r_idx, column=8, value=meds_str).border = borde_fino

    # -----------------------------------------------------------------------
    # 4. HOJA CONFIG
    # -----------------------------------------------------------------------
    ws_cfg = wb.create_sheet(title="CONFIG")
    ws_cfg["A1"] = "CAAPD ISPACAS — CONFIGURACIÓN DEL SISTEMA"
    ws_cfg["A1"].font = fuente_titulo

    # Celda JSON Crudo para reconstrucción byte por byte
    ws_cfg["A3"] = "JSON_CONFIG_COMPLETO"
    ws_cfg["A3"].font = fuente_encabezado
    ws_cfg["A3"].fill = fill_azul
    raw_json = json.dumps(config, indent=2, ensure_ascii=False)
    ws_cfg["A4"] = raw_json
    ws_cfg["A4"].font = Font(name="Courier New", size=9)
    ws_cfg.column_dimensions["A"].width = 50

    # Tablas legibles al lado
    ws_cfg["C3"] = "PARAMETRO"
    ws_cfg["D3"] = "VALOR"
    ws_cfg["C3"].fill = fill_verde
    ws_cfg["C3"].font = fuente_encabezado
    ws_cfg["D3"].fill = fill_verde
    ws_cfg["D3"].font = fuente_encabezado

    ws_cfg["C4"] = "Último Recibo"
    ws_cfg["D4"] = config.get("ultimo_recibo", 0)
    ws_cfg["C5"] = "Periodo Actual"
    ws_cfg["D5"] = mes_act.get("periodo", "")
    ws_cfg["C6"] = "Estado Mes Actual"
    ws_cfg["D6"] = mes_act.get("estado", "")
    ws_cfg["C7"] = "Fecha Emisión"
    ws_cfg["D7"] = mes_act.get("fecha_emision", "")
    ws_cfg["C8"] = "Fecha Vencimiento"
    ws_cfg["D8"] = mes_act.get("fecha_vencimiento", "")
    ws_cfg["C9"] = "Sectores"
    ws_cfg["D9"] = ", ".join(config.get("sectores") or [])

    # Autoajuste de columnas en todas las hojas
    for ws in wb.worksheets:
        for col in ws.columns:
            letra = get_column_letter(col[0].column)
            if ws.title == "CONFIG" and letra == "A":
                continue
            max_len = max(len(str(c.value or "")) for c in col)
            ws.column_dimensions[letra].width = min(max(max_len + 3, 10), 45)

    # Guardar
    if ruta_archivo:
        destino = Path(ruta_archivo)
    else:
        try:
            import rutas
            destino = rutas.ruta_respaldos(f"RESPALDO_{periodo_obj}.xlsx")
        except Exception:
            destino = Path(f"respaldos/RESPALDO_{periodo_obj}.xlsx")

    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(destino))
    return destino


def leer_respaldo_excel(ruta_archivo: Path | str) -> Dict[str, Any]:
    """Lee y reconstruye la configuración, usuarios y documentos del mes desde un Excel de respaldo.

    Valida checksum y versión del LEEME.
    """
    p = Path(ruta_archivo)
    if not p.exists():
        raise FileNotFoundError(f"No se encontró el archivo de respaldo: {p}")

    wb = openpyxl.load_workbook(str(p), data_only=True)

    # 1. Leer LEEME
    if "LEEME" not in wb.sheetnames:
        raise ValueError("El archivo no es un respaldo válido de CAAPD (falta la hoja LEEME).")

    ws_leeme = wb["LEEME"]
    metadatos = {}
    for r in range(5, 15):
        k = ws_leeme.cell(row=r, column=1).value
        v = ws_leeme.cell(row=r, column=2).value
        if k:
            metadatos[str(k).strip()] = v

    periodo = metadatos.get("Periodo Respaldado") or "2026-10"
    total_docs_esperado = int(metadatos.get("Total Documentos Mes") or 0)
    suma_esperada = float(metadatos.get("Suma Total a Pagar (S/.)") or 0.0)

    # 2. Leer CONFIG
    config = {}
    if "CONFIG" in wb.sheetnames:
        ws_cfg = wb["CONFIG"]
        raw_json = ws_cfg["A4"].value
        if raw_json and isinstance(raw_json, str) and raw_json.strip().startswith("{"):
            try:
                config = json.loads(raw_json)
            except Exception:
                pass

    # 3. Leer USUARIOS
    usuarios: Dict[str, Dict[str, Any]] = {}
    if "USUARIOS" in wb.sheetnames:
        ws_usr = wb["USUARIOS"]
        for r in range(4, ws_usr.max_row + 1):
            uid = ws_usr.cell(row=r, column=1).value
            if not uid:
                continue
            uid = str(uid).strip()
            meds_raw = str(ws_usr.cell(row=r, column=8).value or "")
            meds_list = [m.strip() for m in meds_raw.split(",") if m.strip()]

            usuarios[uid] = {
                "id_usuario": uid,
                "nro_conexion": str(ws_usr.cell(row=r, column=2).value or "").strip(),
                "nombre": str(ws_usr.cell(row=r, column=3).value or "").strip(),
                "sector": str(ws_usr.cell(row=r, column=4).value or "").strip(),
                "direccion": str(ws_usr.cell(row=r, column=5).value or "").strip(),
                "codigo_categoria": str(ws_usr.cell(row=r, column=6).value or "A").strip(),
                "activo": str(ws_usr.cell(row=r, column=7).value or "").upper() == "SI",
                "medidores": meds_list,
            }

    # 4. Leer Documentos del Mes por Sector
    mes_docs: Dict[str, Dict[str, Any]] = {}
    hojas_excluidas = {"LEEME", "USUARIOS", "CONFIG"}

    for s_name in wb.sheetnames:
        if s_name in hojas_excluidas:
            continue
        ws_sec = wb[s_name]

        # Determinar índice del bloque gris
        inicio_gris = 17  # Columna Q por defecto

        for r in range(4, ws_sec.max_row + 1):
            uid = ws_sec.cell(row=r, column=inicio_gris).value
            if not uid:
                # Intentar leer por DNI si no está en la columna Q
                continue
            uid = str(uid).strip()

            n_med = ws_sec.cell(row=r, column=3).value
            n_med_str = str(n_med).strip() if n_med is not None else ""

            l_ant = ws_sec.cell(row=r, column=6).value
            l_act = ws_sec.cell(row=r, column=7).value
            f_lect = ws_sec.cell(row=r, column=1).value
            nov = ws_sec.cell(row=r, column=9).value
            nota = ws_sec.cell(row=r, column=10).value

            # Campos del medidor
            med_obj = {
                "nro_medidor": n_med_str,
                "lectura_anterior": int(l_ant) if l_ant is not None and str(l_ant).isdigit() else 0,
                "lectura_actual": int(l_act) if l_act is not None and str(l_act).isdigit() else None,
                "fecha_lectura": str(f_lect).strip() if f_lect else None,
                "novedad": str(nov).strip() if nov else "NORMAL",
                "nota": str(nota).strip() if nota else "",
                "fecha_anterior": str(ws_sec.cell(row=r, column=inicio_gris + 1).value or "").strip() or None,
                "consumo_anterior": ws_sec.cell(row=r, column=inicio_gris + 2).value,
                "estado_lectura": str(ws_sec.cell(row=r, column=inicio_gris + 3).value or "LEIDO").strip(),
                "registrado_por": str(ws_sec.cell(row=r, column=inicio_gris + 4).value or "ADMIN").strip(),
            }

            if uid not in mes_docs:
                rec_val = ws_sec.cell(row=r, column=11).value
                d_ant_val = ws_sec.cell(row=r, column=12).value
                tot_val = ws_sec.cell(row=r, column=13).value
                meses_val = ws_sec.cell(row=r, column=14).value
                pag_val = ws_sec.cell(row=r, column=15).value
                f_pag_val = ws_sec.cell(row=r, column=16).value

                hist_raw = str(ws_sec.cell(row=r, column=inicio_gris + 6).value or "")
                hist_list = [float(x) for x in hist_raw.split(",") if x.strip()]

                mes_docs[uid] = {
                    "id_usuario": uid,
                    "nro_conexion": str(ws_sec.cell(row=r, column=2).value or "").strip(),
                    "nombre": str(ws_sec.cell(row=r, column=4).value or "").strip(),
                    "sector": s_name,
                    "direccion": str(ws_sec.cell(row=r, column=5).value or "").strip(),
                    "codigo_categoria": str(ws_sec.cell(row=r, column=inicio_gris + 5).value or "A").strip(),
                    "medidores": [med_obj] if n_med_str else [],
                    "historial_m3": hist_list,
                    "consumo_total_m3": ws_sec.cell(row=r, column=inicio_gris + 7).value,
                    "nro_recibo": str(rec_val).strip() if rec_val else None,
                    "deuda_anterior": float(d_ant_val or 0.0),
                    "total_a_pagar": float(tot_val or 0.0) if tot_val is not None else None,
                    "meses_adeudados": int(meses_val or 1),
                    "monto_pagado": float(pag_val or 0.0),
                    "fecha_pago": str(f_pag_val).strip() if f_pag_val else None,
                    "monto_agua": ws_sec.cell(row=r, column=inicio_gris + 8).value,
                    "monto_desague": ws_sec.cell(row=r, column=inicio_gris + 9).value,
                    "cargo_fijo": ws_sec.cell(row=r, column=inicio_gris + 10).value,
                    "igv": ws_sec.cell(row=r, column=inicio_gris + 11).value,
                    "redondeo": ws_sec.cell(row=r, column=inicio_gris + 12).value,
                }
            else:
                # Si el usuario tiene múltiples medidores, agregar a la lista
                if n_med_str:
                    mes_docs[uid]["medidores"].append(med_obj)

    # Validar sumas
    suma_reconstruida = sum(float(d.get("total_a_pagar") or 0.0) for d in mes_docs.values())
    coincide_suma = abs(suma_reconstruida - suma_esperada) < 0.05

    return {
        "metadatos": metadatos,
        "periodo": periodo,
        "config": config,
        "usuarios": usuarios,
        "mes_docs": mes_docs,
        "validacion": {
            "total_docs_esperado": total_docs_esperado,
            "total_docs_obtenido": len(mes_docs),
            "suma_esperada": suma_esperada,
            "suma_obtenida": round(suma_reconstruida, 2),
            "coincide": coincide_suma and (len(mes_docs) == total_docs_esperado or total_docs_esperado == 0),
        },
    }
