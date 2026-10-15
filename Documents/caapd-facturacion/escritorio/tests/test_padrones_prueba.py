"""
tests/test_padrones_prueba.py — Verificaciones de los padrones de prueba (Abril a Septiembre 2026).
"""
from __future__ import annotations
from pathlib import Path
import openpyxl
import pytest

import rutas
import respaldo_excel
from servicios.datos_padron import (
    buscar_archivos_base_datos,
    validar_archivos_sin_duplicados,
    ServicioDatosPadron,
)

DIR_PRUEBA = rutas.DIR_BASE / "Base de datos PRUEBA"
PERIODOS = ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]


def test_existencia_archivos_y_sin_octubre():
    """Verifica que existan los 6 meses requeridos y NINGUNO de octubre."""
    archivos = list(DIR_PRUEBA.glob("PADRON_MES_*.xlsx"))
    nombres = [a.name for a in archivos]

    for p in PERIODOS:
        assert f"PADRON_MES_{p}.xlsx" in nombres, f"Falta archivo del mes {p}"

    # Regla de seguridad: NO debe existir archivo de octubre
    assert "PADRON_MES_2026-10.xlsx" not in nombres
    assert not any("2026-10" in n for n in nombres)


def test_maximo_5_usuarios_por_sector():
    """Verifica que en cada archivo y en cada sector haya un máximo de 5 usuarios."""
    for p in PERIODOS:
        ruta = DIR_PRUEBA / f"PADRON_MES_{p}.xlsx"
        wb = openpyxl.load_workbook(str(ruta), data_only=True)
        sectores = [s for s in wb.sheetnames if s not in ("LEEME", "USUARIOS", "CONFIG")]

        for sec in sectores:
            ws = wb[sec]
            uids = set()
            for r in range(4, ws.max_row + 1):
                uid = ws.cell(row=r, column=17).value
                if uid:
                    uids.add(str(uid).strip())
            assert len(uids) <= 5, f"Sector {sec} en {p} tiene {len(uids)} usuarios (> 5)"


def test_consistencia_lecturas_y_consumos():
    """Verifica que Lect. Anterior(M) == Lect. Actual(M-1) y consumo == actual - anterior."""
    datos_meses = {}
    for p in PERIODOS:
        ruta = DIR_PRUEBA / f"PADRON_MES_{p}.xlsx"
        datos_meses[p] = respaldo_excel.leer_respaldo_excel(ruta)

    for i in range(1, len(PERIODOS)):
        p_prev = PERIODOS[i - 1]
        p_act = PERIODOS[i]
        docs_prev = datos_meses[p_prev]["mes_docs"]
        docs_act = datos_meses[p_act]["mes_docs"]

        for uid, doc in docs_act.items():
            if uid == "75849301":
                # Usuario nuevo de septiembre: no existía en p_prev
                assert uid not in docs_prev
                continue

            assert uid in docs_prev, f"Usuario {uid} no encontrado en {p_prev}"
            doc_prev = docs_prev[uid]

            # Mapear medidores
            meds_prev = {m["nro_medidor"]: m for m in doc_prev["medidores"]}
            for m_act in doc["medidores"]:
                m_num = m_act["nro_medidor"]
                if m_num == "SIN_MEDIDOR":
                    continue
                assert m_num in meds_prev
                m_prev = meds_prev[m_num]

                # Lect. Anterior de hoy == Lect. Actual del mes anterior
                assert m_act["lectura_anterior"] == m_prev["lectura_actual"], (
                    f"Mes {p_act}, medidor {m_num}: anterior {m_act['lectura_anterior']} != previo {m_prev['lectura_actual']}"
                )
                # Consumo = actual - anterior
                assert m_act["consumo"] == (m_act["lectura_actual"] - m_act["lectura_anterior"])


