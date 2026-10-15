"""
scripts/generar_recibos_muestra.py — Genera recibos PDF de muestra desde el padrón real.

Toma usuarios del padrón histórico (LISTA DE USUARIOS 2026.xlsx y RELACION...),
calcula sus recibos y genera 3 PDFs demostrativos en salida/recibos_muestra/:
  1. Recibo AZUL (1 mes de deuda / al día)
  2. Recibo NARANJA (2 meses de deuda)
  3. Recibo ROJO (3 meses de deuda - aviso de corte)
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

# Configurar rutas
DIR_BASE = Path(__file__).resolve().parent.parent
if str(DIR_BASE) not in sys.path:
    sys.path.insert(0, str(DIR_BASE))

import rutas
from scripts.importar_excel import procesar_migracion
from calculos import calcular_monto_agua, calcular_recibo
from servicios.generador_pdf import generar_recibo_pdf


def generar_muestras() -> list[Path]:
    ruta_lista = rutas.ruta_datos("LISTA DE USUARIOS 2026.xlsx")
    ruta_relacion = rutas.ruta_datos("RELACION_DE_USUARIOS_DEL_CAAPD.xlsx")

    print("[1/3] Cargando padrón de usuarios desde Excel...")
    usuarios, semilla, aux = procesar_migracion(str(ruta_lista), str(ruta_relacion))
    print(f"      Padrón cargado con éxito: {len(usuarios)} usuarios encontrados.")

    # Carpeta de salida
    dir_salida = rutas.ruta_salida("recibos_muestra")
    dir_salida.mkdir(parents=True, exist_ok=True)

    # Filtrar usuarios con medidor y lecturas para las muestras
    candidatos = [
        u for u in usuarios.values()
        if u.get("activo") and u.get("medidores") and len(u.get("medidores")) > 0
    ]
    if len(candidatos) < 3:
        candidatos = list(usuarios.values())[:3]

    # Configuraciones de prueba para los 3 niveles de mora
    casos = [
        {
            "color_nombre": "AZUL",
            "meses": 1,
            "deuda_ant": 0.0,
            "archivo": "recibo_1_azul_al_dia.pdf",
            "desc": "1 mes / Al día",
        },
        {
            "color_nombre": "NARANJA",
            "meses": 2,
            "deuda_ant": 17.50,
            "archivo": "recibo_2_naranja_dos_meses.pdf",
            "desc": "2 meses adeudados",
        },
        {
            "color_nombre": "ROJO",
            "meses": 3,
            "deuda_ant": 35.00,
            "archivo": "recibo_3_rojo_tres_meses_corte.pdf",
            "desc": "3 meses adeudados (Aviso de corte)",
        },
    ]

    print("[2/3] Generando recibos en PDF con coordenadas oficiales...")
    archivos_generados = []

    for idx, caso in enumerate(casos):
        u = candidatos[idx % len(candidatos)]
        medidores_usuario = u.get("medidores") or ["001000"]
        n_med = medidores_usuario[0]

        # Lecturas del padrón o estimadas
        sem_m = semilla.get(n_med) or {}
        l_ant = float(sem_m.get("lectura_anterior") or 40.0)
        l_act = float(sem_m.get("lectura_actual") or (l_ant + 16.0))
        consumo_m3 = max(0.0, l_act - l_ant)

        # Cálculo tarifario
        rangos_ejemplo = [
            {"m3_desde": 0, "m3_hasta": 20, "precio_m3": 1.00},
            {"m3_desde": 21, "m3_hasta": 40, "precio_m3": 1.20},
            {"m3_desde": 41, "m3_hasta": None, "precio_m3": 1.50},
        ]
        cargo_fijo = 1.50
        monto_agua = calcular_monto_agua(consumo_m3, rangos_ejemplo, modo_rangos="unico")
        monto_desague = 0.0
        deuda_anterior = caso["deuda_ant"]

        subtotal_afecto = monto_agua + monto_desague + cargo_fijo
        igv = 0.0
        total_sin_redondeo = subtotal_afecto + deuda_anterior + igv
        redondeo = round(total_sin_redondeo % 0.10, 2)
        total_a_pagar = round(total_sin_redondeo - redondeo, 2)

        # Historial de consumos para el histograma
        historico = {
            "ABR": max(2.0, consumo_m3 - 4),
            "MAY": max(5.0, consumo_m3 + 2),
            "JUN": max(3.0, consumo_m3 - 2),
            "JUL": max(6.0, consumo_m3 + 5),
            "AGO": max(4.0, consumo_m3 + 1),
            "SET": consumo_m3,
        }

        datos_recibo = {
            "numero_recibo": 1001 + idx,
            "periodo": "2026-09",
            "temporada": "SEPTIEMBRE 2026",
            "fecha_emision": "01-09-2026",
            "ultimo_dia_pago": "20/09/2026",
            "conexion": u.get("nro_conexion") or "000796",
            "nombre": u.get("nombre") or "USUARIO DE PRUEBA",
            "dni_ruc": u.get("id_usuario") or "30771072",
            "zona": u.get("sector") or "CENTRO",
            "direccion": u.get("direccion") or "CALLE PRINCIPAL S/N",
            "categoria": "DOMESTICO",
            "medidores": [
                {
                    "medidor": n_med,
                    "lectura_anterior": l_ant,
                    "fecha_anterior": "07-08-2026",
                    "lectura_actual": l_act,
                    "fecha_actual": "07-09-2026",
                    "consumo": consumo_m3,
                }
            ],
            "servicio_agua": monto_agua,
            "servicio_desague": monto_desague,
            "cargo_fijo": cargo_fijo,
            "deuda_anterior": deuda_anterior,
            "meses_adeudados": caso["meses"],
            "subtotal": subtotal_afecto + deuda_anterior,
            "igv": igv,
            "redondeo": redondeo,
            "total_a_pagar": total_a_pagar,
            "consumos_historicos": historico,
            "resolucion": "RESOLUCION 192-2017",
            "whatsapp_url": "https://api.whatsapp.com/send?phone=51986054179&text=Consulta%20recibo",
        }

        destino = dir_salida / caso["archivo"]
        generar_recibo_pdf(datos_recibo, destino)
        archivos_generados.append(destino)
        print(f"      [{caso['color_nombre']}] Generado: {destino.name} ({caso['desc']}) -> S/. {total_a_pagar:.2f}")

    print("[3/3] ¡Recibos de muestra generados exitosamente!")
    return archivos_generados


if __name__ == "__main__":
    generar_muestras()
