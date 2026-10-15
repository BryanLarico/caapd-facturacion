"""
scripts/sembrar_config.py — Crea config/general en Firestore.

Lee la estructura exacta de docs/firestore_ejemplo_v2.json y
la sube como documento config/general. Categorías B y C usan
los mismos valores que A (configurables luego desde la pantalla).

Uso:
    python scripts/sembrar_config.py
    python scripts/sembrar_config.py --forzar   # sobreescribe si ya existe
"""

from __future__ import annotations
import argparse
import json
import os
import sys

# Agrega el directorio raíz al path para importar firebase_client
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import firebase_client as fb


# ---------------------------------------------------------------------------
# Estructura base de config/general
# ---------------------------------------------------------------------------

CONFIG_INICIAL = {
    "empresa": {
        "nombre": (
            "COMITÉ DE ADMINISTRACIÓN DE AGUA POTABLE Y DESAGÜE "
            "DE LA COMUNIDAD CAMPESINA DE ISPACAS"
        ),
        "resolucion": "192-2017",
        "telefono": "986054179",
        "whatsapp": None,
        "direccion": (
            "Calle 5 de Agosto s/n - Distrito de Yanaquihua "
            "- Provincia de Condesuyos - Región Arequipa"
        ),
    },
    "igv": {
        "activo": False,
        "porcentaje": 0.18,
    },
    "dias_vencimiento": 15,
    "ultimo_recibo": 0,   # El script de importación actualiza este valor
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
            "nombre": "Doméstico",
            "tarifa_desague": 0.0,
            "cargo_fijo": 1.5,
            "rangos": [
                {"m3_desde": 0, "m3_hasta": None, "precio_m3": 1.0}
            ],
        },
        "B": {
            "nombre": "Negocio pequeño",
            # Mismos valores que A hasta que el dueño los configure
            "tarifa_desague": 0.0,
            "cargo_fijo": 1.5,
            "rangos": [
                {"m3_desde": 0, "m3_hasta": None, "precio_m3": 1.0}
            ],
        },
        "C": {
            "nombre": "Hotel o Restaurante",
            # Mismos valores que A hasta que el dueño los configure
            "tarifa_desague": 0.0,
            "cargo_fijo": 1.5,
            "rangos": [
                {"m3_desde": 0, "m3_hasta": None, "precio_m3": 1.0}
            ],
        },
    },
    "mora": [
        {"meses_min": 1, "nombre": "AZUL",    "color": "#1E88E5", "corte": False},
        {"meses_min": 2, "nombre": "NARANJA", "color": "#FB8C00", "corte": False},
        {"meses_min": 3, "nombre": "ROJO",    "color": "#E53935", "corte": True},
    ],
    "mes_actual": {
        "periodo": None,
        "fecha_emision": None,
        "fecha_vencimiento": None,
        "estado": "CERRADO",
    },
}


def main():
    parser = argparse.ArgumentParser(
        description="Crea config/general en Firestore con los valores iniciales."
    )
    parser.add_argument(
        "--forzar",
        action="store_true",
        help="Sobreescribe config/general si ya existe.",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("sembrar_config.py — CAAPD Ispacas")
    print("=" * 60)

    # Verificar si ya existe
    try:
        doc = fb.db().collection("config").document("general").get()
        fb._contar("lecturas", 1)
        existe = doc.exists
    except Exception as e:
        print(f"\n❌ Error al conectar con Firebase: {e}")
        sys.exit(1)

    if existe and not args.forzar:
        print("\n✓ config/general ya existe. Usa --forzar para sobreescribir.")
        print("  Valores actuales:")
        datos = doc.to_dict()
        for k, v in datos.items():
            print(f"    {k}: {v}")
        print("\nNo se realizaron cambios.")
        return

    if existe and args.forzar:
        print("\n⚠  config/general ya existe. Sobreescribiendo por --forzar...")

    # Subir la configuración
    try:
        fb.guardar_config(CONFIG_INICIAL)
        print("\n✅ config/general creado/actualizado exitosamente.")
        print(f"\nOperaciones usadas: {fb.get_ops()}")
        print("\nRecuerda configurar antes de empezar:")
        print("  • Número de WhatsApp (para el QR del talón)")
        print("  • Último número de recibo (lo hace scripts/importar_excel.py)")
        print("  • Tarifas de categorías B y C (desde la pantalla Configuración)")
    except Exception as e:
        print(f"\n❌ Error al guardar en Firestore: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
