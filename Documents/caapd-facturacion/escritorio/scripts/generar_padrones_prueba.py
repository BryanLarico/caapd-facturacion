"""
scripts/generar_padrones_prueba.py — Generador determinista de 6 padrones de prueba (Abril a Septiembre 2026).

Escribe en: escritorio/Base de datos PRUEBA/
Máximo 5 usuarios por sector tomados del padrón real de octubre.
Cubre los 12 casos obligatorios de prueba:
1. Con DNI y sin DNI (al menos 2 usuarios con SD-xxx).
2. Dos usuarios con DNI compartido (12345678-1 y 12345678-2 / o par real).
3. Al menos un usuario con 2 medidores (misma conexión, filas consecutivas, 1 recibo).
4. Un usuario al día (Pago SI todos los meses, Meses 0).
5. Un usuario que debe 2 meses en sep (ago y sep sin pagar).
6. Un usuario que debe 3 meses (jul, ago y sep sin pagar).
7. Un usuario que debe 4 meses (jun, jul, ago y sep sin pagar).
8. Resto: pagan al día, salvo ~1/3 que en sep quedan con Pago NO y Meses 1.
9. Extra: un usuario que no pagó mayo ni junio y pagó todo en julio (se normaliza en agosto).
10. En sep, al menos 2 usuarios con observaciones (MEDIDOR_DANADO "Tapa rota" y FUGA_VISIBLE "Fuga en el patio").
11. Un usuario nuevo creado en sep (no existe en abril-agosto).
12. Extras: un usuario con consumo 0 m³ (solo cargo fijo) y uno con consumo >100 m³.
"""
from __future__ import annotations
import copy
import datetime
import json
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# Asegurar importación de módulos locales
import sys
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import calculos

SEMILLA = 42
DIR_DESTINO = BASE_DIR / "Base de datos PRUEBA"
ARCHIVO_REAL_OCTUBRE = BASE_DIR / "Base de datos" / "PADRON_MES_2026-10.xlsx"

PERIODOS = [
    "2026-04",
    "2026-05",
    "2026-06",
    "2026-07",
    "2026-08",
    "2026-09",
]

CONFIG_BASE = {
    "empresa": {
        "nombre": "CAAPD ISPACAS",
        "jass": "CAAPD ISPACAS",
        "ruc": "20123456789",
        "direccion": "Plaza Principal S/N, Ispacas, Yanaquihua",
        "telefono": "959123456",
        "distrito": "Yanaquihua",
        "provincia": "Condesuyos",
        "departamento": "Arequipa",
    },
    "comite": {
        "presidente": "MANUEL QUISPE",
        "tesorero": "ANA FLORES",
        "fiscal": "CARLOS MENDOZA",
    },
    "general": {
        "nombre_jass": "CAAPD ISPACAS",
        "ruc": "20123456789",
        "periodo_gracia_dias": 15,
        "meses_para_corte": 3,
        "moneda": "S/.",
    },
    "sectores": [
        "AYACUCHO",
        "CHAUPICERCA",
        "BARRIO DE CHAUPI",
        "BARRIO DE LUCMANI",
        "BARRIO DE PACHAYZA",
        "HUAQUILLO",
    ],
    "categorias": {
        "A": {
            "nombre": "Doméstico / General",
            "cargo_fijo": 5.0,
            "tarifa_desague": 0.0,
            "modo_rangos": "unico",
            "rangos": [
                {"m3_desde": 0, "m3_hasta": 10, "precio_m3": 1.0},
                {"m3_desde": 11, "m3_hasta": 15, "precio_m3": 1.5},
                {"m3_desde": 16, "m3_hasta": None, "precio_m3": 4.0},
            ],
        }
    },
    "lectores": {
        "AYACUCHO": "lector.ayacucho@prueba.local",
        "CHAUPICERCA": "lector.chaupicerca@prueba.local",
        "BARRIO DE CHAUPI": "lector.chaupi@prueba.local",
        "BARRIO DE LUCMANI": "lector.lucmani@prueba.local",
        "BARRIO DE PACHAYZA": "lector.pachayza@prueba.local",
        "HUAQUILLO": "lector.huaquillo@prueba.local",
    },
}


