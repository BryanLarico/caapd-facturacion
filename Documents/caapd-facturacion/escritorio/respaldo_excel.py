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
    periodo_obj = periodo or mes_act.get(
        "periodo") or datetime.date.today().strftime("%Y-%m")

    wb = openpyxl.Workbook()

    # Estilos compartidos
    fuente_titulo = Font(name="Arial", size=13, bold=True, color="0F172A")
    fuente_sub = Font(name="Arial", size=10, italic=True, color="475569")
    fuente_encabezado = Font(name="Arial", size=10, bold=True, color="FFFFFF")
    fuente_datos = Font(name="Arial", size=10, color="0F172A")
    fuente_gris = Font(name="Arial", size=9, color="334155")

    fill_azul = PatternFill(start_color="0369A1",
                            end_color="0369A1", fill_type="solid")
    fill_verde = PatternFill(start_color="15803D",
                             end_color="15803D", fill_type="solid")
    fill_gris = PatternFill(start_color="E2E8F0",
                            end_color="E2E8F0", fill_type="solid")
    fill_bloque_restaurar = PatternFill(
        start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

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

    suma_total_pagar = sum(float(d.get("total_a_pagar") or 0.0)
                           for d in mes_docs.values())
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
        ("Checksum Verificación",
         f"{total_docs_mes}_{round(suma_total_pagar, 2):.2f}"),
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
    fila_inst = len(filas_leeme) + 6
    ws_leeme.cell(row=fila_inst, column=1, value="INSTRUCCIONES DE RESTAURACIÓN:").font = Font(
        name="Arial", size=11, bold=True, color="1E3A8A")
    instrucciones = [
        "1. Para restaurar automáticamente ejecute:",
        f"   python scripts/restaurar_excel.py --archivo respaldos/RESPALDO_{periodo_obj}.xlsx",
        "2. El script valida los conteos y la suma de control de esta hoja antes y después de restaurar.",
        "3. Las hojas por sector contienen a la derecha un bloque gris con los datos técnicos para reconstrucción exacta.",
        "4. No altere los valores de ID Usuario ni las columnas del bloque gris para garantizar consistencia.",
    ]
    for i, inst in enumerate(instrucciones, start=fila_inst + 1):
        ws_leeme.cell(row=i, column=1, value=inst).font = Font(
            name="Arial", size=10, color="334155")

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
        "Deuda Actual (S/.)", "Meses", "Pago", "Fecha Pago",
    ]
    encabezados_restaurar = [
        "ID Usuario", "Fecha Anterior", "Consumo Anterior", "Estado Lectura",
        "Registrado Por", "Categoría", "Historial m³", "Consumo Total m³",
        "Monto Agua", "Monto Desagüe", "Cargo Fijo", "IGV", "Redondeo",
        "Deuda Ant Manual",
    ]

    for sec in todos_sectores:
        # Excel max sheet title 31 chars
        ws_sec = wb.create_sheet(title=sec[:31])
        ws_sec["A1"] = f"CAAPD ISPACAS — PLANILLA SECTOR: {sec} — PERIODO {periodo_obj}"
        ws_sec["A1"].font = fuente_titulo

        # Fila 3: Encabezados Visibles
        for col_idx, enc in enumerate(encabezados_visibles, start=1):
            cell = ws_sec.cell(row=3, column=col_idx, value=enc)
            cell.font = fuente_encabezado
            cell.fill = fill_azul
            cell.alignment = Alignment(
                horizontal="center", vertical="center", wrap_text=True)

        # Fila 3: Encabezados Técnicos (Bloque Gris)
        inicio_gris = len(encabezados_visibles) + 1
        for col_idx, enc in enumerate(encabezados_restaurar, start=inicio_gris):
            cell = ws_sec.cell(row=3, column=col_idx, value=enc)
            cell.font = Font(name="Arial", size=9, bold=True, color="1E293B")
            cell.fill = fill_gris
            cell.alignment = Alignment(
                horizontal="center", vertical="center", wrap_text=True)

        items_sec = docs_por_sector.get(sec, [])
        items_sec.sort(key=lambda x: str(x.get("nombre") or "").upper())

        fila_act = 4
        for d in items_sec:
            meds = d.get("medidores") or []
            if not meds:
                meds = [{}]  # Al menos una fila

            tot_pagar = float(d.get("total_a_pagar") or 0.0)
            deuda_ant = float(d.get("deuda_anterior") or 0.0)

            # Deuda Actual = valor del mes
            if "deuda_actual" in d and d["deuda_actual"] is not None:
                deuda_act = float(d["deuda_actual"])
            else:
                deuda_act = max(0.0, round(tot_pagar - deuda_ant, 2))

            # Pago = SI o NO
            m_pagado = float(d.get("monto_pagado") or 0.0)
            pago_field = str(d.get("pago") or "").strip().upper()
            if m_pagado > 0 and (tot_pagar <= 0 or m_pagado >= tot_pagar):
                pago_str = "SI"
            elif m_pagado <= 0:
                if pago_field == "SI" and tot_pagar <= 0:
                    pago_str = "SI"
                else:
                    pago_str = "NO"
            elif pago_field in ("SI", "NO"):
                pago_str = pago_field
            else:
                pago_str = "SI" if (
                    m_pagado >= tot_pagar and tot_pagar > 0) else "NO"

            if pago_str == "SI":
                meses = 0
            else:
                meses = int(d.get("meses_adeudados") or 1)
            rec_nro = d.get("nro_recibo")
            hist_str = ",".join(str(h) for h in d.get("historial_m3", []))

            for m_idx, m in enumerate(meds):
                if not isinstance(m, dict):
                    m = {"nro_medidor": str(m)}
                l_ant = m.get("lectura_anterior")
                l_act = m.get("lectura_actual")

                ws_sec.cell(row=fila_act, column=1, value=m.get(
                    "fecha_lectura") or "").border = borde_fino
                ws_sec.cell(row=fila_act, column=2, value=str(
                    d.get("nro_conexion") or "")).border = borde_fino
                ws_sec.cell(row=fila_act, column=3, value=str(
                    m.get("nro_medidor") or "")).border = borde_fino
                ws_sec.cell(row=fila_act, column=4, value=str(
                    d.get("nombre") or "")).border = borde_fino
                ws_sec.cell(row=fila_act, column=5, value=str(
                    d.get("direccion") or "")).border = borde_fino

                c_ant = ws_sec.cell(row=fila_act, column=6, value=l_ant)
                c_ant.border = borde_fino
                c_act = ws_sec.cell(row=fila_act, column=7, value=l_act)
                c_act.border = borde_fino

                # Consumo
                c_con = ws_sec.cell(row=fila_act, column=8)
                if l_act is not None and l_ant is not None:
                    try:
                        import calculos
                        c_con.value = calculos.consumo_medidor(
                            int(l_ant), int(l_act), m.get("novedad")
                        )
                    except Exception:
                        c_con.value = max(0, int(l_act) - int(l_ant))
                else:
                    c_con.value = ""
                c_con.border = borde_fino

                ws_sec.cell(row=fila_act, column=9, value=str(
                    m.get("novedad") or "NORMAL")).border = borde_fino
                ws_sec.cell(row=fila_act, column=10, value=str(
                    m.get("nota") or "")).border = borde_fino

                # Campos de recibo y pago solo en la primera fila de la persona
                if m_idx == 0:
                    ws_sec.cell(row=fila_act, column=11, value=str(
                        rec_nro) if rec_nro else "").border = borde_fino
                    c_d = ws_sec.cell(row=fila_act, column=12, value=deuda_ant)
                    c_d.number_format = '"S/. "#,##0.00'
                    c_d.border = borde_fino

                    c_act_val = ws_sec.cell(
                        row=fila_act, column=13, value=deuda_act)
                    c_act_val.number_format = '"S/. "#,##0.00'
                    c_act_val.border = borde_fino

                    ws_sec.cell(row=fila_act, column=14,
                                value=meses).border = borde_fino

                    c_pag = ws_sec.cell(
                        row=fila_act, column=15, value=pago_str)
                    c_pag.alignment = Alignment(horizontal="center")
                    c_pag.border = borde_fino

                    fecha_pag_val = str(d.get("fecha_pago") or "") if pago_str == "SI" else ""
                    ws_sec.cell(row=fila_act, column=16, value=fecha_pag_val).border = borde_fino
                else:
                    for col_c in range(11, 17):
                        ws_sec.cell(row=fila_act, column=col_c,
                                    value="").border = borde_fino

                # Bloque Gris para Restaurar (ID Usuario en todas las filas)
                ws_sec.cell(row=fila_act, column=inicio_gris, value=str(
                    d.get("id_usuario") or "")).border = borde_fino
                ws_sec.cell(row=fila_act, column=inicio_gris + 1,
                            value=str(m.get("fecha_anterior") or "")).border = borde_fino
                ws_sec.cell(row=fila_act, column=inicio_gris + 2,
                            value=m.get("consumo_anterior")).border = borde_fino
                ws_sec.cell(row=fila_act, column=inicio_gris + 3,
                            value=str(m.get("estado_lectura") or ("LEIDO" if l_act is not None else "PENDIENTE"))).border = borde_fino
                ws_sec.cell(row=fila_act, column=inicio_gris + 4,
                            value=str(m.get("registrado_por") or ("LECTOR" if l_act is not None else ""))).border = borde_fino

                # Montos e historial técnico solo en la primera fila
                if m_idx == 0:
                    ws_sec.cell(row=fila_act, column=inicio_gris + 5,
                                value=str(d.get("codigo_categoria") or "A")).border = borde_fino
                    ws_sec.cell(row=fila_act, column=inicio_gris +
                                6, value=hist_str).border = borde_fino
                    ws_sec.cell(row=fila_act, column=inicio_gris + 7,
                                value=d.get("consumo_total_m3")).border = borde_fino
                    ws_sec.cell(row=fila_act, column=inicio_gris + 8,
                                value=d.get("monto_agua")).border = borde_fino
                    ws_sec.cell(row=fila_act, column=inicio_gris + 9,
                                value=d.get("monto_desague")).border = borde_fino
                    ws_sec.cell(row=fila_act, column=inicio_gris + 10,
                                value=d.get("cargo_fijo")).border = borde_fino
                    ws_sec.cell(row=fila_act, column=inicio_gris +
                                11, value=d.get("igv")).border = borde_fino
                    ws_sec.cell(row=fila_act, column=inicio_gris +
                                12, value=d.get("redondeo")).border = borde_fino
                    ws_sec.cell(row=fila_act, column=inicio_gris + 13,
                                value=1 if d.get("deuda_anterior_manual") else 0).border = borde_fino
                else:
                    for col_c in range(inicio_gris + 5, inicio_gris + 14):
                        ws_sec.cell(row=fila_act, column=col_c,
                                    value="").border = borde_fino

                for col_c in range(inicio_gris, inicio_gris + len(encabezados_restaurar)):
                    ws_sec.cell(
                        row=fila_act, column=col_c).fill = fill_bloque_restaurar

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

    usuarios_ordenados = sorted(
        usuarios.items(), key=lambda x: str(x[1].get("nombre") or "").upper())
    for r_idx, (uid, u) in enumerate(usuarios_ordenados, start=4):
        meds_lista = u.get("medidores") or []
        meds_str = ",".join(str(m) if isinstance(m, str) else str(
            m.get("nro_medidor", "")) for m in meds_lista)

        ws_usr.cell(row=r_idx, column=1, value=str(uid)).border = borde_fino
        ws_usr.cell(row=r_idx, column=2, value=str(
            u.get("nro_conexion") or "")).border = borde_fino
        ws_usr.cell(row=r_idx, column=3, value=str(
            u.get("nombre") or "")).border = borde_fino
        ws_usr.cell(row=r_idx, column=4, value=str(
            u.get("sector") or "")).border = borde_fino
        ws_usr.cell(row=r_idx, column=5, value=str(
            u.get("direccion") or "")).border = borde_fino
        ws_usr.cell(row=r_idx, column=6, value=str(
            u.get("codigo_categoria") or "A")).border = borde_fino
        ws_usr.cell(row=r_idx, column=7, value="SI" if u.get(
            "activo", True) else "NO").border = borde_fino
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
    try:
        wb.close()
    except Exception:
        pass
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
        raise ValueError(
            "El archivo no es un respaldo válido de CAAPD (falta la hoja LEEME).")

    ws_leeme = wb["LEEME"]
    metadatos = {}
    for r in range(4, 25):
        k = ws_leeme.cell(row=r, column=1).value
        v = ws_leeme.cell(row=r, column=2).value
        if k:
            metadatos[str(k).strip()] = v
        if k and "ARCHIVO DE PRUEBA" in str(k).upper():
            metadatos["es_prueba"] = True

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

        # Leer parámetros de la tabla auxiliar de CONFIG para complementar
        if "ultimo_recibo" not in config or not config["ultimo_recibo"]:
            val_rec = ws_cfg["D4"].value
            if val_rec is not None and str(val_rec).isdigit():
                config["ultimo_recibo"] = int(val_rec)
        mes_act = config.setdefault("mes_actual", {})
        if ws_cfg["D5"].value and not mes_act.get("periodo"):
            mes_act["periodo"] = str(ws_cfg["D5"].value).strip()
        if ws_cfg["D6"].value and not mes_act.get("estado"):
            mes_act["estado"] = str(ws_cfg["D6"].value).strip()
        if ws_cfg["D7"].value and not mes_act.get("fecha_emision"):
            mes_act["fecha_emision"] = str(ws_cfg["D7"].value).strip()
        if ws_cfg["D8"].value and not mes_act.get("fecha_vencimiento"):
            mes_act["fecha_vencimiento"] = str(ws_cfg["D8"].value).strip()

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

        # Mapear columnas dinámicamente según la fila 3
        def _norm_col(val: Any) -> str:
            import re
            s = str(val or "").lower().strip()
            s = s.replace("á", "a").replace("é", "e").replace(
                "í", "i").replace("ó", "o").replace("ú", "u")
            s = re.sub(r"[^a-z0-9]", "_", s)
            return re.sub(r"_+", "_", s).strip("_")

        col_map: Dict[str, int] = {}
        for c in range(1, ws_sec.max_column + 1):
            h = _norm_col(ws_sec.cell(row=3, column=c).value)
            if not h:
                continue
            if h in ("fecha_lect", "fecha_lectura", "f_lect"):
                col_map["fecha_lect"] = c
            elif h in ("conexion", "nro_conexion", "n_conexion"):
                col_map["conexion"] = c
            elif h in ("n_medidor", "nro_medidor", "medidor"):
                col_map["medidor"] = c
            elif h in ("titular_beneficiario", "titular", "nombre", "usuario"):
                col_map["nombre"] = c
            elif h in ("direccion", "calle"):
                col_map["direccion"] = c
            elif h in ("lect_anterior", "lectura_anterior", "lec_ant"):
                col_map["lect_anterior"] = c
            elif h in ("lect_actual", "lectura_actual", "lec_act"):
                col_map["lect_actual"] = c
            elif h in ("consumo_m3", "consumo"):
                col_map["consumo"] = c
            elif h in ("observacion", "novedad"):
                col_map["novedad"] = c
            elif h in ("nota", "comentario"):
                col_map["nota"] = c
            elif h in ("n_recibo", "nro_recibo", "recibo"):
                col_map["nro_recibo"] = c
            elif h in ("deuda_ant_s", "deuda_ant", "deuda_anterior"):
                col_map["deuda_ant"] = c
            elif h in ("deuda_actual_s", "deuda_actual"):
                col_map["deuda_actual"] = c
            elif h in ("total_pagar_s", "total_pagar", "total_a_pagar"):
                col_map["total_pagar"] = c
            elif h in ("meses", "meses_adeudados"):
                col_map["meses"] = c
            elif h == "pago":
                col_map["pago"] = c
            elif h in ("pagado", "monto_pagado_s", "monto_pagado"):
                col_map["monto_pagado"] = c
            elif h in ("fecha_pago", "f_pago"):
                col_map["fecha_pago"] = c
            elif h in ("id_usuario", "dni", "dni_id"):
                col_map["id_usuario"] = c
            elif h in ("fecha_anterior", "f_anterior"):
                col_map["fecha_anterior"] = c
            elif h in ("consumo_anterior", "c_anterior"):
                col_map["consumo_anterior"] = c
            elif h in ("estado_lectura", "estado_med"):
                col_map["estado_lectura"] = c
            elif h in ("registrado_por", "lector"):
                col_map["registrado_por"] = c
            elif h in ("categoria", "codigo_categoria", "cat"):
                col_map["categoria"] = c
            elif h in ("historial_m3", "historial"):
                col_map["historial_m3"] = c
            elif h in ("consumo_total_m3", "consumo_total"):
                col_map["consumo_total_m3"] = c
            elif h == "monto_agua":
                col_map["monto_agua"] = c
            elif h == "monto_desague":
                col_map["monto_desague"] = c
            elif h == "cargo_fijo":
                col_map["cargo_fijo"] = c
            elif h == "igv":
                col_map["igv"] = c
            elif h == "redondeo":
                col_map["redondeo"] = c
            elif h in ("deuda_ant_manual", "deuda_anterior_manual"):
                col_map["deuda_ant_manual"] = c

        inicio_gris = col_map.get("id_usuario", 17)

        for r in range(4, ws_sec.max_row + 1):
            uid = ws_sec.cell(row=r, column=inicio_gris).value
            if not uid:
                continue
            uid = str(uid).strip()

            n_med = ws_sec.cell(row=r, column=col_map.get("medidor", 3)).value
            n_med_str = str(n_med).strip() if n_med is not None else ""

            l_ant = ws_sec.cell(
                row=r, column=col_map.get("lect_anterior", 6)).value
            l_act = ws_sec.cell(
                row=r, column=col_map.get("lect_actual", 7)).value
            f_lect = ws_sec.cell(
                row=r, column=col_map.get("fecha_lect", 1)).value
            nov = ws_sec.cell(row=r, column=col_map.get("novedad", 9)).value
            nota = ws_sec.cell(row=r, column=col_map.get("nota", 10)).value

            # Campos del medidor
            l_ant_val = int(l_ant) if l_ant is not None and str(
                l_ant).isdigit() else 0
            l_act_val = int(l_act) if l_act is not None and str(
                l_act).isdigit() else None
            if l_act_val is not None:
                try:
                    import calculos
                    cons_val = calculos.consumo_medidor(l_ant_val, l_act_val, nov)
                except Exception:
                    cons_val = max(0, l_act_val - l_ant_val)
            else:
                cons_val = 0

            val_est = ws_sec.cell(row=r, column=col_map.get("estado_lectura", inicio_gris + 3)).value
            est_default = "LEIDO" if l_act_val is not None else "PENDIENTE"
            med_obj = {
                "nro_medidor": n_med_str,
                "lectura_anterior": l_ant_val,
                "lectura_actual": l_act_val,
                "consumo": cons_val,
                "fecha_lectura": str(f_lect).strip() if f_lect else None,
                "novedad": str(nov).strip() if nov else "NORMAL",
                "nota": str(nota).strip() if nota else "",
                "fecha_anterior": str(ws_sec.cell(row=r, column=col_map.get("fecha_anterior", inicio_gris + 1)).value or "").strip() or None,
                "consumo_anterior": ws_sec.cell(row=r, column=col_map.get("consumo_anterior", inicio_gris + 2)).value,
                "estado_lectura": str(val_est).strip() if val_est else est_default,
                "registrado_por": str(ws_sec.cell(row=r, column=col_map.get("registrado_por", inicio_gris + 4)).value or ("LECTOR" if l_act_val is not None else "")).strip(),
            }

            if uid not in mes_docs:
                rec_val = ws_sec.cell(
                    row=r, column=col_map.get("nro_recibo", 11)).value
                d_ant_val = ws_sec.cell(row=r, column=col_map.get(
                    "deuda_ant", 12)).value if "deuda_ant" in col_map else 0.0
                deuda_ant = float(d_ant_val or 0.0)

                if "deuda_actual" in col_map:
                    d_act_val = ws_sec.cell(
                        row=r, column=col_map["deuda_actual"]).value
                    deuda_act = float(d_act_val or 0.0)
                    tot_pagar = round(deuda_ant + deuda_act, 2)
                elif "total_pagar" in col_map:
                    tot_val = ws_sec.cell(
                        row=r, column=col_map["total_pagar"]).value
                    tot_pagar = float(tot_val or 0.0)
                    deuda_act = max(0.0, round(tot_pagar - deuda_ant, 2))
                else:
                    tot_val = ws_sec.cell(row=r, column=13).value
                    tot_pagar = float(tot_val or 0.0)
                    deuda_act = max(0.0, round(tot_pagar - deuda_ant, 2))

                meses_val = ws_sec.cell(
                    row=r, column=col_map.get("meses", 14)).value
                f_pag_val = ws_sec.cell(
                    row=r, column=col_map.get("fecha_pago", 16)).value

                if "pago" in col_map:
                    p_val = str(ws_sec.cell(
                        row=r, column=col_map["pago"]).value or "").strip().upper()
                    if p_val in ("SI", "1", "TRUE", "PAGADO"):
                        m_pagado = tot_pagar
                        pago_txt = "SI"
                    else:
                        m_pagado = 0.0
                        pago_txt = "NO"
                elif "monto_pagado" in col_map:
                    p_val = ws_sec.cell(
                        row=r, column=col_map["monto_pagado"]).value
                    if str(p_val).strip().upper() in ("SI", "PAGADO"):
                        m_pagado = tot_pagar
                        pago_txt = "SI"
                    else:
                        try:
                            m_pagado = float(p_val or 0.0)
                        except Exception:
                            m_pagado = 0.0
                        pago_txt = "SI" if (
                            m_pagado >= tot_pagar and tot_pagar > 0) else "NO"
                else:
                    p_val = ws_sec.cell(row=r, column=15).value
                    if str(p_val).strip().upper() in ("SI", "PAGADO"):
                        m_pagado = tot_pagar
                        pago_txt = "SI"
                    else:
                        try:
                            m_pagado = float(p_val or 0.0)
                        except Exception:
                            m_pagado = 0.0
                        pago_txt = "SI" if (
                            m_pagado >= tot_pagar and tot_pagar > 0) else "NO"

                hist_col = col_map.get("historial_m3", inicio_gris + 6)
                hist_raw = str(ws_sec.cell(row=r, column=hist_col).value or "")
                hist_list = [float(x)
                             for x in hist_raw.split(",") if x.strip()]

                mes_docs[uid] = {
                    "id_usuario": uid,
                    "nro_conexion": str(ws_sec.cell(row=r, column=col_map.get("conexion", 2)).value or "").strip(),
                    "nombre": str(ws_sec.cell(row=r, column=col_map.get("nombre", 4)).value or "").strip(),
                    "sector": s_name,
                    "direccion": str(ws_sec.cell(row=r, column=col_map.get("direccion", 5)).value or "").strip(),
                    "codigo_categoria": str(ws_sec.cell(row=r, column=col_map.get("categoria", inicio_gris + 5)).value or "A").strip(),
                    "medidores": [med_obj] if n_med_str else [],
                    "historial_m3": hist_list,
                    "consumo_total_m3": ws_sec.cell(row=r, column=col_map.get("consumo_total_m3", inicio_gris + 7)).value,
                    "nro_recibo": str(rec_val).strip() if rec_val else None,
                    "deuda_anterior": deuda_ant,
                    "deuda_actual": deuda_act,
                    "total_a_pagar": tot_pagar,
                    "meses_adeudados": 0 if pago_txt == "SI" else int(meses_val if meses_val is not None else 1),
                    "monto_pagado": m_pagado,
                    "pago": pago_txt,
                    "fecha_pago": str(f_pag_val).strip() if f_pag_val else None,
                    "monto_agua": ws_sec.cell(row=r, column=col_map.get("monto_agua", inicio_gris + 8)).value,
                    "monto_desague": ws_sec.cell(row=r, column=col_map.get("monto_desague", inicio_gris + 9)).value,
                    "cargo_fijo": ws_sec.cell(row=r, column=col_map.get("cargo_fijo", inicio_gris + 10)).value,
                    "igv": ws_sec.cell(row=r, column=col_map.get("igv", inicio_gris + 11)).value,
                    "redondeo": ws_sec.cell(row=r, column=col_map.get("redondeo", inicio_gris + 12)).value,
                    "deuda_anterior_manual": str(
                        ws_sec.cell(
                            row=r, column=col_map["deuda_ant_manual"]).value or "0"
                    ).strip().upper() in ("1", "SI", "TRUE", "1.0") if "deuda_ant_manual" in col_map else False,
                }
            else:
                if n_med_str:
                    mes_docs[uid]["medidores"].append(med_obj)

    # Validar sumas
    suma_reconstruida = sum(float(d.get("total_a_pagar") or 0.0)
                            for d in mes_docs.values())
    coincide_suma = abs(suma_reconstruida - suma_esperada) < 0.05

    return {
        "metadatos": metadatos,
        "periodo": periodo,
        "es_prueba": bool(metadatos.get("es_prueba", False)),
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
