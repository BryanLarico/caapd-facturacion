"""
servicios/datos_padron.py — Servicio de datos Local-First basado en Padrones Excel.

Lee directamente desde el archivo de padrón / respaldo Excel local al iniciar
y en todas las operaciones del programa, garantizando 0 lecturas a Firestore en
la operación regular.

Solo consulta Firestore cuando el usuario hace clic explícitamente en "🔄 Actualizar",
descargando las lecturas tomadas por los lectores móviles y guardándolas en el Excel.
"""
from __future__ import annotations
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import calculos
import codigos
import respaldo_excel
import rutas
from servicios.cola_offline import encolar_cambio
from servicios.datos import ServicioDatos
from servicios.metricas_monitoring import consultar_metricas_hoy


def buscar_archivos_base_datos(dir_bd: Optional[Path | str] = None) -> List[Path]:
    """Busca todos los archivos Excel en la carpeta 'Base de datos/' que cumplan el patrón PADRON_MES_aaaa-mm*.xlsx."""
    import re
    if dir_bd is None:
        directorio = rutas.ruta_base_de_datos()
    else:
        directorio = Path(dir_bd)
    if not directorio.exists():
        return []
    patron = re.compile(r"^PADRON_MES_\d{4}-\d{2}.*\.xlsx$", re.IGNORECASE)
    archivos = [p for p in directorio.glob("*.xlsx") if patron.match(p.name) and not p.name.startswith("~$")]
    archivos.sort(key=lambda p: p.name)
    return archivos


def validar_archivos_sin_duplicados(archivos: List[Path]) -> Tuple[List[Path], List[str]]:
    """Filtra y avisa si hay dos o más archivos correspondientes al mismo periodo."""
    import re
    por_periodo: Dict[str, List[Path]] = {}
    advertencias = []
    patron = re.compile(r"PADRON_MES_(\d{4}-\d{2})", re.IGNORECASE)
    for a in archivos:
        m = patron.search(a.name)
        if m:
            periodo = m.group(1)
            por_periodo.setdefault(periodo, []).append(a)

    seleccionados = []
    for per, lista in por_periodo.items():
        # Priorizar archivo con nombre canónico exacto PADRON_MES_{per}.xlsx
        lista.sort(key=lambda p: (0 if p.name.upper() == f"PADRON_MES_{per}.XLSX" else 1, p.name))
        if len(lista) > 1:
            advertencias.append(
                f"Se detectaron múltiples archivos para el mes {per}: "
                f"{[p.name for p in lista]}. Se conservará solo {lista[0].name} para evitar mezclas."
            )
            seleccionados.append(lista[0])
        else:
            seleccionados.append(lista[0])
    seleccionados.sort(key=lambda p: p.name)
    return seleccionados, advertencias


def buscar_archivo_respaldo() -> Optional[Path]:
    """Busca el archivo de respaldo RESPALDO_*.xlsx más reciente."""
    dir_resp = rutas.ruta_respaldos()
    archivos = [p for p in dir_resp.glob("RESPALDO_*.xlsx") if not p.name.startswith("~$")]
    if not archivos:
        dir_raiz = dir_resp.parent / "respaldos"
        if dir_raiz.exists():
            archivos = [p for p in dir_raiz.glob("RESPALDO_*.xlsx") if not p.name.startswith("~$")]
    if archivos:
        archivos.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return archivos[0]
    return None


def buscar_archivo_padron_mes() -> Optional[Path]:
    """Busca archivos de padrón PADRON_MES_*.xlsx priorizando la carpeta 'Base de datos/'."""
    # 1. Priorizar archivos en 'Base de datos/'
    archivos_bd = buscar_archivos_base_datos()
    if archivos_bd:
        return archivos_bd[0]

    candidatos = [
        rutas.ruta_datos("PADRON_MES_2026-10_NUEVO.xlsx"),
        rutas.DIR_BASE.parent / "escritorio" / "datos" / "PADRON_MES_2026-10_NUEVO.xlsx",
        rutas.ruta_datos("PADRON_MES_2026-09_LIMPIO.xlsx"),
    ]
    for c in candidatos:
        if c.exists():
            return c

    dir_datos = rutas.ruta_datos()
    padrones = [p for p in dir_datos.glob("PADRON_MES_*.xlsx") if not p.name.startswith("~$")]
    if padrones:
        padrones.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return padrones[0]
    return None


