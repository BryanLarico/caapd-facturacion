"""
servicios/contador_ops.py — Contador DIARIO y persistente de operaciones Firestore.

Cuenta las lecturas y escrituras que realiza ESTA PC contra Firebase durante el
día de cuota de Google (que se reinicia a las 00:00 hora del Pacífico, EE. UU.).

- Se guarda en datos/ops_diarias.json, así sobrevive a cerrar/abrir el programa.
- Al cambiar el día (Pacífico) vuelve a 0 automáticamente.
- Cada vez que se registra una operación avisa a los "oyentes" (la ventana
  principal) para que el pie de página se actualice al instante.

Es independiente de Qt y seguro entre hilos (las operaciones se ejecutan en
hilos de trabajo).
"""
from __future__ import annotations

import datetime
import json
import os
import threading
from typing import Callable, Dict, List

import rutas

try:  # zona horaria de la cuota de Firebase
    import zoneinfo
    _TZ_CUOTA = zoneinfo.ZoneInfo("America/Los_Angeles")
except Exception:  # pragma: no cover - sin base de datos de zonas
    _TZ_CUOTA = datetime.timezone(datetime.timedelta(hours=-7))

_LOCK = threading.RLock()
_OYENTES: List[Callable[[Dict[str, int]], None]] = []
_ESTADO: Dict[str, object] = {"fecha": None, "lecturas": 0, "escrituras": 0}
_CARGADO = False


def _ruta_archivo():
    return rutas.ruta_datos("ops_diarias.json")


def fecha_cuota_hoy() -> str:
    """Fecha (AAAA-MM-DD) del día de cuota actual, en hora del Pacífico."""
    return datetime.datetime.now(_TZ_CUOTA).strftime("%Y-%m-%d")


def _cargar_si_hace_falta() -> None:
    global _CARGADO
    if _CARGADO:
        return
    _CARGADO = True
    try:
        ruta = _ruta_archivo()
        if ruta.exists():
            datos = json.loads(ruta.read_text(encoding="utf-8"))
            if isinstance(datos, dict):
                _ESTADO["fecha"] = str(datos.get("fecha") or "")
                _ESTADO["lecturas"] = int(datos.get("lecturas") or 0)
                _ESTADO["escrituras"] = int(datos.get("escrituras") or 0)
    except Exception:
        pass


def _reiniciar_si_cambio_el_dia() -> None:
    hoy = fecha_cuota_hoy()
    if _ESTADO["fecha"] != hoy:
        _ESTADO["fecha"] = hoy
        _ESTADO["lecturas"] = 0
        _ESTADO["escrituras"] = 0


def _guardar() -> None:
    try:
        ruta = _ruta_archivo()
        ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp = ruta.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(_ESTADO, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, ruta)
    except Exception:
        pass


def obtener() -> Dict[str, int]:
    """Devuelve {'lecturas': n, 'escrituras': n} acumulados HOY por esta PC."""
    with _LOCK:
        _cargar_si_hace_falta()
        _reiniciar_si_cambio_el_dia()
        return {"lecturas": int(_ESTADO["lecturas"]),
                "escrituras": int(_ESTADO["escrituras"])}


def registrar(tipo: str, n: int = 1) -> Dict[str, int]:
    """
    Suma n operaciones de 'lecturas' o 'escrituras' al día de hoy, persiste y
    notifica a los oyentes. Devuelve los totales actualizados.
    """
    if tipo not in ("lecturas", "escrituras") or n <= 0:
        return obtener()
    with _LOCK:
        _cargar_si_hace_falta()
        _reiniciar_si_cambio_el_dia()
        _ESTADO[tipo] = int(_ESTADO[tipo]) + int(n)
        _guardar()
        totales = {"lecturas": int(_ESTADO["lecturas"]),
                   "escrituras": int(_ESTADO["escrituras"])}
        oyentes = list(_OYENTES)
    for cb in oyentes:
        try:
            cb(totales)
        except Exception:
            pass
    return totales


def suscribir(callback: Callable[[Dict[str, int]], None]) -> None:
    """Registra una función que se llamará (desde el hilo que opera) tras cada registro."""
    with _LOCK:
        if callback not in _OYENTES:
            _OYENTES.append(callback)


def desuscribir(callback: Callable[[Dict[str, int]], None]) -> None:
    with _LOCK:
        if callback in _OYENTES:
            _OYENTES.remove(callback)


def reiniciar_para_pruebas() -> None:
    """Solo para tests: vuelve al estado inicial en memoria."""
    global _CARGADO
    with _LOCK:
        _CARGADO = False
        _ESTADO["fecha"] = None
        _ESTADO["lecturas"] = 0
        _ESTADO["escrituras"] = 0
        _OYENTES.clear()