def test_recibos_correlativos_sin_saltos():
    """Verifica que los recibos sean estrictamente correlativos entre meses."""
    ultimo_rec = 0
    todos_recibos = []

    for p in PERIODOS:
        ruta = DIR_PRUEBA / f"PADRON_MES_{p}.xlsx"
        datos = respaldo_excel.leer_respaldo_excel(ruta)
        docs = datos["mes_docs"]

        recibos_mes = []
        for d in docs.values():
            r = int(d["nro_recibo"])
            recibos_mes.append(r)
            todos_recibos.append(r)

        recibos_mes.sort()
        # El primero del mes debe ser el siguiente al último del mes anterior
        assert recibos_mes[0] == ultimo_rec + 1
        # Dentro del mes no debe haber saltos
        for j in range(1, len(recibos_mes)):
            assert recibos_mes[j] == recibos_mes[j-1] + 1

        ultimo_rec = recibos_mes[-1]
        assert datos["config"]["ultimo_recibo"] == ultimo_rec

    # Sin repetidos en ningún mes
    assert len(todos_recibos) == len(set(todos_recibos))


def test_casos_obligatorios_cubiertos():
    """Verifica la cobertura de los 12 casos obligatorios."""
    ruta_sep = DIR_PRUEBA / "PADRON_MES_2026-09.xlsx"
    sep = respaldo_excel.leer_respaldo_excel(ruta_sep)
    docs_sep = sep["mes_docs"]

    # Caso 1: SD-xxx
    sds = [uid for uid in docs_sep if str(uid).startswith("SD-")]
    assert len(sds) >= 2, f"Se esperaban >= 2 SD, hay {len(sds)}"

    # Caso 2: DNI compartido
    assert "30769551-1" in docs_sep
    assert "30769551-2" in docs_sep

    # Caso 3: Usuario con 2 medidores
    assert "45209656" in docs_sep
    u_2med = docs_sep["45209656"]
    assert len(u_2med["medidores"]) == 2
    assert u_2med["nro_recibo"] is not None

    # Caso 4: Al día todos los meses
    assert docs_sep["30771152"]["meses_adeudados"] == 0
    assert docs_sep["30771152"]["pago"] == "SI"

    # Caso 5: Mora 2 meses en sep
    assert docs_sep["30770229"]["meses_adeudados"] == 2
    assert docs_sep["30770229"]["pago"] == "NO"

    # Caso 6: Mora 3 meses en sep (lista de corte)
    assert docs_sep["30770890"]["meses_adeudados"] == 3
    assert docs_sep["30770890"]["pago"] == "NO"

    # Caso 7: Mora 4 meses en sep
    assert docs_sep["30770036"]["meses_adeudados"] == 4
    assert docs_sep["30770036"]["pago"] == "NO"

    # Caso 9: Pagó en julio deuda acumulada y se normalizó
    assert docs_sep["30778043"]["meses_adeudados"] == 0
    assert docs_sep["30778043"]["pago"] == "SI"

    # Caso 10: Observaciones en septiembre
    obs_distintas = set()
    for d in docs_sep.values():
        for m in d["medidores"]:
            if m.get("novedad") not in ("", "NORMAL"):
                obs_distintas.add(m["novedad"])
    assert "MEDIDOR_DANADO" in obs_distintas
    assert "FUGA_VISIBLE" in obs_distintas

    # Caso 11: Usuario nuevo de septiembre
    assert "75849301" in docs_sep
    for p in PERIODOS[:-1]:
        d_prev = respaldo_excel.leer_respaldo_excel(DIR_PRUEBA / f"PADRON_MES_{p}.xlsx")
        assert "75849301" not in d_prev["mes_docs"]
        assert "75849301" not in d_prev["usuarios"]


def test_carga_servicio_datos_padron_entorno_prueba(monkeypatch):
    """Verifica que ServicioDatosPadron en modo prueba cargue los 6 meses y fije 2026-09 como activo."""
    monkeypatch.setenv("CAAPD_ENTORNO", "prueba")
    monkeypatch.setattr(rutas, "ruta_base_de_datos", lambda p="": DIR_PRUEBA if not p else DIR_PRUEBA / p)

    servicio = ServicioDatosPadron(base_dir=DIR_PRUEBA)
    assert len(servicio.usuarios) >= 28
    assert len(servicio.mes) >= 28
    assert servicio.periodo == "2026-09"
    assert servicio.config["mes_actual"]["periodo"] == "2026-09"
    assert servicio.config["mes_actual"]["estado"] == "FACTURADO"