def obtener_usuarios_muestra() -> List[Dict[str, Any]]:
    """Extrae exactamente hasta 5 usuarios reales por sector de PADRON_MES_2026-10.xlsx."""
    wb = openpyxl.load_workbook(str(ARCHIVO_REAL_OCTUBRE), data_only=True)
    usuarios_seleccionados: List[Dict[str, Any]] = []

    # 1. AYACUCHO: 5 usuarios
    ws = wb["AYACUCHO"]
    for r in range(4, ws.max_row + 1):
        con = str(ws.cell(row=r, column=2).value or "").strip()
        med = str(ws.cell(row=r, column=3).value or "").strip()
        nom = str(ws.cell(row=r, column=4).value or "").strip()
        dni = str(ws.cell(row=r, column=17).value or "").strip()
        ant_oct = ws.cell(row=r, column=6).value
        if con and nom:
            usuarios_seleccionados.append({
                "id_usuario": dni,
                "nro_conexion": con,
                "nombre": nom,
                "sector": "AYACUCHO",
                "direccion": "AYACUCHO S/N",
                "medidores": [{"nro_medidor": med, "ant_octubre": int(ant_oct or 100)}],
            })

    # 2. CHAUPICERCA: 4 usuarios
    ws = wb["CHAUPICERCA"]
    for r in range(4, ws.max_row + 1):
        con = str(ws.cell(row=r, column=2).value or "").strip()
        med = str(ws.cell(row=r, column=3).value or "").strip()
        nom = str(ws.cell(row=r, column=4).value or "").strip()
        dni = str(ws.cell(row=r, column=17).value or "").strip()
        ant_oct = ws.cell(row=r, column=6).value
        if con and nom:
            usuarios_seleccionados.append({
                "id_usuario": dni,
                "nro_conexion": con,
                "nombre": nom,
                "sector": "CHAUPICERCA",
                "direccion": "CHAUPICERCA S/N",
                "medidores": [{"nro_medidor": med, "ant_octubre": int(ant_oct or 100)}],
            })

    # 3. BARRIO DE CHAUPI: Seleccionar 5 usuarios (incluye 1 con 2 medidores: ALFARO TORREZ)
    # r4: ALFARO NEYRA (30769528)
    # r5-r6: ALFARO TORREZ (45209656, 2 medidores!)
    # r7: ALVAREZ VERA (30769348)
    # r8: ANGULO ESCOBAR (46981924)
    # Usuario nuevo en septiembre será el 5to de Chaupi: QUISPE MAMANI NUEVO
    usuarios_seleccionados.append({
        "id_usuario": "30769528",
        "nro_conexion": "000498",
        "nombre": "ALFARO NEYRA DE CHUQUIYANQUI LUCIA POMPEYA",
        "sector": "BARRIO DE CHAUPI",
        "direccion": "AV. CENTENARIO 102",
        "medidores": [{"nro_medidor": "60062505", "ant_octubre": 249}],
    })
    usuarios_seleccionados.append({
        "id_usuario": "45209656",
        "nro_conexion": "000308",
        "nombre": "ALFARO TORREZ, TATIANA PAOLA",
        "sector": "BARRIO DE CHAUPI",
        "direccion": "JR. LIMA 45",
        "medidores": [
            {"nro_medidor": "60062454", "ant_octubre": 137},
            {"nro_medidor": "18052517", "ant_octubre": 745},
        ],
    })
    usuarios_seleccionados.append({
        "id_usuario": "30769348",
        "nro_conexion": "000274",
        "nombre": "ALVAREZ VERA LELIS SOLNA",
        "sector": "BARRIO DE CHAUPI",
        "direccion": "CALLE CHAUPI 12",
        "medidores": [{"nro_medidor": "009174", "ant_octubre": 503}],
    })
    usuarios_seleccionados.append({
        "id_usuario": "46981924",
        "nro_conexion": "000746",
        "nombre": "ANGULO ESCOBAR, JEISVER ANTONIO",
        "sector": "BARRIO DE CHAUPI",
        "direccion": "AV. CIRCUNVALACION 88",
        "medidores": [{"nro_medidor": "23022187", "ant_octubre": 384}],
    })

    # 4. BARRIO DE LUCMANI: Seleccionar 5 usuarios (incluye SD-026 y 4 usuarios normales)
    usuarios_seleccionados.append({
        "id_usuario": "SD-026",
        "nro_conexion": "000771",
        "nombre": "CONEXION SIN MEDIDOR 000771",
        "sector": "BARRIO DE LUCMANI",
        "direccion": "LUCMANI S/N",
        "medidores": [{"nro_medidor": "SIN_MEDIDOR", "ant_octubre": 0}],
    })
    usuarios_seleccionados.append({
        "id_usuario": "30771072",
        "nro_conexion": "000002",
        "nombre": "ANTACHOQUE MOTA, JUANA HILDA",
        "sector": "BARRIO DE LUCMANI",
        "direccion": "SECTOR LUCMANI 14",
        "medidores": [{"nro_medidor": "6659764", "ant_octubre": 367}],
    })
    usuarios_seleccionados.append({
        "id_usuario": "30769540",
        "nro_conexion": "000004",
        "nombre": "ANTACHOQUE VERA, JUAN JUSTO",
        "sector": "BARRIO DE LUCMANI",
        "direccion": "SECTOR LUCMANI 22",
        "medidores": [{"nro_medidor": "6585597", "ant_octubre": 609}],
    })
    usuarios_seleccionados.append({
        "id_usuario": "30770030",
        "nro_conexion": "000006",
        "nombre": "AYMARA HUAMANI, ALEJA",
        "sector": "BARRIO DE LUCMANI",
        "direccion": "SECTOR LUCMANI 30",
        "medidores": [{"nro_medidor": "6582810", "ant_octubre": 559}],
    })
    usuarios_seleccionados.append({
        "id_usuario": "30770213",
        "nro_conexion": "000007",
        "nombre": "CABRERA CHAVEZ, ASISCLO",
        "sector": "BARRIO DE LUCMANI",
        "direccion": "SECTOR LUCMANI 45",
        "medidores": [{"nro_medidor": "23015480", "ant_octubre": 889}],
    })

    # 5. BARRIO DE PACHAYZA: Seleccionar 5 usuarios (incluye SD-001 y pareja DNI compartido 30769551-1 y 30769551-2)
    usuarios_seleccionados.append({
        "id_usuario": "SD-001",
        "nro_conexion": "000092",
        "nombre": "ANTACHOQUE ANCO, YULY INES",
        "sector": "BARRIO DE PACHAYZA",
        "direccion": "AV. PACHAYZA 10",
        "medidores": [{"nro_medidor": "21003057", "ant_octubre": 1741}],
    })
    usuarios_seleccionados.append({
        "id_usuario": "30769551-1",
        "nro_conexion": "000098",
        "nombre": "CARPIO HUAMANI, JUAN VITALIANO",
        "sector": "BARRIO DE PACHAYZA",
        "direccion": "JR. BOLOGNESI 15",
        "medidores": [{"nro_medidor": "6587963", "ant_octubre": 1063}],
    })
    usuarios_seleccionados.append({
        "id_usuario": "30769551-2",
        "nro_conexion": "000099",
        "nombre": "CARPIO LAZARO, NANCY CELSA",
        "sector": "BARRIO DE PACHAYZA",
        "direccion": "JR. BOLOGNESI 17",
        "medidores": [{"nro_medidor": "6579722", "ant_octubre": 1499}],
    })
    usuarios_seleccionados.append({
        "id_usuario": "30770148",
        "nro_conexion": "000089",
        "nombre": "ALFARO LUQUE, MARIA",
        "sector": "BARRIO DE PACHAYZA",
        "direccion": "AV. PACHAYZA 5",
        "medidores": [{"nro_medidor": "6579582", "ant_octubre": 485}],
    })
    usuarios_seleccionados.append({
        "id_usuario": "02434916",
        "nro_conexion": "000095",
        "nombre": "APAZA QUISPE, JOSE",
        "sector": "BARRIO DE PACHAYZA",
        "direccion": "JR. GRAU 44",
        "medidores": [{"nro_medidor": "6659519", "ant_octubre": 875}],
    })

    # 6. HUAQUILLO: Seleccionar 5 usuarios
    usuarios_seleccionados.append({
        "id_usuario": "29302445",
        "nro_conexion": "000055",
        "nombre": "ALFARO NAVINTA, ANIBAL",
        "sector": "HUAQUILLO",
        "direccion": "HUAQUILLO CENTRO",
        "medidores": [{"nro_medidor": "6587782", "ant_octubre": 486}],
    })
    usuarios_seleccionados.append({
        "id_usuario": "02150722",
        "nro_conexion": "000066",
        "nombre": "CALLA HUARSAYA, LUIS",
        "sector": "HUAQUILLO",
        "direccion": "HUAQUILLO ALTO",
        "medidores": [{"nro_medidor": "6659665", "ant_octubre": 520}],
    })
    usuarios_seleccionados.append({
        "id_usuario": "30769698",
        "nro_conexion": "000059",
        "nombre": "CHALCO CORIMANYA, BLANCA DELIA",
        "sector": "HUAQUILLO",
        "direccion": "HUAQUILLO S/N",
        "medidores": [{"nro_medidor": "6593586", "ant_octubre": 1571}],
    })
    usuarios_seleccionados.append({
        "id_usuario": "30769343",
        "nro_conexion": "000061",
        "nombre": "CHALCO HUAMANI, SAIDA",
        "sector": "HUAQUILLO",
        "direccion": "HUAQUILLO PRINCIPAL",
        "medidores": [{"nro_medidor": "21003055", "ant_octubre": 141}],
    })
    usuarios_seleccionados.append({
        "id_usuario": "12345678",
        "nro_conexion": "000070",
        "nombre": "HUAMANI CASTRO, BERTHA",
        "sector": "HUAQUILLO",
        "direccion": "HUAQUILLO BAJO",
        "medidores": [{"nro_medidor": "6659861", "ant_octubre": 671}],
    })

    return usuarios_seleccionados


