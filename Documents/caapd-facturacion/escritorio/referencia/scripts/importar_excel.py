"""
scripts/importar_excel.py — Importación inicial del padrón desde los dos Excel históricos.

Fuentes:
  - datos/LISTA DE USUARIOS 2026.xlsx (DNI, estado, medidor, sector, dirección)
  - datos/RELACION_DE_USUARIOS_DEL_CAAPD.xlsx (hojas por sector: número de conexión, lecturas)

Uso:
  python scripts/importar_excel.py --simular
  python scripts/importar_excel.py
"""

from __future__ import annotations
import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict
from typing import Any

import openpyxl

# Agregar directorio raíz al PYTHONPATH si se corre directo
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from codigos import (
    normalizar_medidor,
    normalizar_conexion,
    normalizar_dni,
    es_id_pendiente,
    limpiar_texto,
)


def buscar_archivo_lista() -> str:
    """Encuentra el archivo de lista de usuarios en datos/."""
    candidatos = [
        os.path.join(BASE_DIR, "datos", "LISTA DE USUARIOS 2026.xlsx"),
        os.path.join(BASE_DIR, "datos", "LISTA_DE_USUARIOS_2026.xlsx"),
    ]
    for c in candidatos:
        if os.path.exists(c):
            return c
    raise FileNotFoundError("No se encontró el Excel de lista de usuarios en datos/.")


def buscar_archivo_relacion() -> str:
    """Encuentra el archivo de relación de usuarios en datos/."""
    candidatos = [
        os.path.join(BASE_DIR, "datos", "RELACION_DE_USUARIOS_DEL_CAAPD.xlsx"),
        os.path.join(BASE_DIR, "datos", "RELACION DE USUARIOS DEL CAAPD.xlsx"),
    ]
    for c in candidatos:
        if os.path.exists(c):
            return c
    raise FileNotFoundError("No se encontró el Excel de relación de usuarios en datos/.")