class ServicioDatosPadron(ServicioDatos):
    """Servicio de datos Local-First que lee del Padrón Excel y sincroniza bajo demanda."""

    def __init__(self, ruta_archivo: Optional[Path | str] = None, base_dir: Optional[Path | str] = None) -> None:
        self.es_contingencia: bool = False
        self.es_local_first: bool = True
        self.ops = {"lecturas": 0, "escrituras": 0}
        self.base_dir: Optional[Path] = Path(base_dir) if base_dir else None

        self.config: Dict[str, Any] = {}
        self.usuarios: Dict[str, Dict[str, Any]] = {}
        self.mes: Dict[str, Dict[str, Any]] = {}
        self.meses_encontrados: Dict[str, Dict[str, Any]] = {}
        self.periodo: str = "2026-10"

        cargado_completo = False

        # 1. Priorizar si el usuario colocó archivos en 'Base de datos/'
        archivos_bd = buscar_archivos_base_datos(self.base_dir)
        if archivos_bd:
            res = self.cargar_desde_carpeta_base_datos(dir_bd=self.base_dir)
            cargado_completo = bool(res.get("exito")) and len(self.usuarios) > 0

        # 2. Si no había bases allí, intentar cargar desde RESPALDO_*.xlsx
        if not cargado_completo:
            self.ruta_excel: Optional[Path] = Path(ruta_archivo) if ruta_archivo else buscar_archivo_respaldo()
            if self.ruta_excel and self.ruta_excel.exists():
                cargado_completo = self._cargar_desde_excel(self.ruta_excel)

        # 3. Si no había mes_docs en el respaldo, cargar desde el padrón Excel
        if not cargado_completo:
            ruta_padron = buscar_archivo_padron_mes()
            if ruta_padron and ruta_padron.exists():
                self._cargar_desde_padron_excel(ruta_padron)
                try:
                    self.guardar_en_respaldo_local()
                except Exception:
                    pass
            else:
                self._inicializar_por_defecto()

    def _cargar_desde_excel(self, ruta: Path) -> bool:
        """Carga config, usuarios y mes_docs desde un archivo de respaldo Excel (RESPALDO_*.xlsx)."""
        try:
            datos = respaldo_excel.leer_respaldo_excel(ruta)
            cfg = datos.get("config") or {}
            usr = datos.get("usuarios") or {}
            mes = datos.get("mes_docs") or {}
            periodo = datos.get("periodo") or (cfg.get("mes_actual") or {}).get("periodo") or "2026-10"

            if not usr or not mes:
                return False

            self.config = cfg
            self.usuarios = usr
            self.mes = mes
            self.periodo = periodo
            return True
        except Exception:
            return False

    def _inicializar_por_defecto(self) -> None:
        self.config = {
            "mes_actual": {
                "periodo": "2026-10",
                "estado": "FACTURADO",
                "fecha_emision": "2026-10-01",
                "fecha_vencimiento": "2026-10-20",
            },
            "ultimo_recibo": 796,
            "sectores": [
                "BARRIO DE CHAUPI",
                "BARRIO DE PACHAYZA",
                "BARRIO DE LUCMANI",
                "HUAQUILLO",
                "CHAUPICERCA",
                "AYACUCHO",
            ],
            "categorias": {
                "A": {
                    "cargo_fijo": 1.5,
                    "tarifa_desague": 0.0,
                    "rangos": [
                        {"m3_desde": 0, "m3_hasta": 10, "precio_m3": 1.0},
                        {"m3_desde": 10, "m3_hasta": 20, "precio_m3": 1.5},
                        {"m3_desde": 20, "m3_hasta": None, "precio_m3": 2.5},
                    ],
                }
            },
        }
        self.periodo = "2026-10"

    def _cargar_desde_padron_excel(self, ruta: Path) -> None:
        """Carga usuarios y documentos del mes desde el archivo de padrón Excel."""
        import openpyxl

        # Mantener config existente si ya se cargó, sino inicializarla
        if not self.config:
            self._inicializar_por_defecto()

        # Extraer periodo del nombre de archivo si contiene YYYY-MM
        nombre = ruta.name
        partes = nombre.split("_")
        for p in partes:
            if len(p) == 7 and p[:4].isdigit() and p[4] == "-" and p[5:].isdigit():
                self.periodo = p
                self.config.setdefault("mes_actual", {})["periodo"] = p
                break

        wb = openpyxl.load_workbook(str(ruta), data_only=True)
        # Buscar hoja de lecturas
        ws = None
        for name in ["Lecturas", "LECTURAS", "Hoja1", "Sheet1"]:
            if name in wb.sheetnames:
                ws = wb[name]
                break
        if not ws:
            ws = wb.active

        self.usuarios = {}
        self.mes = {}

        ultimo_recibo = int(self.config.get("ultimo_recibo") or 700)

        for r in range(2, ws.max_row + 1):
            nro_conexion = str(ws.cell(row=r, column=1).value or "").strip()
            dni = str(ws.cell(row=r, column=2).value or "").strip()
            nombre = str(ws.cell(row=r, column=3).value or "").strip()
            sector = str(ws.cell(row=r, column=4).value or "").strip()
            direccion = str(ws.cell(row=r, column=5).value or "").strip()
            categoria = str(ws.cell(row=r, column=6).value or "A").strip()
            nro_medidor = str(ws.cell(row=r, column=7).value or "").strip()
            lec_ant = ws.cell(row=r, column=8).value
            lec_act = ws.cell(row=r, column=9).value
            novedad = str(ws.cell(row=r, column=10).value or "NORMAL").strip()
            nota = str(ws.cell(row=r, column=11).value or "").strip()

            if not dni:
                continue

            uid = dni
            l_ant_int = int(lec_ant) if lec_ant is not None and str(lec_ant).isdigit() else 0
            l_act_int = int(lec_act) if lec_act is not None and str(lec_act).isdigit() else None

            med_obj = {
                "nro_medidor": nro_medidor,
                "lectura_anterior": l_ant_int,
                "lectura_actual": l_act_int,
                "estado_lectura": "LEIDO" if l_act_int is not None else "PENDIENTE",
                "novedad": novedad or "NORMAL",
                "nota": nota or "",
                "fecha_lectura": datetime.date.today().isoformat() if l_act_int is not None else None,
            }

            if uid not in self.usuarios:
                self.usuarios[uid] = {
                    "_id": uid,
                    "id_usuario": uid,
                    "nro_conexion": nro_conexion,
                    "nombre": nombre,
                    "sector": sector,
                    "direccion": direccion,
                    "codigo_categoria": categoria,
                    "activo": True,
                    "medidores": [nro_medidor] if nro_medidor else [],
                }
            else:
                if nro_medidor and nro_medidor not in self.usuarios[uid]["medidores"]:
                    self.usuarios[uid]["medidores"].append(nro_medidor)

            if uid not in self.mes:
                self.mes[uid] = {
                    "_id": uid,
                    "id_usuario": uid,
                    "nro_conexion": nro_conexion,
                    "nombre": nombre,
                    "sector": sector,
                    "direccion": direccion,
                    "codigo_categoria": categoria,
                    "medidores": [med_obj] if nro_medidor else [],
                    "total_a_pagar": 0.0,
                    "monto_pagado": 0.0,
                    "meses_adeudados": 1,
                    "nro_recibo": None,
                    "deuda_anterior": 0.0,
                    "cargo_fijo": 1.5,
                    "monto_agua": 0.0,
                    "monto_desague": 0.0,
                    "igv": 0.0,
                    "redondeo": 0.0,
                    "consumo_total_m3": 0,
                    "fecha_pago": None,
                }
            else:
                if nro_medidor:
                    self.mes[uid]["medidores"].append(med_obj)

        # Generar cálculo y recibo para cada usuario con consumo o cargo base
        categorias = self.config.get("categorias", {})
        todos_con_lectura = True

        for uid, doc in self.mes.items():
            tiene_pendientes = any(m.get("lectura_actual") is None for m in doc.get("medidores", []))
            if tiene_pendientes:
                todos_con_lectura = False
                doc["nro_recibo"] = None
                doc["total_a_pagar"] = 0.0
                doc["monto_pagado"] = 0.0
                doc["consumo_total_m3"] = 0
                continue

            cat_cod = doc.get("codigo_categoria", "A")
            cat_obj = categorias.get(cat_cod) or {"cargo_fijo": 1.5, "tarifa_desague": 0.0, "rangos": [{"m3_desde": 0, "m3_hasta": None, "precio_m3": 1.0}]}
            try:
                calc = calculos.calcular_recibo(
                    medidores=doc.get("medidores", []),
                    categoria=cat_obj,
                    igv_activo=False,
                    igv_porcentaje=0.18,
                    recibo_anterior=None,
                )
                ultimo_recibo += 1
                doc["nro_recibo"] = f"{ultimo_recibo:09d}"
                doc.update({
                    "consumo_total_m3": calc["consumo_total_m3"],
                    "monto_agua": calc["monto_agua"],
                    "monto_desague": calc["monto_desague"],
                    "cargo_fijo": calc["cargo_fijo"],
                    "deuda_anterior": calc["deuda_anterior"],
                    "igv": calc["igv"],
                    "redondeo": calc["redondeo"],
                    "total_a_pagar": calc["total_a_pagar"],
                    "meses_adeudados": calc["meses_adeudados"],
                })
            except Exception:
                doc["nro_recibo"] = None
                doc["total_a_pagar"] = 0.0

        self.config["ultimo_recibo"] = ultimo_recibo
        if "mes_actual" in self.config:
            self.config["mes_actual"]["estado"] = "FACTURADO" if todos_con_lectura and len(self.mes) > 0 else "ABIERTO"

    def guardar_en_respaldo_local(self, periodo: Optional[str] = None) -> Path:
        """Guarda el estado actual en el archivo de respaldo Excel local y en Base de datos/."""
        p_obj = periodo or self.periodo or self.config.get("mes_actual", {}).get("periodo") or "2026-10"
        es_prueba = rutas.es_entorno_prueba()

        # En entorno de prueba, SOLO escribe en escritorio/Base de datos PRUEBA/
        if es_prueba:
            destino_bd = rutas.ruta_base_de_datos(f"PADRON_MES_{p_obj}.xlsx")
            self.ruta_excel = destino_bd
            resp = respaldo_excel.generar_respaldo_excel(
                config=self.config,
                usuarios=self.usuarios,
                mes_docs=self.mes,
                periodo=p_obj,
                ruta_archivo=destino_bd,
                es_prueba=True,
            )
            return resp

        # Modo normal (producción)
        destino = rutas.ruta_respaldos(f"RESPALDO_{p_obj}.xlsx")
        self.ruta_excel = destino
        resp = respaldo_excel.generar_respaldo_excel(
            config=self.config,
            usuarios=self.usuarios,
            mes_docs=self.mes,
            periodo=p_obj,
            ruta_archivo=destino,
            es_prueba=False,
        )
        try:
            destino_bd = rutas.ruta_base_de_datos(f"PADRON_MES_{p_obj}.xlsx")
            respaldo_excel.generar_respaldo_excel(
                config=self.config,
                usuarios=self.usuarios,
                mes_docs=self.mes,
                periodo=p_obj,
                ruta_archivo=destino_bd,
                es_prueba=False,
            )
        except Exception:
            pass
        return resp

    def _extraer_datos_archivo_excel(self, ruta: Path) -> Dict[str, Any]:
        """Extrae usuarios y documentos del mes desde cualquier archivo de respaldo o padrón Excel."""
        import openpyxl

        # 1. Intentar leer como formato integral de respaldo
        try:
            datos_resp = respaldo_excel.leer_respaldo_excel(ruta)
            if datos_resp.get("usuarios") and datos_resp.get("mes_docs"):
                return {
                    "usuarios": datos_resp["usuarios"],
                    "mes_docs": datos_resp["mes_docs"],
                    "periodo": datos_resp.get("periodo") or "2026-10",
                    "config": datos_resp.get("config") or {},
                    "metadatos": datos_resp.get("metadatos") or {},
                }
        except Exception:
            pass

        # 2. Leer como hoja de lecturas / padrón tabular con coincidencia exacta
        def _norm_k(h: Any) -> str:
            import re
            s = str(h or "").lower().strip()
            s = s.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
            s = re.sub(r"[^a-z0-9]", "_", s)
            return re.sub(r"_+", "_", s).strip("_")

        periodo = "2026-10"
        nombre = ruta.name
        partes = nombre.split("_")
        for p in partes:
            if len(p) == 7 and p[:4].isdigit() and p[4] == "-" and p[5:].isdigit():
                periodo = p
                break

        wb = openpyxl.load_workbook(str(ruta), data_only=True)
        ws = None
        for name in ["Lecturas", "LECTURAS", "Hoja1", "Sheet1"]:
            if name in wb.sheetnames:
                ws = wb[name]
                break
        if not ws:
            ws = wb.active

        col_map = {
            "conexion": 1, "dni": 2, "nombre": 3, "sector": 4,
            "direccion": 5, "categoria": 6, "medidor": 7,
            "anterior": 8, "actual": 9, "novedad": 10, "nota": 11,
            "deuda_ant": None, "deuda_actual": None, "total_pagar": None,
            "meses": None, "pago": None, "monto_pagado": None, "fecha_pago": None,
        }
        for c in range(1, ws.max_column + 1):
            val = _norm_k(ws.cell(row=1, column=c).value)
            if not val:
                continue
            if val in ("conexion", "nro_conexion", "n_conexion", "cod_con", "nro_con"): col_map["conexion"] = c
            elif val in ("dni", "id_usuario", "dni_id", "documento"): col_map["dni"] = c
            elif val in ("nombre", "titular_beneficiario", "titular", "usuario", "abonado", "persona"): col_map["nombre"] = c
            elif val in ("sector", "barrio"): col_map["sector"] = c
            elif val in ("direccion", "calle", "lugar"): col_map["direccion"] = c
            elif val in ("categoria", "codigo_categoria", "cat"): col_map["categoria"] = c
            elif val in ("n_medidor", "nro_medidor", "medidor", "num_med"): col_map["medidor"] = c
            elif val in ("lect_anterior", "lectura_anterior", "lec_ant", "anterior"): col_map["anterior"] = c
            elif val in ("lect_actual", "lectura_actual", "lec_act", "actual"): col_map["actual"] = c
            elif val in ("observacion", "novedad", "estado_med"): col_map["novedad"] = c
            elif val in ("nota", "detalle", "comentario"): col_map["nota"] = c
            elif val in ("deuda_ant_s", "deuda_ant", "deuda_anterior"): col_map["deuda_ant"] = c
            elif val in ("deuda_actual_s", "deuda_actual"): col_map["deuda_actual"] = c
            elif val in ("total_pagar_s", "total_pagar", "total_a_pagar"): col_map["total_pagar"] = c
            elif val in ("meses", "meses_adeudados"): col_map["meses"] = c
            elif val == "pago": col_map["pago"] = c
            elif val in ("pagado", "monto_pagado_s", "monto_pagado"): col_map["monto_pagado"] = c
            elif val in ("fecha_pago", "f_pago"): col_map["fecha_pago"] = c

        usuarios: Dict[str, Dict[str, Any]] = {}
        mes: Dict[str, Dict[str, Any]] = {}
        ultimo_recibo = int(self.config.get("ultimo_recibo") or 700)

        for r in range(2, ws.max_row + 1):
            dni_raw = ws.cell(row=r, column=col_map["dni"]).value
            dni = str(dni_raw or "").strip()
            if not dni or dni.lower() in ("dni", "dni_id", "none"):
                continue

            nro_conexion = str(ws.cell(row=r, column=col_map["conexion"]).value or "").strip()
            nombre = str(ws.cell(row=r, column=col_map["nombre"]).value or "").strip().upper()
            sector = str(ws.cell(row=r, column=col_map["sector"]).value or "").strip().upper()
            direccion = str(ws.cell(row=r, column=col_map["direccion"]).value or "").strip()
            categoria = str(ws.cell(row=r, column=col_map["categoria"]).value or "A").strip().upper()
            nro_medidor = str(ws.cell(row=r, column=col_map["medidor"]).value or "").strip()

            lec_ant = ws.cell(row=r, column=col_map["anterior"]).value
            lec_act = ws.cell(row=r, column=col_map["actual"]).value
            novedad = str(ws.cell(row=r, column=col_map["novedad"]).value or "NORMAL").strip()
            nota = str(ws.cell(row=r, column=col_map["nota"]).value or "").strip()

            l_ant_int = int(lec_ant) if lec_ant is not None and str(lec_ant).isdigit() else 0
            l_act_int = int(lec_act) if lec_act is not None and str(lec_act).isdigit() else None

            d_ant_val = ws.cell(row=r, column=col_map["deuda_ant"]).value if col_map.get("deuda_ant") else 0.0
            try:
                d_ant_f = float(d_ant_val or 0.0)
            except Exception:
                d_ant_f = 0.0

            d_act_f = 0.0
            tot_pagar_f = 0.0
            if col_map.get("deuda_actual"):
                try:
                    d_act_f = float(ws.cell(row=r, column=col_map["deuda_actual"]).value or 0.0)
                    tot_pagar_f = round(d_ant_f + d_act_f, 2)
                except Exception:
                    tot_pagar_f = d_ant_f
            elif col_map.get("total_pagar"):
                try:
                    tot_pagar_f = float(ws.cell(row=r, column=col_map["total_pagar"]).value or 0.0)
                    d_act_f = max(0.0, round(tot_pagar_f - d_ant_f, 2))
                except Exception:
                    tot_pagar_f = 0.0

            pago_val = ws.cell(row=r, column=col_map["pago"]).value if col_map.get("pago") else None
            monto_pag_val = ws.cell(row=r, column=col_map["monto_pagado"]).value if col_map.get("monto_pagado") else None
            fecha_pag_val = ws.cell(row=r, column=col_map["fecha_pago"]).value if col_map.get("fecha_pago") else None
            meses_val = ws.cell(row=r, column=col_map["meses"]).value if col_map.get("meses") else None
            meses_num = int(meses_val) if (meses_val is not None and str(meses_val).isdigit()) else 1

            uid = dni
            med_obj = {
                "nro_medidor": nro_medidor,
                "lectura_anterior": l_ant_int,
                "lectura_actual": l_act_int,
                "estado_lectura": "LEIDO" if l_act_int is not None else "PENDIENTE",
                "novedad": novedad or "NORMAL",
                "nota": nota or "",
                "fecha_lectura": datetime.date.today().isoformat() if l_act_int is not None else None,
            }

            if uid not in usuarios:
                usuarios[uid] = {
                    "_id": uid,
                    "id_usuario": uid,
                    "nro_conexion": nro_conexion,
                    "nombre": nombre,
                    "sector": sector,
                    "direccion": direccion,
                    "codigo_categoria": categoria,
                    "activo": True,
                    "medidores": [nro_medidor] if nro_medidor else [],
                }
            elif nro_medidor and nro_medidor not in usuarios[uid]["medidores"]:
                usuarios[uid]["medidores"].append(nro_medidor)

            if uid not in mes:
                mes[uid] = {
                    "_id": uid,
                    "id_usuario": uid,
                    "nro_conexion": nro_conexion,
                    "nombre": nombre,
                    "sector": sector,
                    "direccion": direccion,
                    "codigo_categoria": categoria,
                    "medidores": [med_obj] if nro_medidor else [],
                    "total_a_pagar": tot_pagar_f,
                    "monto_pagado": 0.0,
                    "meses_adeudados": meses_num,
                    "nro_recibo": None,
                    "deuda_anterior": d_ant_f,
                    "deuda_actual": d_act_f,
                    "cargo_fijo": 1.5,
                    "monto_agua": 0.0,
                    "monto_desague": 0.0,
                    "igv": 0.0,
                    "redondeo": 0.0,
                    "consumo_total_m3": 0,
                    "fecha_pago": None,
                }
            elif nro_medidor:
                mes[uid]["medidores"].append(med_obj)

            if pago_val and str(pago_val).strip().upper() in ("SI", "1", "TRUE", "PAGADO"):
                mes[uid]["monto_pagado"] = tot_pagar_f
                mes[uid]["pago"] = "SI"
                mes[uid]["meses_adeudados"] = 0
                mes[uid]["fecha_pago"] = str(fecha_pag_val or datetime.date.today().isoformat())
            elif monto_pag_val is not None and str(monto_pag_val).replace(".", "", 1).isdigit():
                mes[uid]["monto_pagado"] = round(float(monto_pag_val), 2)
                mes[uid]["fecha_pago"] = str(fecha_pag_val or datetime.date.today().isoformat())
                if mes[uid]["monto_pagado"] >= tot_pagar_f and tot_pagar_f > 0:
                    mes[uid]["pago"] = "SI"
                    mes[uid]["meses_adeudados"] = 0

        return {
            "usuarios": usuarios,
            "mes_docs": mes,
            "periodo": periodo,
        }

    def cargar_desde_carpeta_base_datos(
        self, callback_progreso: Optional[Any] = None, dir_bd: Optional[Path | str] = None
    ) -> Dict[str, Any]:
        """
        Carga y consolida todas las bases de datos / padrones presentes en la carpeta 'Base de datos/'.
        Permite al usuario colocar bases simuladas de meses anteriores o actuales,
        recalculando usuarios, consumos y estados de pago en memoria sin consultar Firebase.
        """
        directorio = Path(dir_bd) if dir_bd else (self.base_dir or rutas.ruta_base_de_datos())
        archivos_encontrados = buscar_archivos_base_datos(directorio)
        archivos, advertencias = validar_archivos_sin_duplicados(archivos_encontrados)

        if not archivos:
            p_alt = buscar_archivo_padron_mes()
            if p_alt:
                archivos = [p_alt]

        if not archivos:
            return {"archivos": 0, "usuarios": 0, "meses": [], "mensaje": "No se encontraron archivos en 'Base de datos/'"}

        total_archivos = len(archivos)
        meses_cargados: Dict[str, Dict[str, Any]] = {}
        config_por_periodo: Dict[str, Dict[str, Any]] = {}
        usuarios_consolidados: Dict[str, Dict[str, Any]] = dict(self.usuarios)

        for idx, arch in enumerate(archivos, 1):
            if callback_progreso:
                pct = int((idx / (total_archivos + 1)) * 100)
                callback_progreso(pct, f"Leyendo {arch.name}...")

            datos_archivo = self._extraer_datos_archivo_excel(arch)
            for uid, u in datos_archivo.get("usuarios", {}).items():
                if uid not in usuarios_consolidados:
                    usuarios_consolidados[uid] = dict(u)
                else:
                    meds_exist = usuarios_consolidados[uid].setdefault("medidores", [])
                    for m in u.get("medidores") or []:
                        m_str = m.get("nro_medidor") if isinstance(m, dict) else str(m)
                        if m_str and m_str not in meds_exist:
                            meds_exist.append(m_str)

            periodo_arch = datos_archivo.get("periodo") or "2026-10"
            docs_mes = datos_archivo.get("mes_docs", {})
            for uid, doc in docs_mes.items():
                d_ant = float(doc.get("deuda_anterior") or 0.0)
                d_act = float(doc.get("deuda_actual") or 0.0)
                if not doc.get("total_a_pagar"):
                    doc["total_a_pagar"] = round(d_ant + d_act, 2)
                pago_val = str(doc.get("pago") or "").strip().upper()
                if pago_val in ("SI", "1", "TRUE", "PAGADO"):
                    doc["monto_pagado"] = doc["total_a_pagar"]
                    doc["pago"] = "SI"
                    doc["meses_adeudados"] = 0
                elif pago_val in ("NO", "0", "FALSE"):
                    doc["monto_pagado"] = 0.0
                    doc["pago"] = "NO"

            meses_cargados[periodo_arch] = docs_mes
            if datos_archivo.get("config"):
                config_por_periodo[periodo_arch] = datos_archivo["config"]

        self.usuarios = usuarios_consolidados
        self.meses_encontrados = meses_cargados

        periodos_ordenados = sorted(meses_cargados.keys(), reverse=True)
        periodo_reciente = periodos_ordenados[0] if periodos_ordenados else "2026-10"
        self.periodo = periodo_reciente
        self.mes = meses_cargados.get(periodo_reciente, {})

        # Actualizar config desde el mes más reciente si contenía CONFIG
        cfg_reciente = config_por_periodo.get(periodo_reciente, {})
        if cfg_reciente:
            self.config.update(cfg_reciente)

        if "mes_actual" in self.config:
            self.config["mes_actual"]["periodo"] = periodo_reciente
            estado_reciente = (cfg_reciente.get("mes_actual") or {}).get("estado")
            if estado_reciente:
                self.config["mes_actual"]["estado"] = estado_reciente

        self.guardar_en_respaldo_local()

        if callback_progreso:
            callback_progreso(100, "¡Base de datos local actualizada con éxito!")

        return {
            "archivos": total_archivos,
            "usuarios": len(self.usuarios),
            "meses": list(meses_cargados.keys()),
            "periodo_activo": self.periodo,
            "advertencias": advertencias,
            "exito": True,
        }

    def reescribir_a_firebase(
        self, callback_progreso: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Sube o restaura a Firebase Firestore todos los usuarios y meses desde la carpeta 'Base de datos/'.
        Escribe en lotes de 500 (WriteBatch) para minimizar tiempo y cuota de red.
        """
        if callback_progreso:
            callback_progreso(10, "Consolidando bases de datos locales...")
        self.cargar_desde_carpeta_base_datos()

        import firebase_client as fb

        total_usuarios = len(self.usuarios)
        total_escrituras = 0
        meses_a_escribir = getattr(self, "meses_encontrados", {})
        if not meses_a_escribir:
            meses_a_escribir = {self.periodo: self.mes}

        # 1. Escribir Usuarios
        if callback_progreso:
            callback_progreso(30, f"Escribiendo {total_usuarios} usuarios en Firebase...")
        fb.guardar_usuarios_lote(self.usuarios)
        total_escrituras += total_usuarios

        # 2. Escribir Meses
        total_meses = len(meses_a_escribir)
        for i, (periodo, docs_mes) in enumerate(meses_a_escribir.items(), 1):
            if callback_progreso:
                pct = 30 + int((i / (total_meses + 1)) * 50)
                callback_progreso(pct, f"Escribiendo mes {periodo} ({len(docs_mes)} registros)...")
            fb.guardar_mes_lote(periodo, docs_mes)
            total_escrituras += len(docs_mes)

        # 3. Actualizar Configuración general en Firestore
        if callback_progreso:
            callback_progreso(90, "Actualizando configuración general en la nube...")
        fb.guardar_config(self.config)
        total_escrituras += 1

        self.ops["escrituras"] += total_escrituras

        if callback_progreso:
            callback_progreso(100, f"¡{total_escrituras} documentos sincronizados con éxito en Firebase!")

        return {
            "usuarios": total_usuarios,
            "meses": list(meses_a_escribir.keys()),
            "operaciones_escritura": total_escrituras,
            "exito": True,
        }

    # -----------------------------------------------------------------------
    # Sincronización explícita con Firebase (SOLO al presionar "Actualizar")
    # -----------------------------------------------------------------------
    def sincronizar_desde_firebase(self, periodo: Optional[str] = None) -> Dict[str, Any]:
        """
        Descarga desde Firestore las lecturas actualizadas por los lectores móviles.
        Solo se ejecuta cuando el usuario presiona el botón Actualizar.
        """
        p = periodo or self.periodo
        actualizados = 0
        errores = []

        try:
            import firebase_client as fb
            docs = fb.db().collection(fb.nombre_coleccion_mes(p)).stream()
            for doc in docs:
                datos = doc.to_dict()
                uid = doc.id
                if uid in self.mes:
                    meds_cloud = datos.get("medidores") or []
                    meds_local = self.mes[uid].get("medidores") or []
                    for mc in meds_cloud:
                        nro = mc.get("nro_medidor")
                        ml = next((m for m in meds_local if m.get("nro_medidor") == nro), None)
                        if ml and mc.get("lectura_actual") is not None:
                            ml["lectura_actual"] = mc.get("lectura_actual")
                            ml["estado_lectura"] = mc.get("estado_lectura", "LEIDO")
                            ml["novedad"] = mc.get("novedad", "NORMAL")
                            ml["nota"] = mc.get("nota", "")
                            ml["fecha_lectura"] = mc.get("fecha_lectura")
                            actualizados += 1

                    if datos.get("monto_pagado", 0) > 0 and self.mes[uid].get("monto_pagado", 0) == 0:
                        self.mes[uid]["monto_pagado"] = datos.get("monto_pagado")
                        self.mes[uid]["fecha_pago"] = datos.get("fecha_pago")

            self.guardar_en_respaldo_local()

        except Exception as e:
            errores.append(str(e))

        return {
            "periodo": p,
            "actualizados": actualizados,
            "errores": errores,
            "exito": len(errores) == 0,
        }

    # -----------------------------------------------------------------------
    # Operaciones de Configuración
    # -----------------------------------------------------------------------
    def cargar_config(self) -> Dict[str, Any]:
        return self.config

    def guardar_config(self, datos: Dict[str, Any]) -> None:
        self.config = dict(datos)
        self.guardar_en_respaldo_local()

    def actualizar_config_campo(self, campo: str, valor: Any) -> None:
        partes = campo.split(".")
        nodo = self.config
        for p in partes[:-1]:
            nodo = nodo.setdefault(p, {})
        nodo[partes[-1]] = valor
        self.guardar_en_respaldo_local()

    # -----------------------------------------------------------------------
    # Usuarios (Padrón)
    # -----------------------------------------------------------------------
    def cargar_usuarios(self, forzar: bool = False) -> Dict[str, Dict[str, Any]]:
        return self.usuarios

    def obtener_usuario(self, id_usuario: str) -> Optional[Dict[str, Any]]:
        return self.usuarios.get(id_usuario)

    def guardar_usuario(
        self, id_usuario: str, datos: Dict[str, Any], agregar_al_mes: bool = False
    ) -> None:
        d = dict(datos)
        d["_id"] = id_usuario
        self.usuarios[id_usuario] = d
        if agregar_al_mes and self.mes is not None:
            if id_usuario not in self.mes:
                self.mes[id_usuario] = dict(d)
        self.guardar_en_respaldo_local()

    def actualizar_usuario(self, id_usuario: str, cambios: Dict[str, Any]) -> None:
        if id_usuario in self.usuarios:
            self.usuarios[id_usuario].update(cambios)
            if id_usuario in self.mes:
                self.mes[id_usuario].update(cambios)
            self.guardar_en_respaldo_local()

    def corregir_dni_usuario(self, id_viejo: str, id_nuevo: str) -> Dict[str, Any]:
        if id_viejo not in self.usuarios:
            raise ValueError(f"Usuario {id_viejo} no existe.")
        u = self.usuarios.pop(id_viejo)
        u["_id"] = id_nuevo
        u["id_usuario"] = id_nuevo
        self.usuarios[id_nuevo] = u
        if id_viejo in self.mes:
            m = self.mes.pop(id_viejo)
            m["_id"] = id_nuevo
            m["id_usuario"] = id_nuevo
            self.mes[id_nuevo] = m
        self.guardar_en_respaldo_local()
        return u

    def obtener_siguiente_conexion_libre(self) -> str:
        con_max = 0
        for u in self.usuarios.values():
            c = str(u.get("nro_conexion") or "")
            if c.isdigit():
                con_max = max(con_max, int(c))
        return f"{con_max + 1:06d}"

    def obtener_siguiente_id_sd(self) -> str:
        sd_max = 0
        for uid in self.usuarios.keys():
            if str(uid).startswith("SD-"):
                num = str(uid)[3:]
                if num.isdigit():
                    sd_max = max(sd_max, int(num))
        return f"SD-{sd_max + 1:03d}"

    def validar_medidores_unicos(
        self, medidores: List[str], id_usuario_actual: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        meds_existentes: Dict[str, str] = {}
        for uid, u in self.usuarios.items():
            if id_usuario_actual and uid == id_usuario_actual:
                continue
            for m in u.get("medidores") or []:
                num = str(m.get("nro_medidor") if isinstance(m, dict) else m).strip()
                if num:
                    meds_existentes[num] = u.get("nombre") or uid
        for med in medidores:
            m_str = str(med).strip()
            if m_str in meds_existentes:
                return False, f"El medidor {m_str} ya pertenece a {meds_existentes[m_str]}."
        return True, None

    # -----------------------------------------------------------------------
    # Documentos del Mes y Lecturas
    # -----------------------------------------------------------------------
    def cargar_mes(self, periodo: str) -> Dict[str, Dict[str, Any]]:
        return self.mes

    def verificar_puede_abrir_mes(self) -> Tuple[bool, str, str]:
        mes_act = self.config.get("mes_actual") or {}
        periodo_actual = mes_act.get("periodo") or self.periodo
        estado_actual = mes_act.get("estado") or "FACTURADO"

        if estado_actual != "FACTURADO":
            return False, f"El mes actual ({periodo_actual}) está {estado_actual}. Debe estar FACTURADO para abrir uno nuevo.", ""

        try:
            a, m = map(int, periodo_actual.split("-"))
            m += 1
            if m > 12:
                m = 1
                a += 1
            siguiente = f"{a:04d}-{m:02d}"
        except Exception:
            siguiente = ""

        return True, "", siguiente

    def verificar_periodo_disponible(self, periodo: str) -> Tuple[bool, str]:
        return True, ""

    def abrir_mes(
        self,
        periodo: str,
        fecha_emision: str,
        fecha_vencimiento: str,
        lecturas_iniciales: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        self.periodo = periodo
        self.config["mes_actual"] = {
            "periodo": periodo,
            "estado": "ABIERTO",
            "fecha_emision": fecha_emision,
            "fecha_vencimiento": fecha_vencimiento,
        }
        self.mes = {}
        for uid, u in self.usuarios.items():
            meds = []
            for m in u.get("medidores") or []:
                nro = m.get("nro_medidor") if isinstance(m, dict) else str(m)
                lec_ant = (lecturas_iniciales or {}).get(nro, 0)
                meds.append({
                    "nro_medidor": nro,
                    "lectura_anterior": lec_ant,
                    "lectura_actual": None,
                    "estado_lectura": "PENDIENTE",
                    "novedad": "NORMAL",
                    "nota": "",
                })
            self.mes[uid] = {
                "_id": uid,
                "id_usuario": uid,
                "nro_conexion": u.get("nro_conexion", ""),
                "nombre": u.get("nombre", ""),
                "sector": u.get("sector", ""),
                "direccion": u.get("direccion", ""),
                "codigo_categoria": u.get("codigo_categoria", "A"),
                "medidores": meds,
                "total_a_pagar": 0.0,
                "monto_pagado": 0.0,
                "meses_adeudados": 1,
            }
        self.guardar_en_respaldo_local()
        return {"periodo": periodo, "estado": "ABIERTO"}

    def cerrar_lecturas(self, periodo: Optional[str] = None) -> Dict[str, Any]:
        p = periodo or self.periodo
        if "mes_actual" in self.config:
            self.config["mes_actual"]["estado"] = "CERRADO"
        self.guardar_en_respaldo_local()
        return {"periodo": p, "estado": "CERRADO"}

    def reabrir_lecturas(self, periodo: Optional[str] = None) -> Dict[str, Any]:
        p = periodo or self.periodo
        if "mes_actual" in self.config:
            self.config["mes_actual"]["estado"] = "ABIERTO"
        self.guardar_en_respaldo_local()
        return {"periodo": p, "estado": "ABIERTO"}

    def guardar_lectura_medidor(
        self,
        periodo: str,
        id_usuario: str,
        nro_medidor: str,
        lectura_actual: int,
        novedad: str = "NORMAL",
        nota: str = "",
        registrado_por: str = "ADMIN",
    ) -> Dict[str, Any]:
        doc = self.mes.get(id_usuario)
        if not doc:
            raise ValueError(f"Usuario {id_usuario} no encontrado en el mes {periodo}.")

        med_obj = next((m for m in doc.get("medidores", []) if m.get("nro_medidor") == nro_medidor), None)
        if med_obj:
            med_obj["lectura_actual"] = int(lectura_actual)
            med_obj["fecha_lectura"] = datetime.date.today().isoformat()
            med_obj["estado_lectura"] = "LEIDO"
            med_obj["novedad"] = novedad or "NORMAL"
            med_obj["nota"] = nota or ""
            med_obj["registrado_por"] = registrado_por

        self.ops["escrituras"] += 1
        self.guardar_en_respaldo_local()

        encolar_cambio("lectura", {
            "periodo": periodo,
            "id_usuario": id_usuario,
            "nro_medidor": nro_medidor,
            "lectura_actual": lectura_actual,
            "novedad": novedad,
            "nota": nota,
            "registrado_por": registrado_por,
        })
        return {"id_usuario": id_usuario, "nro_medidor": nro_medidor}

    # -----------------------------------------------------------------------
    # Emisión de Recibos y Cobros
    # -----------------------------------------------------------------------
    def verificar_estado_generacion_recibos(self, periodo: Optional[str] = None) -> Dict[str, Any]:
        p = periodo or self.periodo
        mes_act = self.config.get("mes_actual") or {}
        estado = mes_act.get("estado") or "FACTURADO"

        rec_gen = sum(1 for d in self.mes.values() if d.get("nro_recibo"))
        tot_fac = sum(float(d.get("total_a_pagar") or 0.0) for d in self.mes.values())
        pagados = sum(1 for d in self.mes.values() if float(d.get("monto_pagado") or 0) >= float(d.get("total_a_pagar") or 0) and float(d.get("total_a_pagar") or 0) > 0)

        faltantes = []
        for uid, d in self.mes.items():
            for m in d.get("medidores", []):
                if m.get("lectura_actual") is None and m.get("estado_lectura") != "LEIDO":
                    faltantes.append({
                        "id_usuario": uid,
                        "nro_conexion": d.get("nro_conexion"),
                        "nombre": d.get("nombre"),
                        "sector": d.get("sector"),
                        "nro_medidor": m.get("nro_medidor"),
                        "lectura_anterior": m.get("lectura_anterior", 0),
                    })

        puede_generar = (estado in ("CERRADO", "FACTURADO"))

        return {
            "periodo": p,
            "estado": estado,
            "puede_generar": puede_generar,
            "faltantes": faltantes,
            "total_usuarios": len(self.mes),
            "recibos_generados": rec_gen,
            "total_facturado": round(tot_fac, 2),
            "pagados": pagados,
            "pendientes": len(self.mes) - pagados,
        }

    def generar_recibo_usuario(self, periodo: str, id_usuario: str) -> Dict[str, Any]:
        doc = self.mes.get(id_usuario)
        if not doc:
            raise ValueError(f"Usuario {id_usuario} no encontrado en el mes {periodo}.")

        for m in doc.get("medidores", []):
            if m.get("lectura_actual") is None:
                m["lectura_actual"] = m.get("lectura_anterior") or 0
                m["estado_lectura"] = "ESTIMADO"

        ultimo_recibo_num = int(self.config.get("ultimo_recibo") or 0)
        if not doc.get("nro_recibo"):
            ultimo_recibo_num += 1
            doc["nro_recibo"] = f"{ultimo_recibo_num:09d}"
            self.config["ultimo_recibo"] = ultimo_recibo_num

        categorias = self.config.get("categorias", {})
        cat_cod = doc.get("codigo_categoria", "A")
        cat_obj = categorias.get(cat_cod) or {"cargo_fijo": 1.5, "tarifa_desague": 0.0, "rangos": [{"m3_desde": 0, "m3_hasta": None, "precio_m3": 1.0}]}

        calc = calculos.calcular_recibo(
            medidores=doc.get("medidores", []),
            categoria=cat_obj,
            igv_activo=False,
            igv_porcentaje=0.18,
            recibo_anterior=None,
        )

        doc.update({
            "consumo_total_m3": calc["consumo_total_m3"],
            "monto_agua": calc["monto_agua"],
            "monto_desague": calc["monto_desague"],
            "cargo_fijo": calc["cargo_fijo"],
            "deuda_anterior": calc["deuda_anterior"],
            "igv": calc["igv"],
            "redondeo": calc["redondeo"],
            "total_a_pagar": calc["total_a_pagar"],
            "meses_adeudados": calc["meses_adeudados"],
        })
        if "monto_pagado" not in doc or doc.get("monto_pagado") is None:
            doc["monto_pagado"] = 0.0
            doc["fecha_pago"] = None

        self.mes[id_usuario] = doc
        self.guardar_en_respaldo_local()
        return doc

    def generar_recibos_mes(
        self,
        periodo: Optional[str] = None,
        callback_progreso: Optional[Any] = None,
    ) -> Dict[str, Any]:
        p = periodo or self.periodo
        total = len(self.mes)
        procesados = 0

        for uid in list(self.mes.keys()):
            self.generar_recibo_usuario(p, uid)
            procesados += 1
            if callback_progreso:
                callback_progreso(procesados, total)

        if "mes_actual" in self.config:
            self.config["mes_actual"]["estado"] = "FACTURADO"

        self.guardar_en_respaldo_local()
        return {"periodo": p, "total_generados": procesados}

    def generar_pdf_recibo(self, periodo: str, id_usuario: str) -> str:
        doc = self.mes.get(id_usuario)
        if not doc:
            raise ValueError(f"Usuario {id_usuario} no encontrado.")
        from servicios.generador_pdf import generar_recibo_pdf_para_usuario
        return str(generar_recibo_pdf_para_usuario(doc, self.config, periodo))

    def generar_zip_recibos(self, periodo: str, sector: Optional[str] = None) -> Optional[str]:
        from servicios.generador_pdf import generar_recibo_pdf_para_usuario, empaquetar_recibos_en_zip
        for uid, doc in self.mes.items():
            if sector and doc.get("sector") != sector:
                continue
            if doc.get("nro_recibo"):
                generar_recibo_pdf_para_usuario(doc, self.config, periodo)
        ruta_zip = empaquetar_recibos_en_zip(periodo, sector)
        return str(ruta_zip) if ruta_zip else None

    def registrar_pago(
        self,
        periodo: str,
        id_usuario: str,
        monto_pagado: float,
        fecha_pago: Optional[str] = None,
    ) -> Dict[str, Any]:
        doc = self.mes.get(id_usuario)
        if not doc:
            raise ValueError(f"Usuario {id_usuario} no encontrado en el mes {periodo}.")
        fecha = fecha_pago or datetime.date.today().isoformat()
        monto = round(float(monto_pagado), 2)
        doc["monto_pagado"] = monto
        doc["fecha_pago"] = fecha

        self.ops["escrituras"] += 1
        self.guardar_en_respaldo_local()

        encolar_cambio("pago", {
            "periodo": periodo,
            "id_usuario": id_usuario,
            "monto_pagado": monto,
            "fecha_pago": fecha,
        })
        return doc

    def anular_pago(self, periodo: str, id_usuario: str) -> Dict[str, Any]:
        doc = self.mes.get(id_usuario)
        if not doc:
            raise ValueError(f"Usuario {id_usuario} no encontrado en el mes {periodo}.")
        doc["monto_pagado"] = 0.0
        doc["fecha_pago"] = None

        self.ops["escrituras"] += 1
        self.guardar_en_respaldo_local()

        encolar_cambio("anular_pago", {
            "periodo": periodo,
            "id_usuario": id_usuario,
        })
        return doc

    def exportar_reporte_morosos_excel(
        self,
        periodo: Optional[str] = None,
        ruta_salida: Optional[str] = None,
    ) -> str:
        p = Path(ruta_salida) if ruta_salida else rutas.ruta_salida(f"reporte_morosos_{periodo or self.periodo}.xlsx")
        p.parent.mkdir(parents=True, exist_ok=True)
        import openpyxl
        from openpyxl.styles import Font, PatternFill

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Lista de Corte"

        ws["A1"] = f"CAAPD ISPACAS — LISTA DE USUARIOS CON CORTE DE SERVICIO ({periodo or self.periodo})"
        ws["A1"].font = Font(name="Arial", size=12, bold=True, color="FFFFFF")
        ws.merge_cells("A1:G1")
        for col in range(1, 8):
            ws.cell(row=1, column=col).fill = PatternFill(start_color="DC2626", end_color="DC2626", fill_type="solid")

        headers = ["Nro Conexión", "DNI", "Titular", "Sector", "Meses Deuda", "Total Deuda S/.", "Medidor"]
        for c, h in enumerate(headers, 1):
            cell = ws.cell(row=3, column=c, value=h)
            cell.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
            cell.fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")

        r_idx = 4
        for d in self.mes.values():
            meses = int(d.get("meses_adeudados") or 0)
            pagado = float(d.get("monto_pagado") or 0)
            total = float(d.get("total_a_pagar") or 0)
            if meses >= 3 and pagado < total:
                med_str = ", ".join(m.get("nro_medidor", "") for m in d.get("medidores", []))
                ws.cell(row=r_idx, column=1, value=d.get("nro_conexion", ""))
                ws.cell(row=r_idx, column=2, value=d.get("id_usuario", ""))
                ws.cell(row=r_idx, column=3, value=d.get("nombre", ""))
                ws.cell(row=r_idx, column=4, value=d.get("sector", ""))
                ws.cell(row=r_idx, column=5, value=meses)
                c_tot = ws.cell(row=r_idx, column=6, value=total)
                c_tot.number_format = '"S/. "#,##0.00'
                ws.cell(row=r_idx, column=7, value=med_str)
                r_idx += 1

        wb.save(str(p))
        return str(p)

    def listar_lectores(self) -> List[Dict[str, Any]]:
        return self.config.get("lectores") or []

    def crear_lector(self, email: str, password: str, display_name: Optional[str] = None) -> Dict[str, Any]:
        lectores = self.config.setdefault("lectores", [])
        nuevo = {
            "uid": f"lector_{len(lectores) + 1}",
            "email": email,
            "display_name": display_name or email.split("@")[0],
            "activo": True,
        }
        lectores.append(nuevo)
        self.guardar_en_respaldo_local()
        return nuevo

    def actualizar_lector(self, uid: str, cambios: Dict[str, Any]) -> Dict[str, Any]:
        lectores = self.config.get("lectores") or []
        for l in lectores:
            if l.get("uid") == uid:
                l.update(cambios)
                self.guardar_en_respaldo_local()
                return l
        raise ValueError(f"Lector {uid} no encontrado.")

    def eliminar_lector(self, uid: str) -> None:
        lectores = self.config.get("lectores") or []
        self.config["lectores"] = [l for l in lectores if l.get("uid") != uid]
        self.guardar_en_respaldo_local()

    def get_ops(self) -> Dict[str, int]:
        return self.ops

    def hay_aviso_ops(self) -> Dict[str, Optional[str]]:
        return {"lecturas": None, "escrituras": None}

    def limpiar_cache(self, limpiar_config: bool = True) -> None:
        """Recarga los datos únicamente desde la carpeta 'Base de datos/' o Padrón Excel local. Cero lecturas a Firestore."""
        archivos_bd = buscar_archivos_base_datos()
        if archivos_bd:
            self.cargar_desde_carpeta_base_datos()
            return

        cargado = False
        if self.ruta_excel and self.ruta_excel.exists():
            cargado = self._cargar_desde_excel(self.ruta_excel)
        if not cargado:
            p_mes = buscar_archivo_padron_mes()
            if p_mes and p_mes.exists():
                self._cargar_desde_padron_excel(p_mes)