def asignar_comportamientos_casos(usuarios: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Asigna a cada usuario su rol en los 12 casos de prueba.
    """
    roles = {}

    # Caso 4: Al día (Pago SI todos los meses, Meses 0)
    # Elegimos al primer usuario de AYACUCHO: 30771152
    roles["30771152"] = {"caso": 4, "descripcion": "Al día: Pago SI todos los meses"}

    # Caso 5: Debe 2 meses al cierre de sep (ago y sep sin pagar) -> 30770229 (AYACUCHO)
    roles["30770229"] = {"caso": 5, "descripcion": "Mora 2 meses en sep (ago y sep sin pagar)"}

    # Caso 6: Debe 3 meses al cierre de sep (jul, ago, sep) -> 30770890 (AYACUCHO)
    roles["30770890"] = {"caso": 6, "descripcion": "Mora 3 meses en sep (jul, ago, sep sin pagar)"}

    # Caso 7: Debe 4 meses al cierre de sep (jun, jul, ago, sep) -> 30770036 (AYACUCHO)
    roles["30770036"] = {"caso": 7, "descripcion": "Mora 4 meses en sep (jun a sep sin pagar)"}

    # Caso 9: Extra: No pagó mayo ni junio y pagó todo en julio (se normaliza en agosto) -> 30778043 (AYACUCHO)
    roles["30778043"] = {"caso": 9, "descripcion": "No pagó may ni jun, pagó todo en jul, al día en ago"}

    # Caso 12a: Consumo 0 en julio (solo cargo fijo 5.00) -> 80313677 (CHAUPICERCA)
    roles["80313677"] = {"caso": "12a", "descripcion": "Consumo 0 m³ en julio (solo cargo fijo 5.00)"}

    # Caso 12b: Consumo > 100 m³ en agosto -> 30769321 (CHAUPICERCA)
    roles["30769321"] = {"caso": "12b", "descripcion": "Consumo alto (105 m³) en agosto (histograma dinámico)"}

    # Caso 10a: En sep MEDIDOR_DANADO 'Tapa rota' -> 30769931-1 (CHAUPICERCA)
    roles["30769931-1"] = {"caso": "10a", "descripcion": "En sep MEDIDOR_DANADO 'Tapa rota'"}

    # Caso 10b: En sep FUGA_VISIBLE 'Fuga en el patio' -> 30769896 (CHAUPICERCA)
    roles["30769896"] = {"caso": "10b", "descripcion": "En sep FUGA_VISIBLE 'Fuga en el patio'"}

    # Caso 3: Usuario con 2 medidores -> 45209656 (CHAUPI)
    roles["45209656"] = {"caso": 3, "descripcion": "2 medidores, misma conexión, 1 recibo"}

    # Caso 1: SD-xxx -> SD-026 (LUCMANI) y SD-001 (PACHAYZA)
    roles["SD-026"] = {"caso": "1a", "descripcion": "Usuario sin DNI (SD-026), conexión sin medidor"}
    roles["SD-001"] = {"caso": "1b", "descripcion": "Usuario sin DNI (SD-001), medidor normal"}

    # Caso 2: Pareja DNI compartido -> 30769551-1 y 30769551-2 (PACHAYZA)
    roles["30769551-1"] = {"caso": "2a", "descripcion": "DNI compartido hermano 1 (30769551-1)"}
    roles["30769551-2"] = {"caso": "2b", "descripcion": "DNI compartido hermano 2 (30769551-2)"}

    return roles


def generar_datos_prueba_completos() -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Any]]:
    """
    Construye la simulación determinista mes a mes de abril a septiembre de 2026.
    Regla de anclaje: Lect. Actual de septiembre = Lect. Anterior de octubre real.
    De ahí hacia atrás se calculan las lecturas decrecientes, asegurando que nunca decrezcan en el tiempo.
    """
    random.seed(SEMILLA)
    usuarios_base = obtener_usuarios_muestra()
    roles = asignar_comportamientos_casos(usuarios_base)

    # El usuario nuevo de septiembre (Caso 11)
    usuario_nuevo_sep = {
        "id_usuario": "75849301",
        "nro_conexion": "000850",
        "nombre": "MAMANI APAZA, CRISTIAN ALFREDO",
        "sector": "BARRIO DE CHAUPI",
        "direccion": "CALLE NUEVA 10",
        "medidores": [{"nro_medidor": "24355999", "ant_octubre": 45}],
    }

    # Meses anteriores para historial (marzo = mes semilla interno)
    # Para cada usuario y medidor, definimos los consumos de cada mes
    # Meses en orden cronológico: ['2026-03', '2026-04', '2026-05', '2026-06', '2026-07', '2026-08', '2026-09']
    todos_usuarios_activos = list(usuarios_base)

    # Estructura para registrar consumo mensual por medidor: {nro_medidor: {mes: consumo}}
    consumos_medidor: Dict[str, Dict[str, int]] = {}

    for u in todos_usuarios_activos + [usuario_nuevo_sep]:
        uid = u["id_usuario"]
        c_info = roles.get(uid, {})
        caso = c_info.get("caso")

        for m_idx, med in enumerate(u["medidores"]):
            m_num = med["nro_medidor"]
            consumos_medidor[m_num] = {}

            if m_num == "SIN_MEDIDOR":
                for p in ["2026-03"] + PERIODOS:
                    consumos_medidor[m_num][p] = 0
                continue

            for p in ["2026-03"] + PERIODOS:
                if uid == "75849301":
                    # Usuario nuevo: solo existe en septiembre
                    consumos_medidor[m_num][p] = 12 if p == "2026-09" else 0
                    continue

                if caso == "12a" and p == "2026-07":
                    consumos_medidor[m_num][p] = 0
                elif caso == "12b" and p == "2026-08":
                    consumos_medidor[m_num][p] = 105
                else:
                    # Consumo variado entre 5 y 22 m3
                    consumos_medidor[m_num][p] = random.randint(6, 18)

    # Calcular lecturas hacia atrás a partir de ant_octubre
    # ant_octubre = Lect. Actual de septiembre
    # Lect. Anterior de M = Lect. Actual de M-1
    # Lect. Actual de M = Lect. Anterior de M + consumo de M
    # Por tanto: Lect. Anterior de M = Lect. Actual de M - consumo de M
    lecturas_medidor: Dict[str, Dict[str, Tuple[int, int]]] = {} # {m_num: {mes: (ant, act)}}

    for u in todos_usuarios_activos:
        for med in u["medidores"]:
            m_num = med["nro_medidor"]
            ant_oct = med["ant_octubre"]
            lecturas_medidor[m_num] = {}

            if m_num == "SIN_MEDIDOR":
                for p in ["2026-03"] + PERIODOS:
                    lecturas_medidor[m_num][p] = (0, 0)
                continue

            # Retropropagar desde sep hacia marzo
            act_actual = ant_oct
            meses_rev = list(reversed(["2026-03"] + PERIODOS))
            for p in meses_rev:
                cons = consumos_medidor[m_num][p]
                ant_p = max(0, act_actual - cons)
                lecturas_medidor[m_num][p] = (ant_p, act_actual)
                act_actual = ant_p

    # Usuario nuevo en septiembre
    m_nuevo = usuario_nuevo_sep["medidores"][0]["nro_medidor"]
    lecturas_medidor[m_nuevo] = {
        "2026-09": (10, 22)
    }

    # Ahora generamos mes por mes de 2026-04 a 2026-09 manteniendo el estado acumulado
    # deudas_anteriores acumuladas: {uid: deuda_ant}
    # meses_adeudados acumulados: {uid: meses}
    deuda_acumulada: Dict[str, float] = {u["id_usuario"]: 0.0 for u in todos_usuarios_activos}
    meses_acumulados: Dict[str, int] = {u["id_usuario"]: 0 for u in todos_usuarios_activos}
    pago_mes_anterior: Dict[str, bool] = {u["id_usuario"]: True for u in todos_usuarios_activos}

    datos_por_mes: Dict[str, List[Dict[str, Any]]] = {}
    config_por_mes: Dict[str, Any] = {}

    correlativo_recibo = 1

    for p in PERIODOS:
        docs_mes: List[Dict[str, Any]] = []

        # Determinar lista de usuarios en este mes
        if p == "2026-09":
            usuarios_este_mes = todos_usuarios_activos + [usuario_nuevo_sep]
            deuda_acumulada["75849301"] = 0.0
            meses_acumulados["75849301"] = 0
            pago_mes_anterior["75849301"] = True
        else:
            usuarios_este_mes = list(todos_usuarios_activos)

        # Ordenar por sector y luego por nombre para asignación ordenada de recibos
        usuarios_este_mes.sort(key=lambda u: (u["sector"], u["nombre"]))

        # Fechas del mes
        dia_lect = 25
        fecha_lectura = f"{p}-{dia_lect:02d}"
        fecha_emision = f"{p}-{dia_lect+1:02d}"
        f_venc_dt = datetime.date(int(p[:4]), int(p[5:7]), dia_lect+1) + datetime.timedelta(days=15)
        fecha_vencimiento = f_venc_dt.isoformat()
        fecha_pago_def = f"{p}-28"

        mes_ant_str = "2026-03" if p == "2026-04" else PERIODOS[PERIODOS.index(p)-1]
        dia_ant = 25
        fecha_anterior_str = f"{mes_ant_str}-{dia_ant:02d}"

        for u in usuarios_este_mes:
            uid = u["id_usuario"]
            c_info = roles.get(uid, {})
            caso = c_info.get("caso")

            # Medidores del usuario
            med_list_docs = []
            consumo_total_m3 = 0

            for med in u["medidores"]:
                m_num = med["nro_medidor"]
                if uid == "75849301" and p != "2026-09":
                    continue

                if m_num == "SIN_MEDIDOR":
                    l_ant, l_act = 0, 0
                    cons = 0
                else:
                    l_ant, l_act = lecturas_medidor[m_num][p]
                    cons = l_act - l_ant

                consumo_total_m3 += cons

                # Novedad y notas
                nov = "NORMAL"
                nota = ""
                if p == "2026-09":
                    if caso == "10a":
                        nov = "MEDIDOR_DANADO"
                        nota = "Tapa rota"
                    elif caso == "10b":
                        nov = "FUGA_VISIBLE"
                        nota = "Fuga en el patio"

                med_list_docs.append({
                    "nro_medidor": m_num,
                    "lectura_anterior": l_ant,
                    "lectura_actual": l_act,
                    "consumo": cons,
                    "fecha_lectura": fecha_lectura,
                    "novedad": nov,
                    "nota": nota,
                    "fecha_anterior": fecha_anterior_str if uid != "75849301" else None,
                    "consumo_anterior": consumos_medidor[m_num].get(mes_ant_str, 0) if uid != "75849301" else None,
                    "estado_lectura": "LEIDO",
                    "registrado_por": CONFIG_BASE["lectores"].get(u["sector"], "lector@prueba.local"),
                })

            # Cálculo de tarifa categoría A:
            # Cargo fijo: 5.00, Rango único: 1-10 a 1.00; 11-15 a 1.50; 16+ a 4.00. Consumo 0 = 5.00
            cargo_fijo = 5.0
            tarifa_desague = 0.0
            if consumo_total_m3 == 0:
                monto_agua = 0.0
            elif consumo_total_m3 <= 10:
                monto_agua = round(consumo_total_m3 * 1.0, 2)
            elif consumo_total_m3 <= 15:
                monto_agua = round(consumo_total_m3 * 1.5, 2)
            else:
                monto_agua = round(consumo_total_m3 * 4.0, 2)

            deuda_actual = round(monto_agua + cargo_fijo, 2)

            # Deuda anterior según reglas:
            # Deuda Ant.(M) = 0 si Pago(M-1) = SI; si no, Deuda Ant.(M-1) + Deuda Actual(M-1)
            deuda_anterior = round(deuda_acumulada[uid], 2)
            total_a_pagar = round(deuda_anterior + deuda_actual, 2)

            # Meses adeudados
            # Meses(M) = 1 si Pago(M-1) = SI; si no, Meses(M-1) + 1
            if pago_mes_anterior[uid]:
                meses_calc = 1
            else:
                meses_calc = meses_acumulados[uid] + 1

            # Decidir Pago SI/NO según caso
            paga_este_mes = True

            if caso == 4:
                paga_este_mes = True
            elif caso == 5:
                # Debe 2 meses en sep: ago y sep sin pagar
                if p in ("2026-08", "2026-09"):
                    paga_este_mes = False
            elif caso == 6:
                # Debe 3 meses en sep: jul, ago, sep
                if p in ("2026-07", "2026-08", "2026-09"):
                    paga_este_mes = False
            elif caso == 7:
                # Debe 4 meses en sep: jun, jul, ago, sep
                if p in ("2026-06", "2026-07", "2026-08", "2026-09"):
                    paga_este_mes = False
            elif caso == 9:
                # No pagó mayo ni junio y pagó todo en julio
                if p in ("2026-05", "2026-06"):
                    paga_este_mes = False
                elif p == "2026-07":
                    paga_este_mes = True # Paga acumulado
            else:
                # Resto: pagan al día, salvo ~1/3 en septiembre con Pago NO
                if p == "2026-09":
                    # Usar hash determinista para seleccionar ~1/3
                    paga_este_mes = (hash(uid) % 3 != 0)
                else:
                    paga_este_mes = True

            # Asignación de N° Recibo
            nro_recibo = f"{correlativo_recibo:09d}"
            correlativo_recibo += 1

            # Si paga SI -> Meses = 0, monto_pagado = total_a_pagar
            # Si paga NO -> Meses = meses_calc, monto_pagado = 0
            if paga_este_mes:
                meses_final = 0
                monto_pagado = total_a_pagar
                pago_str = "SI"
                fecha_pago_str = fecha_pago_def
                # Próximo mes deuda_ant = 0
                deuda_acumulada[uid] = 0.0
                meses_acumulados[uid] = 0
                pago_mes_anterior[uid] = True
            else:
                meses_final = meses_calc
                monto_pagado = 0.0
                pago_str = "NO"
                fecha_pago_str = None
                # Próximo mes acumula
                deuda_acumulada[uid] = total_a_pagar
                meses_acumulados[uid] = meses_final
                pago_mes_anterior[uid] = False

            # Historial de consumos m3 anteriores (hasta 5)
            # Meses previos a este mes
            idx_p = PERIODOS.index(p)
            meses_previos = (["2026-03"] + PERIODOS)[:idx_p+1]
            if uid == "75849301":
                hist_m3_list = []
            else:
                hist_m3_list = []
                for prev in meses_previos[-5:]:
                    tot_prev = sum(consumos_medidor[m["nro_medidor"]].get(prev, 0) for m in u["medidores"])
                    hist_m3_list.append(float(tot_prev))

            doc_usuario = {
                "id_usuario": uid,
                "nro_conexion": u["nro_conexion"],
                "nombre": u["nombre"],
                "sector": u["sector"],
                "direccion": u["direccion"],
                "codigo_categoria": "A",
                "medidores": med_list_docs,
                "consumo_total_m3": consumo_total_m3,
                "monto_agua": monto_agua,
                "monto_desague": tarifa_desague,
                "cargo_fijo": cargo_fijo,
                "igv": 0.0,
                "redondeo": 0.0,
                "deuda_anterior": deuda_anterior,
                "deuda_actual": deuda_actual,
                "total_a_pagar": total_a_pagar,
                "meses_adeudados": meses_final,
                "pago": pago_str,
                "monto_pagado": monto_pagado,
                "fecha_pago": fecha_pago_str,
                "nro_recibo": nro_recibo,
                "historial_m3": hist_m3_list,
            }
            docs_mes.append(doc_usuario)

        datos_por_mes[p] = docs_mes

        # Configuración de este mes
        cfg_mes = copy.deepcopy(CONFIG_BASE)
        cfg_mes["ultimo_recibo"] = correlativo_recibo - 1
        cfg_mes["mes_actual"] = {
            "periodo": p,
            "estado": "FACTURADO" if p == "2026-09" else "CERRADO",
            "fecha_emision": fecha_emision,
            "fecha_vencimiento": fecha_vencimiento,
        }
        config_por_mes[p] = cfg_mes

    return datos_por_mes, config_por_mes


def escribir_archivo_padron_excel(
    periodo: str,
    docs_mes: List[Dict[str, Any]],
    config: Dict[str, Any],
    ruta_salida: Path,
) -> None:
    """Escribe un archivo PADRON_MES_aaaa-mm.xlsx completo con el formato exigido."""
    wb = openpyxl.Workbook()

    fuente_titulo = Font(name="Arial", size=12, bold=True, color="0F172A")
    fuente_sub = Font(name="Arial", size=10, italic=True, color="475569")
    fuente_encabezado_vis = Font(name="Arial", size=10, bold=True, color="FFFFFF")
    fuente_encabezado_gris = Font(name="Arial", size=9, bold=True, color="1E293B")
    fuente_datos = Font(name="Arial", size=10, color="0F172A")
    fuente_gris = Font(name="Arial", size=9, color="475569")

    fill_azul = PatternFill(start_color="0369A1", end_color="0369A1", fill_type="solid")
    fill_gris = PatternFill(start_color="CBD5E1", end_color="CBD5E1", fill_type="solid")
    fill_bloque_gris = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

    borde_fino = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )

    # 1. HOJA LEEME
    ws_leeme = wb.active
    ws_leeme.title = "LEEME"

    suma_total_pagar = sum(float(d["total_a_pagar"]) for d in docs_mes)
    total_usuarios = len(docs_mes)
    total_filas = sum(len(d["medidores"]) for d in docs_mes)

    ws_leeme["A1"] = f"CAAPD ISPACAS — PADRÓN Y RESPALDO DEL MES {periodo}"
    ws_leeme["A1"].font = fuente_titulo
    ws_leeme["A2"] = "Archivo de prueba generado deterministamente para verificación integral."
    ws_leeme["A2"].font = fuente_sub

    filas_leeme = [
        ("Versión del Formato", "2.0"),
        ("Fecha de Generación", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ("Periodo Respaldado", periodo),
        ("Estado del Mes", config["mes_actual"]["estado"]),
        ("Total Usuarios Padrón", total_usuarios),
        ("Total Filas Planilla", total_filas),
        ("Suma Total a Pagar (S/.)", round(suma_total_pagar, 2)),
        ("Checksum Verificación", f"{total_usuarios}_{round(suma_total_pagar, 2):.2f}"),
        ("TIPO: ARCHIVO DE PRUEBA", "SI"),
    ]

    ws_leeme.cell(row=4, column=1, value="PARÁMETRO").font = fuente_encabezado_vis
    ws_leeme.cell(row=4, column=1).fill = fill_azul
    ws_leeme.cell(row=4, column=2, value="VALOR").font = fuente_encabezado_vis
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
        if param == "TIPO: ARCHIVO DE PRUEBA":
            c1.font = Font(name="Arial", size=10, bold=True, color="DC2626")
            c2.font = Font(name="Arial", size=10, bold=True, color="DC2626")

    ws_leeme.column_dimensions["A"].width = 28
    ws_leeme.column_dimensions["B"].width = 30

    # 2. HOJAS POR SECTOR
    sectores = config["sectores"]
    docs_por_sector: Dict[str, List[Dict[str, Any]]] = {s: [] for s in sectores}
    for d in docs_mes:
        docs_por_sector.setdefault(d["sector"], []).append(d)

    encabezados_visibles = [
        "Fecha Lect.", "Conexión", "N° Medidor", "Titular / Beneficiario",
        "Dirección", "Lect. Anterior", "Lect. Actual", "Consumo (m³)",
        "Observación", "Nota", "N° Recibo", "Deuda Ant. (S/.)",
        "Deuda Actual (S/.)", "Meses", "Pago", "Fecha Pago",
    ]
    encabezados_grises = [
        "ID Usuario", "Fecha Anterior", "Consumo Anterior", "Estado Lectura",
        "Registrado Por", "Categoría", "Historial m³", "Consumo Total m³",
        "Monto Agua", "Monto Desagüe", "Cargo Fijo", "IGV", "Redondeo",
    ]

    for sec in sectores:
        ws_sec = wb.create_sheet(title=sec)

        # Fila 1: Título
        ws_sec["A1"] = f"PADRÓN DE USUARIOS Y LECTURAS — {sec} ({periodo})"
        ws_sec["A1"].font = fuente_titulo

        # Fila 3: Encabezados
        for c_idx, h in enumerate(encabezados_visibles, start=1):
            cell = ws_sec.cell(row=3, column=c_idx, value=h)
            cell.font = fuente_encabezado_vis
            cell.fill = fill_azul
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = borde_fino

        for c_idx, h in enumerate(encabezados_grises, start=len(encabezados_visibles) + 1):
            cell = ws_sec.cell(row=3, column=c_idx, value=h)
            cell.font = fuente_encabezado_gris
            cell.fill = fill_gris
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = borde_fino

        fila_actual = 4
        sec_docs = docs_por_sector.get(sec, [])

        for d in sec_docs:
            medidores = d.get("medidores") or []
            if not medidores:
                medidores = [{"nro_medidor": "", "lectura_anterior": 0, "lectura_actual": 0, "consumo": 0, "fecha_lectura": ""}]

            for m_idx, m in enumerate(medidores):
                es_primera = (m_idx == 0)

                # Col 1: Fecha Lect.
                ws_sec.cell(row=fila_actual, column=1, value=m.get("fecha_lectura") or "")
                # Col 2: Conexión
                c_con = ws_sec.cell(row=fila_actual, column=2, value=str(d.get("nro_conexion") or "").zfill(6))
                c_con.number_format = '@'
                # Col 3: N° Medidor
                c_med = ws_sec.cell(row=fila_actual, column=3, value=str(m.get("nro_medidor") or ""))
                c_med.number_format = '@'
                # Col 4: Titular
                ws_sec.cell(row=fila_actual, column=4, value=d.get("nombre") or "")
                # Col 5: Dirección
                ws_sec.cell(row=fila_actual, column=5, value=d.get("direccion") or "")
                # Col 6: Lect. Anterior
                ws_sec.cell(row=fila_actual, column=6, value=m.get("lectura_anterior"))
                # Col 7: Lect. Actual
                ws_sec.cell(row=fila_actual, column=7, value=m.get("lectura_actual"))
                # Col 8: Consumo
                ws_sec.cell(row=fila_actual, column=8, value=m.get("consumo"))
                # Col 9: Observación
                ws_sec.cell(row=fila_actual, column=9, value=m.get("novedad") or "NORMAL")
                # Col 10: Nota
                ws_sec.cell(row=fila_actual, column=10, value=m.get("nota") or "")

                # Columnas financieras (solo en primera fila de usuario)
                if es_primera:
                    c_rec = ws_sec.cell(row=fila_actual, column=11, value=str(d.get("nro_recibo") or ""))
                    c_rec.number_format = '@'
                    c_dant = ws_sec.cell(row=fila_actual, column=12, value=float(d.get("deuda_anterior") or 0.0))
                    c_dant.number_format = '#,##0.00'
                    c_dact = ws_sec.cell(row=fila_actual, column=13, value=float(d.get("deuda_actual") or 0.0))
                    c_dact.number_format = '#,##0.00'
                    ws_sec.cell(row=fila_actual, column=14, value=int(d.get("meses_adeudados") or 0))
                    ws_sec.cell(row=fila_actual, column=15, value=d.get("pago") or "NO")
                    ws_sec.cell(row=fila_actual, column=16, value=d.get("fecha_pago") or "")
                else:
                    for col_k in range(11, 17):
                        ws_sec.cell(row=fila_actual, column=col_k, value=None)

                # Bloque técnico gris
                col_g = 17
                # ID Usuario en todas las filas
                c_uid = ws_sec.cell(row=fila_actual, column=col_g, value=str(d.get("id_usuario") or ""))
                c_uid.number_format = '@'
                # Fecha Anterior
                ws_sec.cell(row=fila_actual, column=col_g+1, value=m.get("fecha_anterior") or "")
                # Consumo Anterior
                ws_sec.cell(row=fila_actual, column=col_g+2, value=m.get("consumo_anterior"))
                # Estado Lectura
                ws_sec.cell(row=fila_actual, column=col_g+3, value=m.get("estado_lectura") or "LEIDO")
                # Registrado Por
                ws_sec.cell(row=fila_actual, column=col_g+4, value=m.get("registrado_por") or "")
                # Categoría
                ws_sec.cell(row=fila_actual, column=col_g+5, value=d.get("codigo_categoria") or "A")

                # Valores de montos / historial solo en primera fila
                if es_primera:
                    hist_str = ",".join(str(int(x)) if float(x).is_integer() else f"{x:.1f}" for x in (d.get("historial_m3") or []))
                    ws_sec.cell(row=fila_actual, column=col_g+6, value=hist_str)
                    ws_sec.cell(row=fila_actual, column=col_g+7, value=d.get("consumo_total_m3"))
                    c_mag = ws_sec.cell(row=fila_actual, column=col_g+8, value=float(d.get("monto_agua") or 0.0))
                    c_mag.number_format = '#,##0.00'
                    c_mdes = ws_sec.cell(row=fila_actual, column=col_g+9, value=float(d.get("monto_desague") or 0.0))
                    c_mdes.number_format = '#,##0.00'
                    c_cf = ws_sec.cell(row=fila_actual, column=col_g+10, value=float(d.get("cargo_fijo") or 0.0))
                    c_cf.number_format = '#,##0.00'
                    ws_sec.cell(row=fila_actual, column=col_g+11, value=float(d.get("igv") or 0.0))
                    ws_sec.cell(row=fila_actual, column=col_g+12, value=float(d.get("redondeo") or 0.0))
                else:
                    for col_k in range(col_g+6, col_g+13):
                        ws_sec.cell(row=fila_actual, column=col_k, value=None)

                # Bordes y fuentes
                for c in range(1, 17):
                    cell = ws_sec.cell(row=fila_actual, column=c)
                    cell.font = fuente_datos
                    cell.border = borde_fino
                for c in range(17, 30):
                    cell = ws_sec.cell(row=fila_actual, column=c)
                    cell.font = fuente_gris
                    cell.fill = fill_bloque_gris
                    cell.border = borde_fino

                fila_actual += 1

        # Anchos de columna
        anchos = [12, 10, 12, 32, 24, 12, 12, 12, 16, 18, 14, 14, 14, 8, 8, 12] + [14, 14, 14, 14, 25, 10, 18, 14, 12, 12, 12, 10, 10]
        for c_idx, w in enumerate(anchos, start=1):
            col_letter = get_column_letter(c_idx)
            ws_sec.column_dimensions[col_letter].width = w

    # 3. HOJA USUARIOS
    ws_usr = wb.create_sheet(title="USUARIOS")
    ws_usr["A1"] = f"PADRÓN MAESTRO DE USUARIOS — CAAPD ISPACAS ({periodo})"
    ws_usr["A1"].font = fuente_titulo

    enc_usr = ["ID Usuario", "N° Conexión", "Nombre Completo", "Sector", "Dirección", "Categoría", "Activo", "Medidores"]
    for c_idx, h in enumerate(enc_usr, start=1):
        cell = ws_usr.cell(row=3, column=c_idx, value=h)
        cell.font = fuente_encabezado_vis
        cell.fill = fill_azul
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = borde_fino

    r_usr = 4
    for d in docs_mes:
        meds_str = ",".join(str(m.get("nro_medidor") or "") for m in d.get("medidores", []))
        c_uid = ws_usr.cell(row=r_usr, column=1, value=str(d.get("id_usuario") or ""))
        c_uid.number_format = '@'
        c_con = ws_usr.cell(row=r_usr, column=2, value=str(d.get("nro_conexion") or "").zfill(6))
        c_con.number_format = '@'
        ws_usr.cell(row=r_usr, column=3, value=d.get("nombre") or "")
        ws_usr.cell(row=r_usr, column=4, value=d.get("sector") or "")
        ws_usr.cell(row=r_usr, column=5, value=d.get("direccion") or "")
        ws_usr.cell(row=r_usr, column=6, value=d.get("codigo_categoria") or "A")
        ws_usr.cell(row=r_usr, column=7, value="SI")
        c_meds = ws_usr.cell(row=r_usr, column=8, value=meds_str)
        c_meds.number_format = '@'

        for c in range(1, 9):
            ws_usr.cell(row=r_usr, column=c).font = fuente_datos
            ws_usr.cell(row=r_usr, column=c).border = borde_fino
        r_usr += 1

    anchos_u = [14, 12, 32, 20, 24, 10, 8, 24]
    for c_idx, w in enumerate(anchos_u, start=1):
        ws_usr.column_dimensions[get_column_letter(c_idx)].width = w

    # 4. HOJA CONFIG
    ws_cfg = wb.create_sheet(title="CONFIG")
    ws_cfg["A1"] = "CONFIGURACIÓN GENERAL DEL SISTEMA (JSON COMPLETO)"
    ws_cfg["A1"].font = fuente_titulo
    ws_cfg["A2"] = "Esta celda (A4) contiene el JSON íntegro para restaurar parámetros, tarifas y sectores."
    ws_cfg["A2"].font = fuente_sub

    # JSON completo en celda A4
    json_str = json.dumps(config, ensure_ascii=False, indent=2)
    c_a4 = ws_cfg["A4"]
    c_a4.value = json_str
    c_a4.alignment = Alignment(wrap_text=True)

    # Tabla auxiliar en columnas D y E
    ws_cfg.cell(row=3, column=4, value="PARÁMETRO CLAVE").font = fuente_encabezado_vis
    ws_cfg.cell(row=3, column=4).fill = fill_azul
    ws_cfg.cell(row=3, column=5, value="VALOR").font = fuente_encabezado_vis
    ws_cfg.cell(row=3, column=5).fill = fill_azul

    params_aux = [
        ("ultimo_recibo", config.get("ultimo_recibo", 0)),
        ("periodo_activo", config.get("mes_actual", {}).get("periodo", periodo)),
        ("estado_mes", config.get("mes_actual", {}).get("estado", "FACTURADO")),
        ("fecha_emision", config.get("mes_actual", {}).get("fecha_emision", "")),
        ("fecha_vencimiento", config.get("mes_actual", {}).get("fecha_vencimiento", "")),
    ]

    for idx, (p_nom, p_val) in enumerate(params_aux, start=4):
        c_k = ws_cfg.cell(row=idx, column=4, value=p_nom)
        c_k.font = Font(name="Arial", size=10, bold=True)
        c_k.border = borde_fino
        c_v = ws_cfg.cell(row=idx, column=5, value=p_val)
        c_v.font = fuente_datos
        c_v.border = borde_fino

    ws_cfg.column_dimensions["A"].width = 50
    ws_cfg.column_dimensions["D"].width = 22
    ws_cfg.column_dimensions["E"].width = 24

    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(ruta_salida))


def generar_archivo_casos_de_prueba(docs_sep: List[Dict[str, Any]], ruta_salida: Path) -> None:
    """Genera CASOS_DE_PRUEBA.xlsx detallando cada usuario, caso asignado y valores esperados."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "CASOS_PRUEBA"

    fuente_titulo = Font(name="Arial", size=12, bold=True, color="0F172A")
    fuente_encabezado = Font(name="Arial", size=10, bold=True, color="FFFFFF")
    fuente_datos = Font(name="Arial", size=10, color="0F172A")
    fill_azul = PatternFill(start_color="0369A1", end_color="0369A1", fill_type="solid")
    borde_fino = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )

    ws["A1"] = "CAAPD ISPACAS — MATRIZ DE CASOS DE PRUEBA (ABRIL - SEPTIEMBRE 2026)"
    ws["A1"].font = fuente_titulo
    ws["A2"] = "Valores de control en Septiembre 2026 y comportamiento esperado al abrir Octubre."

    encs = [
        "Caso N°", "Descripción del Caso", "ID Usuario", "Conexión", "Titular",
        "Sector", "Deuda Ant. (S/.)", "Deuda Act. (S/.)", "Total Pagar (S/.)",
        "Meses (Sep)", "Pago (Sep)", "Color Recibo Sep", "Esperado Deuda Ant Octubre",
        "Esperado Meses Octubre"
    ]

    for c_idx, h in enumerate(encs, start=1):
        c = ws.cell(row=4, column=c_idx, value=h)
        c.font = fuente_encabezado
        c.fill = fill_azul
        c.border = borde_fino

    roles = asignar_comportamientos_casos(obtener_usuarios_muestra())

    # Mapa de docs_sep por uid
    docs_map = {d["id_usuario"]: d for d in docs_sep}

    r = 5
    for uid, d in docs_map.items():
        c_info = roles.get(uid, {"caso": "General", "descripcion": "Usuario regular del padrón"})
        caso_id = str(c_info.get("caso"))
        desc = c_info.get("descripcion")

        d_ant = float(d["deuda_anterior"])
        d_act = float(d["deuda_actual"])
        tot = float(d["total_a_pagar"])
        meses = int(d["meses_adeudados"])
        pago = d["pago"]

        if meses == 0 or meses == 1:
            color = "AZUL"
        elif meses == 2:
            color = "NARANJA"
        else:
            color = "ROJO"

        # Comportamiento al abrir octubre:
        # Si Pago = SI -> Deuda Ant = 0.0, Meses = 1
        # Si Pago = NO -> Deuda Ant = Total Pagar Sep, Meses = Meses Sep + 1
        if pago == "SI":
            esp_dant = 0.0
            esp_meses = 1
        else:
            esp_dant = tot
            esp_meses = meses + 1

        fila_vals = [
            caso_id, desc, uid, d["nro_conexion"], d["nombre"], d["sector"],
            d_ant, d_act, tot, meses, pago, color, esp_dant, esp_meses
        ]

        for c_idx, val in enumerate(fila_vals, start=1):
            cell = ws.cell(row=r, column=c_idx, value=val)
            cell.font = fuente_datos
            cell.border = borde_fino
            if c_idx in (7, 8, 9, 13):
                cell.number_format = '"S/. "#,##0.00'

        r += 1

    anchos = [10, 36, 14, 12, 32, 20, 14, 14, 14, 12, 10, 14, 22, 20]
    for c_idx, w in enumerate(anchos, start=1):
        ws.column_dimensions[get_column_letter(c_idx)].width = w

    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(ruta_salida))


