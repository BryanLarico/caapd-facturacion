"""
servicios/cola_offline.py — Cola local de cambios fuera de línea (offline queue) para CAAPD Ispacas.

Gestiona las operaciones pendientes en cola_pendiente.json (cobros, anulaciones, lecturas)
cuando no hay conexión con Firebase, aplicándolas en memoria y sincronizándolas
automáticamente al restablecer la conexión.
"""
from __future__ import annotations
import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import rutas

logger = logging.getLogger("caapd.cola_offline")


def _ruta_cola() -> Path:
    return rutas.ruta_datos("cola_pendiente.json")


def cargar_cola() -> List[Dict[str, Any]]:
    """Carga la lista de cambios pendientes desde cola_pendiente.json."""
    p = _ruta_cola()
    if not p.exists():
        return []
    try:
        contenido = p.read_text(encoding="utf-8").strip()
        if not contenido:
            return []
        data = json.loads(contenido)
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error("Error al leer cola_pendiente.json: %s", e)
        return []


def guardar_cola(cola: List[Dict[str, Any]]) -> None:
    """Guarda la lista de cambios en cola_pendiente.json."""
    p = _ruta_cola()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cola, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.error("Error al escribir cola_pendiente.json: %s", e)


def encolar_cambio(tipo: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Agrega una operación a la cola local y la persiste en disco.

    Tipos soportados: 'pago', 'anular_pago', 'lectura'.
    """
    cola = cargar_cola()
    item = {
        "id_evento": f"evt_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
        "tipo": tipo,
        "payload": payload,
        "fecha_creacion": datetime.datetime.now().isoformat(),
        "reintentos": 0,
    }
    cola.append(item)
    guardar_cola(cola)
    logger.info("Cambio encolado offline: tipo=%s, id=%s", tipo, item["id_evento"])
    return item


def cantidad_pendientes() -> int:
    """Devuelve la cantidad de operaciones pendientes en la cola."""
    return len(cargar_cola())


def sincronizar_cola(servicio_remoto: Any) -> Dict[str, Any]:
    """Intenta enviar los cambios encolados hacia Firebase.

    Si un cambio se procesa con éxito, se remueve de la cola.
    Si falla por conectividad, se conserva para el próximo reintento.
    """
    cola = cargar_cola()
    if not cola:
        return {"enviados": 0, "fallidos": 0, "conflictos": 0, "pendientes": 0}

    enviados = 0
    fallidos = 0
    conflictos = 0
    cola_restante: List[Dict[str, Any]] = []

    for item in cola:
        tipo = item.get("tipo")
        pay = item.get("payload") or {}
        exito = False

        try:
            if tipo == "pago":
                servicio_remoto.registrar_pago(
                    periodo=pay["periodo"],
                    id_usuario=pay["id_usuario"],
                    monto_pagado=pay["monto_pagado"],
                    fecha_pago=pay.get("fecha_pago"),
                )
                exito = True

            elif tipo == "anular_pago":
                servicio_remoto.anular_pago(
                    periodo=pay["periodo"],
                    id_usuario=pay["id_usuario"],
                )
                exito = True

            elif tipo == "lectura":
                servicio_remoto.guardar_lectura_medidor(
                    periodo=pay["periodo"],
                    id_usuario=pay["id_usuario"],
                    nro_medidor=pay["nro_medidor"],
                    lectura_actual=pay["lectura_actual"],
                    novedad=pay.get("novedad", "NORMAL"),
                    nota=pay.get("nota", ""),
                    registrado_por=pay.get("registrado_por", "ADMIN"),
                )
                exito = True
            else:
                logger.warning("Tipo de evento desconocido en cola offline: %s", tipo)
                exito = True  # Descartar evento corrupto

        except Exception as e:
            msg = str(e).lower()
            if "conflict" in msg or "modificado" in msg:
                conflictos += 1
                logger.warning("Conflicto al sincronizar evento %s: %s", item.get("id_evento"), e)
            else:
                fallidos += 1
                logger.warning("Fallo al sincronizar evento %s: %s", item.get("id_evento"), e)
            ultimo_err = str(e)
            exito = False

        if exito:
            enviados += 1
        else:
            item["reintentos"] = int(item.get("reintentos", 0)) + 1
            item["ultimo_error"] = ultimo_err
            cola_restante.append(item)

    guardar_cola(cola_restante)
    return {
        "enviados": enviados,
        "fallidos": fallidos,
        "conflictos": conflictos,
        "pendientes": len(cola_restante),
    }
