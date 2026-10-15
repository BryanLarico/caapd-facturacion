"""
scripts/restaurar_excel.py — Herramienta CLI de restauración desde Excel de respaldo (Fase 6).

Uso:
  python scripts/restaurar_excel.py --archivo respaldos/RESPALDO_2026-10.xlsx --simular
  python scripts/restaurar_excel.py --archivo respaldos/RESPALDO_2026-10.xlsx --ejecutar [--sobrescribir] [--solo config|usuarios|mes] [--credenciales ruta_clave.json]
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import sys
from typing import Any, Dict, Optional

# Agregar raíz al sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import respaldo_excel


def inicializar_firebase_personalizado(ruta_credenciales: Optional[str] = None) -> Any:
    """Inicializa Firebase con credenciales personalizadas o por defecto."""
    import firebase_admin
    from firebase_admin import credentials, firestore

    if ruta_credenciales:
        cred_path = Path(ruta_credenciales).resolve()
        if not cred_path.exists():
            raise FileNotFoundError(f"No se encontró el archivo de credenciales: {cred_path}")
        cred = credentials.Certificate(str(cred_path))
        # Inicializar app con nombre único si ya existe default
        app_name = f"restauracion_{cred_path.stem}"
        try:
            app = firebase_admin.get_app(app_name)
        except ValueError:
            app = firebase_admin.initialize_app(cred, name=app_name)
        return firestore.client(app=app)
    else:
        import firebase_client as fb
        return fb._get_db()


def restaurar_datos(
    datos_respaldo: Dict[str, Any],
    db_firestore: Any = None,
    solo_seccion: Optional[str] = None,
    simular: bool = True,
    sobrescribir: bool = False,
) -> Dict[str, Any]:
    """Ejecuta o simula la restauración de datos en Firestore en el orden: config -> usuarios -> mes.

    Devuelve un diccionario con las estadísticas de la restauración.
    """
    config = datos_respaldo.get("config") or {}
    usuarios = datos_respaldo.get("usuarios") or {}
    mes_docs = datos_respaldo.get("mes_docs") or {}
    periodo = datos_respaldo.get("periodo") or "2026-10"

    secciones = {"config", "usuarios", "mes"}
    if solo_seccion:
        solo_seccion = solo_seccion.strip().lower()
        if solo_seccion not in secciones:
            raise ValueError(f"Opción --solo inválida: '{solo_seccion}'. Debe ser config, usuarios o mes.")

    resumen = {
        "simulacion": simular,
        "sobrescribir": sobrescribir,
        "config_escrito": False,
        "usuarios_nuevos": 0,
        "usuarios_existentes": 0,
        "usuarios_omitidos": 0,
        "mes_docs_nuevos": 0,
        "mes_docs_existentes": 0,
        "mes_docs_omitidos": 0,
        "suma_total_restaurada": 0.0,
    }

    # Si db_firestore es None y no es simulación, obtener cliente Firestore
    db = db_firestore
    if not simular and db is None:
        db = inicializar_firebase_personalizado()

    # 1. RESTAURAR CONFIG
    if not solo_seccion or solo_seccion == "config":
        if config:
            if not simular and db is not None:
                db.collection("config").document("general").set(config, merge=not sobrescribir)
            resumen["config_escrito"] = True

    # 2. RESTAURAR USUARIOS
    if not solo_seccion or solo_seccion == "usuarios":
        usuarios_col = db.collection("usuarios") if db is not None else None
        for uid, u in usuarios.items():
            existe = False
            if db is not None:
                doc_snap = usuarios_col.document(uid).get()
                existe = doc_snap.exists

            if existe:
                resumen["usuarios_existentes"] += 1
                if sobrescribir:
                    if not simular and db is not None:
                        usuarios_col.document(uid).set(u)
                    resumen["usuarios_nuevos"] += 1
                else:
                    resumen["usuarios_omitidos"] += 1
            else:
                if not simular and db is not None:
                    usuarios_col.document(uid).set(u)
                resumen["usuarios_nuevos"] += 1

    # 3. RESTAURAR MES
    if not solo_seccion or solo_seccion == "mes":
        col_mes_nombre = f"mes_{periodo}"
        mes_col = db.collection(col_mes_nombre) if db is not None else None

        for uid, doc in mes_docs.items():
            tot = float(doc.get("total_a_pagar") or 0.0)
            resumen["suma_total_restaurada"] += tot

            existe = False
            if db is not None:
                doc_snap = mes_col.document(uid).get()
                existe = doc_snap.exists

            if existe:
                resumen["mes_docs_existentes"] += 1
                if sobrescribir:
                    if not simular and db is not None:
                        mes_col.document(uid).set(doc)
                    resumen["mes_docs_nuevos"] += 1
                else:
                    resumen["mes_docs_omitidos"] += 1
            else:
                if not simular and db is not None:
                    mes_col.document(uid).set(doc)
                resumen["mes_docs_nuevos"] += 1

    resumen["suma_total_restaurada"] = round(resumen["suma_total_restaurada"], 2)
    return resumen


def main():
    parser = argparse.ArgumentParser(description="Restauración de base de datos CAAPD desde archivo Excel de respaldo.")
    parser.add_argument("--archivo", required=True, help="Ruta al archivo Excel de respaldo (ej. respaldos/RESPALDO_2026-10.xlsx).")
    parser.add_argument("--solo", choices=["config", "usuarios", "mes"], default=None, help="Restaura únicamente la sección indicada.")
    parser.add_argument("--simular", action="store_true", help="Modo simulación (no escribe cambios en Firestore).")
    parser.add_argument("--ejecutar", action="store_true", help="Ejecuta la restauración real en Firestore.")
    parser.add_argument("--sobrescribir", action="store_true", help="Sobrescribe documentos que ya existan en la base de datos.")
    parser.add_argument("--credenciales", default=None, help="Ruta al JSON de credenciales de Firebase para proyectos nuevos.")

    args = parser.parse_args()

    ruta_p = Path(args.archivo).resolve()
    if not ruta_p.exists():
        print(f"[ERROR] No se encontró el archivo: {ruta_p}")
        sys.exit(1)

    print(f"\nLeyendo archivo de respaldo: {ruta_p.name}...")
    datos = respaldo_excel.leer_respaldo_excel(ruta_p)
    meta = datos["metadatos"]
    val = datos["validacion"]

    print("=" * 70)
    print("                 METADATOS DEL RESPALDO")
    print("=" * 70)
    print(f"Versión Formato     : {meta.get('Versión del Formato', 'Desconocida')}")
    print(f"Fecha Generación    : {meta.get('Fecha de Generación')}")
    print(f"Periodo             : {datos['periodo']}")
    print(f"Total Usuarios      : {len(datos['usuarios'])}")
    print(f"Total Documentos Mes: {len(datos['mes_docs'])}")
    print(f"Suma Total a Pagar  : S/. {val['suma_obtenida']:,.2f}")
    print(f"Validación Checksum : {'[CORRECTO]' if val['coincide'] else '[DISCREPANCIA DETECTADA]'}")
    print("=" * 70)

    # Por defecto, simular si no se especificó --ejecutar
    es_simulacion = True if args.simular or not args.ejecutar else False

    if es_simulacion:
        print("\n>>> MODO SIMULACIÓN ACTIVO (No se realizarán escrituras en Firestore) <<<")
    else:
        print("\n>>> MODO REAL: Se aplicarán cambios en la base de datos <<<")
        if not args.sobrescribir:
            print("  (Protección activa: Los documentos existentes NO se sobrescribirán)")
        else:
            print("  (ALERTA: Se sobrescribirán documentos existentes con --sobrescribir)")

    try:
        db = inicializar_firebase_personalizado(args.credenciales) if not es_simulacion else None
    except Exception as e:
        print(f"[ERROR] No se pudo inicializar conexión a Firestore: {e}")
        sys.exit(1)

    resultado = restaurar_datos(
        datos,
        db_firestore=db,
        solo_seccion=args.solo,
        simular=es_simulacion,
        sobrescribir=args.sobrescribir,
    )

    print("\n" + "=" * 70)
    print("                 RESULTADO DE LA OPERACIÓN")
    print("=" * 70)
    print(f"Configuración       : {'Restaurada' if resultado['config_escrito'] else 'No modificada'}")
    print(f"Usuarios Nuevos     : {resultado['usuarios_nuevos']}")
    print(f"Usuarios Omitidos   : {resultado['usuarios_omitidos']}")
    print(f"Documentos Mes      : {resultado['mes_docs_nuevos']}")
    print(f"Mes Omitidos        : {resultado['mes_docs_omitidos']}")
    print(f"Suma Restaurada     : S/. {resultado['suma_total_restaurada']:,.2f}")
    print("=" * 70)

    if es_simulacion:
        print("\n[OK] Simulación exitosa. Para aplicar los cambios reales ejecute con '--ejecutar'.\n")
    else:
        print("\n[OK] Restauración completada satisfactoriamente en Firestore.\n")


if __name__ == "__main__":
    main()