def normalizar_nombre(nombre: str | None) -> str:
    """Normaliza un nombre a mayúsculas, espacios simples y comas limpias."""
    if not nombre:
        return ""
    t = str(nombre).upper()
    t = re.sub(r"\s*,\s*", ", ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def clave_match_medidor(medidor_raw: Any) -> str:
    """Clave para emparejar medidores entre ambos Excel eliminando ceros a la izquierda."""
    s = limpiar_texto(medidor_raw)
    if s.isdigit():
        return s.lstrip("0") or "0"
    return s


def procesar_migracion(
    ruta_lista: str, ruta_relacion: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Procesa los dos Excel y genera los datos de padrón, semilla y reportes."""
    # -----------------------------------------------------------------------
    # 1. Leer RELACION_DE_USUARIOS_DEL_CAAPD.xlsx
    # -----------------------------------------------------------------------
    wb_rel = openpyxl.load_workbook(ruta_relacion, data_only=True)
    rel_por_clave = defaultdict(list)
    conexiones_sin_medidor = []
    semilla_lecturas = {}
    todas_conexiones_numericas = []

    for sheetname in wb_rel.sheetnames:
        ws = wb_rel[sheetname]
        filas = list(ws.iter_rows(values_only=True))
        h_idx = None
        for idx, r in enumerate(filas):
            textos = [str(c).strip().lower() for c in r if c is not None]
            if any("conexi" in t for t in textos) and any("medidor" in t for t in textos):
                h_idx = idx
                break
        if h_idx is None:
            continue

        h_row = [str(c).strip().lower() if c is not None else "" for c in filas[h_idx]]
        col_con = col_med = col_ben = col_dir = col_lant = col_lact = col_fec = None
        for i, col_name in enumerate(h_row):
            if "conexi" in col_name:
                col_con = i
            elif "medidor" in col_name:
                col_med = i
            elif "beneficiario" in col_name:
                col_ben = i
            elif "direcci" in col_name:
                col_dir = i
            elif "anterior" in col_name:
                col_lant = i
            elif "actual" in col_name:
                col_lact = i
            elif "fecha" in col_name:
                col_fec = i

        for r in filas[h_idx + 1 :]:
            if not any(r):
                continue
            c_raw = r[col_con] if col_con is not None else None
            m_raw = r[col_med] if col_med is not None else None
            ben_raw = r[col_ben] if col_ben is not None else ""
            dir_raw = r[col_dir] if col_dir is not None else ""
            lant_raw = r[col_lant] if col_lant is not None else None
            lact_raw = r[col_lact] if col_lact is not None else None
            fec_raw = r[col_fec] if col_fec is not None else None

            con_norm = normalizar_conexion(c_raw) if c_raw else ""
            if con_norm and con_norm.isdigit():
                todas_conexiones_numericas.append(int(con_norm))

            med_str = limpiar_texto(m_raw)
            if not med_str and con_norm:
                conexiones_sin_medidor.append(
                    {
                        "nro_conexion": con_norm,
                        "beneficiario": ben_raw or "",
                        "sector": sheetname,
                        "direccion": dir_raw or "",
                        "lectura_anterior": lant_raw,
                        "lectura_actual": lact_raw,
                    }
                )
                continue

            if med_str:
                k = clave_match_medidor(med_str)
                med_canonica = normalizar_medidor(med_str)

                # Formatear fecha si es datetime
                fecha_str = None
                if fec_raw is not None:
                    if hasattr(fec_raw, "strftime"):
                        fecha_str = fec_raw.strftime("%Y-%m-%d")
                    else:
                        fecha_str = str(fec_raw).strip()

                info = {
                    "conexion": con_norm,
                    "sector": sheetname,
                    "beneficiario": ben_raw or "",
                    "direccion": dir_raw or "",
                    "lectura_anterior": int(lant_raw) if isinstance(lant_raw, (int, float)) else lant_raw,
                    "lectura_actual": int(lact_raw) if isinstance(lact_raw, (int, float)) else lact_raw,
                    "fecha": fecha_str,
                    "med_raw": med_str,
                    "med_norm": med_canonica,
                }
                rel_por_clave[k].append(info)

                semilla_lecturas[med_canonica] = {
                    "lectura_anterior": info["lectura_anterior"],
                    "lectura_actual": info["lectura_actual"],
                    "fecha": info["fecha"],
                }

    # -----------------------------------------------------------------------
    # 2. Leer LISTA DE USUARIOS
    # -----------------------------------------------------------------------
    wb_usr = openpyxl.load_workbook(ruta_lista, data_only=True)
    ws_usr = wb_usr.active
    filas_raw = list(ws_usr.iter_rows(values_only=True))

    header_idx = None
    for idx, r in enumerate(filas_raw):
        if any(str(c).strip().upper() == "ESTADO" for c in r if c is not None):
            header_idx = idx
            break
    if header_idx is None:
        raise ValueError("No se encontró el encabezado 'ESTADO' en la lista de usuarios.")

    header = [str(c).strip().upper() if c is not None else "" for c in filas_raw[header_idx]]
    col_map = {h: i for i, h in enumerate(header)}

    total_filas_lista = 0
    conteo_estados = {}
    filas_activas = []
    dni_7_count = 0
    dni_9_count = 0
    med_menos_6_count = 0

    for r in filas_raw[header_idx + 1 :]:
        if not any(r):
            continue
        total_filas_lista += 1
        estado = str(r[col_map.get("ESTADO", 2)] or "").strip().upper()
        conteo_estados[estado] = conteo_estados.get(estado, 0) + 1

        if estado == "ACTIVO":
            dni_raw = limpiar_texto(r[col_map.get("DNI", 4)])
            med_raw = limpiar_texto(r[col_map.get("MEDIDIDOR", 3)])
            nombre_raw = limpiar_texto(r[col_map.get("BENIFICIARIO", 5)])
            sector_raw = limpiar_texto(r[col_map.get("SECTOR", 6)])
            dir_raw = limpiar_texto(r[col_map.get("DIRECCION", 7)])

            if dni_raw.isdigit():
                if len(dni_raw) == 7:
                    dni_7_count += 1
                elif len(dni_raw) == 9:
                    dni_9_count += 1

            if med_raw.isdigit() and len(med_raw) < 6:
                med_menos_6_count += 1

            filas_activas.append(
                {
                    "dni_raw": dni_raw,
                    "med_raw": med_raw,
                    "med_norm": normalizar_medidor(med_raw),
                    "med_key": clave_match_medidor(med_raw),
                    "nombre_raw": nombre_raw,
                    "nombre_norm": normalizar_nombre(nombre_raw),
                    "sector": sector_raw,
                    "direccion": dir_raw,
                }
            )

    # -----------------------------------------------------------------------
    # 3. Agrupación por persona = (DNI_norm, nombre_norm)
    # -----------------------------------------------------------------------
    personas_dict = defaultdict(list)
    medidor_a_personas = defaultdict(set)

    for f in filas_activas:
        dni_clave = f["dni_raw"]
        if dni_clave.isdigit() and len(dni_clave) == 7:
            dni_clave = dni_clave.zfill(8)
        clave = (dni_clave, f["nombre_norm"])
        personas_dict[clave].append(f)
        medidor_a_personas[f["med_norm"]].add(clave)

    # Medidores repetidos entre personas distintas
    medidores_repetidos_entre_personas = []
    for med, pers in medidor_a_personas.items():
        if len(pers) > 1:
            medidores_repetidos_entre_personas.append(
                {
                    "nro_medidor": med,
                    "personas": [f"{p[1]} (DNI: {p[0]})" for p in pers],
                }
            )

    # -----------------------------------------------------------------------
    # 4. Asignación de ID (DNI), sufijos -1/-2 y SD-xxx
    # -----------------------------------------------------------------------
    dni_a_nombres = defaultdict(list)
    for (d, n) in personas_dict.keys():
        if d:
            dni_a_nombres[d].append(n)

    dnis_compartidos = {d: noms for d, noms in dni_a_nombres.items() if len(noms) > 1}

    # Asignar IDs
    personas_con_id = {}
    contador_sin_dni = 1

    # Ordenar claves para reproducibilidad
    claves_ordenadas = sorted(personas_dict.keys(), key=lambda p: (p[0] or "ZZZ", p[1]))

    # Para sufijos de DNI compartido
    sufijo_por_dni = defaultdict(int)

    for (d, n) in claves_ordenadas:
        if not d:
            id_usr = f"SD-{contador_sin_dni:03d}"
            contador_sin_dni += 1
            motivo_guion = "SIN_DNI"
        elif d in dnis_compartidos:
            sufijo_por_dni[d] += 1
            id_usr = f"{normalizar_dni(d)}-{sufijo_por_dni[d]}"
            motivo_guion = "DNI_COMPARTIDO"
        else:
            id_usr = normalizar_dni(d)
            motivo_guion = None

        personas_con_id[(d, n)] = {
            "id_usuario": id_usr,
            "motivo_guion": motivo_guion,
            "filas": personas_dict[(d, n)],
        }

    # -----------------------------------------------------------------------
    # 5. Conexiones, medidores y sectores por persona
    # -----------------------------------------------------------------------
    max_conexion_existente = max(todas_conexiones_numericas) if todas_conexiones_numericas else 796
    prox_conexion_libre = max_conexion_existente + 1

    usuarios_finales = {}
    reporte_varios_codigos = []
    reporte_sin_conexion = []
    reporte_dni_pendientes = []
    reporte_dni_9 = []

    for (d, n), pinfo in personas_con_id.items():
        id_usr = pinfo["id_usuario"]
        filas = pinfo["filas"]

        # Medidores únicos de esta persona
        medidores_persona = []
        vistos_med = set()
        for f in filas:
            m = f["med_norm"]
            if m and m not in vistos_med:
                vistos_med.add(m)
                medidores_persona.append(m)

        # Buscar códigos de conexión en RELACION
        codigos_conexion = set()
        sectores_rel = set()
        direcciones_rel = set()

        for f in filas:
            k = f["med_key"]
            matches = rel_por_clave.get(k, [])
            for match in matches:
                if match["conexion"]:
                    codigos_conexion.add(match["conexion"])
                if match["sector"]:
                    sectores_rel.add(match["sector"])
                if match["direccion"]:
                    direcciones_rel.add(match["direccion"])

        # Elegir un solo nro_conexion: el menor de sus códigos
        if codigos_conexion:
            # Ordenar numéricamente si son dígitos
            def clave_con(c):
                return int(c) if c.isdigit() else 999999
            con_elegida = sorted(codigos_conexion, key=clave_con)[0]
        else:
            con_elegida = f"{prox_conexion_libre:06d}"
            prox_conexion_libre += 1
            reporte_sin_conexion.append(
                {
                    "id_usuario": id_usr,
                    "nombre": n,
                    "sector": filas[0]["sector"],
                    "medidores": ", ".join(medidores_persona),
                    "conexion_asignada": con_elegida,
                }
            )

        if len(codigos_conexion) > 1:
            reporte_varios_codigos.append(
                {
                    "id_usuario": id_usr,
                    "nombre": n,
                    "sector": filas[0]["sector"],
                    "conexion_asignada": con_elegida,
                    "todos_los_codigos": ", ".join(sorted(codigos_conexion)),
                    "medidores": ", ".join(medidores_persona),
                }
            )

        # Sector y dirección prioritarios
        sector_final = filas[0]["sector"] or (list(sectores_rel)[0] if sectores_rel else "BARRIO DE CHAUPI")
        dir_final = filas[0]["direccion"] or (list(direcciones_rel)[0] if direcciones_rel else "S/N")

        # Documento final del usuario
        usuarios_finales[id_usr] = {
            "nro_conexion": con_norm if con_elegida else con_elegida,
            "nro_conexion": con_elegida,
            "nombre": n,
            "sector": sector_final,
            "direccion": dir_final,
            "codigo_categoria": "A",
            "activo": True,
            "medidores": medidores_persona,
        }

        # Reportes de DNI
        if pinfo["motivo_guion"]:
            reporte_dni_pendientes.append(
                {
                    "id_usuario": id_usr,
                    "dni_original": d or "(SIN DNI)",
                    "motivo": pinfo["motivo_guion"],
                    "nombre": n,
                    "sector": sector_final,
                    "nro_conexion": con_elegida,
                    "medidores": ", ".join(medidores_persona),
                }
            )

        if d and d.isdigit() and len(d) == 9:
            reporte_dni_9.append(
                {
                    "id_usuario": id_usr,
                    "dni_original": d,
                    "nombre": n,
                    "sector": sector_final,
                    "nro_conexion": con_elegida,
                    "medidores": ", ".join(medidores_persona),
                }
            )

    # -----------------------------------------------------------------------
    # 6. Agregar conexión sin medidor (000771) si existe
    # -----------------------------------------------------------------------
    for csm in conexiones_sin_medidor:
        if csm["nro_conexion"] == "000771":
            id_771 = f"SD-{contador_sin_dni:03d}"
            contador_sin_dni += 1
            nom_771 = csm["beneficiario"].strip().upper() or "CONEXION SIN MEDIDOR 000771"
            usuarios_finales[id_771] = {
                "nro_conexion": "000771",
                "nombre": nom_771,
                "sector": csm["sector"] or "BARRIO DE LUCMANI",
                "direccion": csm["direccion"] or "CALLE LUCMANI S/N",
                "codigo_categoria": "A",
                "activo": True,
                "medidores": [],
            }
            reporte_dni_pendientes.append(
                {
                    "id_usuario": id_771,
                    "dni_original": "(SIN DNI - CONEXION 000771)",
                    "motivo": "SIN_DNI",
                    "nombre": nom_771,
                    "sector": csm["sector"],
                    "nro_conexion": "000771",
                    "medidores": "(NINGUNO)",
                }
            )

    # Estadísticas para el resumen
    estadisticas = {
        "filas_lista": total_filas_lista,
        "conteo_estados": conteo_estados,
        "filas_activas": len(filas_activas),
        "total_personas": len(personas_con_id),
        "personas_1_medidor": sum(1 for u in usuarios_finales.values() if len(u["medidores"]) == 1),
        "personas_2_mas_medidores": sum(1 for u in usuarios_finales.values() if len(u["medidores"]) > 1),
        "personas_varios_codigos": len(reporte_varios_codigos),
        "dnis_compartidos_conteo": len(dnis_compartidos),
        "personas_afectadas_dni_compartido": sum(len(n) for n in dnis_compartidos.values()),
        "personas_sin_dni": len([p for p in personas_dict.keys() if not p[0]]),
        "dni_7_digitos": dni_7_count,
        "dni_9_digitos": dni_9_count,
        "medidores_menos_6_digitos": med_menos_6_count,
        "medidores_repetidos_entre_personas": len(medidores_repetidos_entre_personas),
        "activos_sin_codigo": len(reporte_sin_conexion),
        "conexiones_sin_medidor": len(conexiones_sin_medidor),
    }

    reportes = {
        "personas_varios_codigos": reporte_varios_codigos,
        "dni_con_guion_pendientes": reporte_dni_pendientes,
        "dni_9_digitos": reporte_dni_9,
        "medidores_repetidos_entre_personas": medidores_repetidos_entre_personas,
        "activos_sin_codigo_conexion": reporte_sin_conexion,
        "conexion_sin_medidor": conexiones_sin_medidor,
    }

    return usuarios_finales, semilla_lecturas, {"estadisticas": estadisticas, "reportes": reportes}


def guardar_archivos_salida(
    semilla_lecturas: dict[str, Any], reportes: dict[str, list[dict[str, Any]]]
) -> list[str]:
    """Genera semilla_mes_previo.json y todos los reportes CSV en salida/."""
    os.makedirs(os.path.join(BASE_DIR, "salida"), exist_ok=True)
    generados = []

    # 1. Semilla mes previo JSON
    ruta_semilla = os.path.join(BASE_DIR, "salida", "semilla_mes_previo.json")
    with open(ruta_semilla, "w", encoding="utf-8") as f:
        json.dump(semilla_lecturas, f, indent=2, ensure_ascii=False)
    generados.append(ruta_semilla)

    # 2. Archivos CSV
    for nombre, filas in reportes.items():
        if not filas:
            # Crear archivo vacío con encabezados indicando sin casos
            ruta_csv = os.path.join(BASE_DIR, "salida", f"{nombre}.csv")
            with open(ruta_csv, "w", newline="", encoding="utf-8-sig") as f:
                f.write("# Sin casos registrados\n")
            generados.append(ruta_csv)
            continue

        ruta_csv = os.path.join(BASE_DIR, "salida", f"{nombre}.csv")
        columnas = list(filas[0].keys())
        with open(ruta_csv, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=columnas)
            writer.writeheader()
            for r in filas:
                writer.writerow(r)
        generados.append(ruta_csv)

    return generados


def imprimir_reporte(stats: dict[str, Any]):
    """Imprime el cuadro comparativo de cifras esperadas vs obtenidas."""
    c = stats["conteo_estados"]
    print("\n" + "=" * 80)
    print("      REPORTE DE SIMULACION DE IMPORTACION - CAAPD ISPACAS")
    print("=" * 80)
    print(f"{'Indicador':<45} | {'Obtenido':<10} | {'Esperado':<10}")
    print("-" * 80)
    print(f"{'Filas en lista de usuarios':<45} | {stats['filas_lista']:<10} | {'808':<10}")
    print(f"  - ACTIVOS: {c.get('ACTIVO', 0)}, INACTIVOS: {c.get('INACTIVO', 0)}, NACTIVO: {c.get('NACTIVO', 0)}")
    print(f"{'Usuarios ACTIVOS (medidores)':<45} | {stats['filas_activas']:<10} | {'766':<10}")
    print(f"{'Personas distintas entre activos':<45} | {stats['total_personas']:<10} | {'~714':<10}")
    print(f"{'  Personas con un solo medidor':<45} | {stats['personas_1_medidor']:<10} | {'664':<10}")
    print(f"{'  Personas con 2 o 3 medidores':<45} | {stats['personas_2_mas_medidores']:<10} | {'50':<10}")
    print(f"{'Personas con varios códigos de conexión':<45} | {stats['personas_varios_codigos']:<10} | {'49':<10}")
    print(f"{'DNI compartidos por personas distintas':<45} | {stats['dnis_compartidos_conteo']:<10} | {'22':<10}")
    print(f"{'Personas afectadas por DNI compartido':<45} | {stats['personas_afectadas_dni_compartido']:<10} | {'48':<10}")
    print(f"{'Personas sin DNI (reciben SD-xxx)':<45} | {stats['personas_sin_dni']:<10} | {'25':<10}")
    print(f"{'DNI de 7 dígitos (completados con cero)':<45} | {stats['dni_7_digitos']:<10} | {'31':<10}")
    print(f"{'DNI de 9 dígitos':<45} | {stats['dni_9_digitos']:<10} | {'3':<10}")
    print(f"{'Medidores < 6 dígitos (completados a 6)':<45} | {stats['medidores_menos_6_digitos']:<10} | {'3':<10}")
    print(f"{'Medidores repetidos entre personas distintas':<45} | {stats['medidores_repetidos_entre_personas']:<10} | {'2':<10}")
    print(f"{'Activos sin código de conexión en RELACION':<45} | {stats['activos_sin_codigo']:<10} | {'2':<10}")
    print(f"{'Conexiones sin medidor en RELACION':<45} | {stats['conexiones_sin_medidor']:<10} | {'1 (000771)':<10}")
    print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Importación inicial del padrón de usuarios a Firestore.")
    parser.add_argument("--simular", action="store_true", help="Modo simulación: genera reportes en salida/ sin escribir en Firestore.")
    parser.add_argument("--lista", type=str, default=None, help="Ruta al archivo Excel de lista de usuarios.")
    parser.add_argument("--relacion", type=str, default=None, help="Ruta al archivo Excel de relación de usuarios.")
    args = parser.parse_args()

    ruta_lista = args.lista or buscar_archivo_lista()
    ruta_relacion = args.relacion or buscar_archivo_relacion()

    print(f"Cargando archivos:\n  Lista: {ruta_lista}\n  Relación: {ruta_relacion}...")
    usuarios, semilla, datos_aux = procesar_migracion(ruta_lista, ruta_relacion)

    stats = datos_aux["estadisticas"]
    reportes = datos_aux["reportes"]

    # Imprimir reporte
    imprimir_reporte(stats)

    # Guardar semilla y CSVs en salida/
    generados = guardar_archivos_salida(semilla, reportes)
    print("Archivos generados en salida/:")
    for g in generados:
        print(f"  [OK] {os.path.relpath(g, BASE_DIR)}")

    if args.simular:
        print("\nModo --simular finalizado con éxito. No se modificó Firestore.")
        return

    # Modo REAL: pedir confirmación escrita
    print("\n" + "!" * 80)
    print("  ATENCIÓN: Se escribirán los usuarios en Firestore.")
    print(f"  Total documentos a escribir en coleccion 'usuarios': {len(usuarios)}")
    print("!" * 80)

    try:
        confirmacion = input("\nEscribe 'SI' para confirmar la importación a Firestore: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nOperación cancelada por el usuario.")
        return

    if confirmacion != "SI":
        print("Importación cancelada (no se escribió 'SI').")
        return

    # Importación real
    import firebase_client as fb
    from respaldo import on_datos_cambiados

    print(f"\nEscribiendo {len(usuarios)} usuarios en Firestore en lotes de máximo 500...")
    fb.guardar_usuarios_lote(usuarios)
    on_datos_cambiados("importacion_excel", {"total_usuarios": len(usuarios)})
    print("[OK] Importacion completada con exito en Firestore.")


if __name__ == "__main__":
    main()
