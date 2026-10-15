"""
scripts/gestionar_lectores.py — Administración de usuarios y lectores en Firebase Authentication.

Permite:
- Listar lectores actuales.
- Crear nuevas cuentas de lectores (correo, contraseña y nombre).
- Cambiar contraseñas.
- Desactivar o eliminar cuentas.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import firebase_client as fb
from firebase_admin import auth


def inicializar():
    fb.db()  # Asegura inicialización de la app con la clave de servicio


def listar_lectores():
    inicializar()
    print("\n--- Lectores registrados en Firebase Auth ---")
    page = auth.list_users()
    if not page.users:
        print("No hay usuarios registrados.")
        return
    for u in page.users:
        estado = "Activo" if not u.disabled else "Deshabilitado"
        print(f"- Correo: {u.email:<30} | Nombre: {str(u.display_name or 'Sin nombre'):<25} | Estado: {estado} | UID: {u.uid}")
    print("---------------------------------------------\n")


def crear_lector(email: str, password: str, display_name: str | None = None):
    inicializar()
    try:
        user = auth.create_user(
            email=email.strip().lower(),
            password=password.strip(),
            display_name=display_name.strip() if display_name else None,
        )
        print(f"[OK] Lector creado exitosamente:")
        print(f"     Email: {user.email}")
        print(f"     Nombre: {user.display_name}")
        print(f"     UID: {user.uid}")
        return user
    except Exception as e:
        print(f"[ERROR] No se pudo crear el usuario: {e}")
        return None


def cambiar_password(email: str, nuevo_password: str):
    inicializar()
    try:
        user = auth.get_user_by_email(email.strip().lower())
        auth.update_user(user.uid, password=nuevo_password.strip())
        print(f"[OK] Contraseña actualizada correctamente para {email}")
    except Exception as e:
        print(f"[ERROR] No se pudo actualizar la contraseña: {e}")


def eliminar_lector(email: str):
    inicializar()
    try:
        user = auth.get_user_by_email(email.strip().lower())
        auth.delete_user(user.uid)
        print(f"[OK] Usuario {email} eliminado correctamente.")
    except Exception as e:
        print(f"[ERROR] No se pudo eliminar el usuario: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gestor de Lectores en Firebase Auth")
    subparsers = parser.add_subparsers(dest="accion", help="Acción a realizar")

    # Listar
    subparsers.add_parser("listar", help="Listar todos los lectores")

    # Crear
    p_crear = subparsers.add_parser("crear", help="Crear nuevo lector")
    p_crear.add_argument("--email", required=True, help="Correo electrónico")
    p_crear.add_argument("--password", required=True, help="Contraseña (mínimo 6 caracteres)")
    p_crear.add_argument("--nombre", required=False, help="Nombre del lector")

    # Cambiar contraseña
    p_pass = subparsers.add_parser("cambiar-clave", help="Cambiar contraseña de un lector")
    p_pass.add_argument("--email", required=True, help="Correo electrónico")
    p_pass.add_argument("--password", required=True, help="Nueva contraseña")

    # Eliminar
    p_del = subparsers.add_parser("eliminar", help="Eliminar un lector")
    p_del.add_argument("--email", required=True, help="Correo electrónico")

    args = parser.parse_args()

    if args.accion == "listar" or not args.accion:
        listar_lectores()
    elif args.accion == "crear":
        crear_lector(args.email, args.password, args.nombre)
    elif args.accion == "cambiar-clave":
        cambiar_password(args.email, args.password)
    elif args.accion == "eliminar":
        eliminar_lector(args.email)
