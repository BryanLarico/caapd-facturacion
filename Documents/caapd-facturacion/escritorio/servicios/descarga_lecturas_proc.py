"""
servicios/descarga_lecturas_proc.py — Descarga aislada de lecturas desde Firestore.

Este módulo se ejecuta como PROCESO SEPARADO:
    python -u -m servicios.descarga_lecturas_proc --periodo 2026-10 --salida ruta.json

MOTIVO: la pila gRPC que usa Firestore puede provocar un cierre nativo del proceso
(«access violation», sin traceback de Python). Mientras esa pila viva en el mismo
proceso que la ventana, un fallo suyo cierra el programa entero. Ejecutándola aquí,
cualquier fallo grave termina SOLO este proceso auxiliar: la ventana sigue abierta y
el programa muestra un error normal.

Protocolo en stdout (una línea JSON por evento, para que la barra de progreso avance):
    {"t": "hb"}                    latido periódico: el proceso sigue vivo
    {"t": "fase", "msg": "..."}    cambio de fase legible para el usuario
    {"t": "prog", "n": 12}         documentos recibidos hasta el momento
    {"t": "fin", "n": 29}          terminó de leer la colección
    {"t": "error", "msg": "..."}   error controlado

El resultado completo (documentos descargados) se escribe en el archivo --salida.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from pathlib import Path

# Permitir importar firebase_client y el resto de módulos de 'escritorio/'.
DIR_BASE = Path(__file__).resolve().parent.parent
if str(DIR_BASE) not in sys.path:
    sys.path.insert(0, str(DIR_BASE))

INTERVALO_LATIDO_S = 4.0


def _emitir(evento: dict) -> None:
    """Escribe un evento JSON en stdout. Nunca lanza excepción."""
    try:
        sys.stdout.write(json.dumps(evento, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    except Exception:
        pass


def descargar(periodo: str, timeout_stream: float) -> dict:
    """Lee la colección mes_aaaa-mm y devuelve {'docs': {...}, 'recibidos': n}."""
    _emitir({"t": "fase", "msg": "Autenticando con Firebase (API REST)..."})
    from servicios import firestore_rest

    _emitir({"t": "fase", "msg": "Leyendo las lecturas del mes en la nube..."})
    docs = firestore_rest.descargar_documentos_mes(
        periodo,
        campos=("medidores", "nombre"),
        timeout=(firestore_rest.TIMEOUT_CONEXION_S, timeout_stream),
        callback_progreso=lambda n, _texto: _emitir({"t": "prog", "n": n}),
    )
    n = len(docs)
    _emitir({"t": "fin", "n": n})
    return {"docs": docs, "recibidos": n}


def main() -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--periodo", required=True)
    parser.add_argument("--salida", required=True)
    parser.add_argument("--timeout", type=float, default=45.0)
    args = parser.parse_args()

    detener = threading.Event()

    def latir() -> None:
        while not detener.wait(INTERVALO_LATIDO_S):
            _emitir({"t": "hb"})

    threading.Thread(target=latir, daemon=True).start()

    resultado = {"exito": False, "docs": {}, "recibidos": 0, "error": ""}
    try:
        resultado.update(descargar(args.periodo, args.timeout))
        resultado["exito"] = True
    except BaseException as e:  # incluye errores de red, permisos y cancelaciones
        resultado["error"] = f"{e.__class__.__name__}: {e}"
        _emitir({"t": "error", "msg": resultado["error"]})
    finally:
        detener.set()
        try:
            Path(args.salida).write_text(
                json.dumps(resultado, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            _emitir({"t": "error", "msg": f"No se pudo escribir el resultado: {e}"})

    return 0 if resultado.get("exito") else 1


if __name__ == "__main__":
    codigo = main()
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(codigo)