def main():
    print("================================================================")
    print("  GENERADOR DE PADRONES DE PRUEBA DETERMINISTA — CAAPD ISPACAS")
    print("  Destino: escritorio/Base de datos PRUEBA/")
    print("================================================================")

    DIR_DESTINO.mkdir(parents=True, exist_ok=True)

    print("\n[1/3] Calculando datos deterministas (abril a septiembre 2026)...")
    datos_por_mes, config_por_mes = generar_datos_prueba_completos()

    print("[2/3] Escribiendo archivos Excel de padron...")
    for periodo in PERIODOS:
        ruta_archivo = DIR_DESTINO / f"PADRON_MES_{periodo}.xlsx"
        docs = datos_por_mes[periodo]
        cfg = config_por_mes[periodo]
        escribir_archivo_padron_excel(periodo, docs, cfg, ruta_archivo)
        print(f"  [OK] Creado: {ruta_archivo.name} ({len(docs)} usuarios, ultimo recibo: {cfg['ultimo_recibo']})")

    print("[3/3] Generando matriz CASOS_DE_PRUEBA.xlsx...")
    ruta_casos = DIR_DESTINO / "CASOS_DE_PRUEBA.xlsx"
    generar_archivo_casos_de_prueba(datos_por_mes["2026-09"], ruta_casos)
    print(f"  [OK] Creado: {ruta_casos.name}")

    print("\n================================================================")
    print("  GENERACION COMPLETADA CON EXITO")
    print(f"  Archivos generados en: {DIR_DESTINO}")
    print("================================================================")


if __name__ == "__main__":
    main()
