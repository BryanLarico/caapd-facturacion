"""
servicios/firestore_rest.py — Descarga de lecturas desde Firestore por la API REST (sin gRPC).

MOTIVO: la acción «Traer lecturas de los lectores» usaba `col.select([...]).stream()` del SDK
de Firestore, que viaja por gRPC. En Windows, la pila nativa de gRPC (cygrpc) puede quedarse
colgada dentro de la llamada de streaming y luego cerrar el proceso con un «access violation»
sin traceback. Este módulo reemplaza esa llamada por peticiones HTTP normales a la API REST
de Firestore (`documents.list`), autenticadas con la misma cuenta de servicio.
  * Cero gRPC en este flujo => no hay cuelgue ni cierre nativo.
  * `requests` respeta los timeouts de verdad => la ventana nunca se congela.
  * Tiempo máximo acotado (timeouts + reintentos limitados) y errores claros en español.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

import rutas

TIMEOUT_CONEXION_S = 15.0
TIMEOUT_LECTURA_S = 45.0
REINTENTOS_POR_PAGINA = 3
ESPERA_BASE_REINTENTO_S = 1.5
TAMANO_PAGINA = 300

SCOPES_FIRESTORE = [
    "https://www.googleapis.com/auth/datastore",
    "https://www.googleapis.com/auth/cloud-platform",
]

_lock_credenciales = threading.Lock()
_credenciales_cache: Dict[str, Any] = {"ruta": None, "creds": None, "project_id": None}


def ruta_credenciales() -> Optional[Path]:
    """Localiza el archivo JSON de la cuenta de servicio (FIREBASE_KEY_PATH o *adminsdk*.json)."""
    candidatos: List[Path] = []
    try:
        import firebase_client
        ruta_cfg = getattr(firebase_client, "FIREBASE_KEY_PATH", None)
        if ruta_cfg:
            candidatos.append(Path(ruta_cfg))
            if not Path(ruta_cfg).is_absolute():
                candidatos.append(rutas.DIR_BASE / ruta_cfg)
                candidatos.append(rutas.DIR_BASE.parent / ruta_cfg)
    except Exception:
        pass

    env = os.environ.get("FIREBASE_KEY_PATH")
    if env:
        candidatos.append(Path(env))

    for c in candidatos:
        try:
            if c.exists() and c.is_file():
                return c
        except Exception:
            continue

    try:
        from servicios.metricas_monitoring import _buscar_archivo_credenciales
        encontrada = _buscar_archivo_credenciales()
        if encontrada:
            return Path(encontrada)
    except Exception:
        pass
    return None


def _cargar_credenciales(ruta: Path):
    with _lock_credenciales:
        if _credenciales_cache["creds"] is not None and _credenciales_cache["ruta"] == str(ruta):
            return _credenciales_cache["creds"], _credenciales_cache["project_id"]

        from google.oauth2 import service_account

        with open(ruta, "r", encoding="utf-8") as f:
            datos = json.load(f)
        project_id = str(datos.get("project_id") or "").strip()
        if not project_id:
            raise ValueError(f"El archivo de credenciales no contiene 'project_id':\n  {ruta}")
        creds = service_account.Credentials.from_service_account_file(str(ruta), scopes=SCOPES_FIRESTORE)
        _credenciales_cache.update({"ruta": str(ruta), "creds": creds, "project_id": project_id})
        return creds, project_id


def crear_sesion_autenticada():
    """Devuelve (sesion AuthorizedSession, project_id). Renueva el token automáticamente."""
    ruta = ruta_credenciales()
    if ruta is None:
        raise FileNotFoundError(
            "No se encontró el archivo de credenciales de Firebase (cuenta de servicio *.json).\n"
            "Revisa FIREBASE_KEY_PATH en config_local.py o coloca el archivo "
            "*firebase-adminsdk*.json junto al programa."
        )
    creds, project_id = _cargar_credenciales(ruta)
    from google.auth.transport.requests import AuthorizedSession
    return AuthorizedSession(creds), project_id


def valor_desde_firestore(valor: Any) -> Any:
    """Convierte un `Value` REST de Firestore en un valor Python plano."""
    if not isinstance(valor, dict):
        return valor
    if "nullValue" in valor:
        return None
    if "booleanValue" in valor:
        return bool(valor["booleanValue"])
    if "integerValue" in valor:
        try:
            return int(valor["integerValue"])
        except (TypeError, ValueError):
            return valor["integerValue"]
    if "doubleValue" in valor:
        v = valor["doubleValue"]
        try:
            f = float(v)
        except (TypeError, ValueError):
            return v
        return int(f) if f.is_integer() else f
    if "stringValue" in valor:
        return valor["stringValue"]
    if "timestampValue" in valor:
        return valor["timestampValue"]
    if "referenceValue" in valor:
        return valor["referenceValue"]
    if "geoPointValue" in valor:
        return dict(valor["geoPointValue"])
    if "bytesValue" in valor:
        return valor["bytesValue"]
    if "arrayValue" in valor:
        return [valor_desde_firestore(v) for v in (valor["arrayValue"] or {}).get("values", []) or []]
    if "mapValue" in valor:
        return campos_desde_firestore((valor["mapValue"] or {}).get("fields", {}) or {})
    return valor


def campos_desde_firestore(fields: Dict[str, Any]) -> Dict[str, Any]:
    return {str(k): valor_desde_firestore(v) for k, v in (fields or {}).items()}


def id_desde_nombre(nombre: str) -> str:
    """'projects/p/databases/(default)/documents/mes_2026-10/30770229' -> '30770229'."""
    return str(nombre or "").rstrip("/").rsplit("/", 1)[-1]


def _mensaje_http(status: int, cuerpo: str, coleccion: str) -> str:
    detalle = ""
    try:
        detalle = (json.loads(cuerpo).get("error") or {}).get("message") or ""
    except Exception:
        detalle = (cuerpo or "")[:200]
    if status in (401, 403):
        return (
            f"Firebase rechazó el acceso a la colección '{coleccion}' (HTTP {status}).\n"
            "Verifica que la cuenta de servicio tenga permiso sobre Cloud Firestore "
            f"(rol 'Cloud Datastore User' o 'Editor').\nDetalle: {detalle}"
        )
    if status == 404:
        return f"Firebase no encontró la base de datos del proyecto (HTTP 404).\nDetalle: {detalle}"
    return f"Error HTTP {status} al leer '{coleccion}' desde Firebase.\nDetalle: {detalle}"


def descargar_documentos_mes(
    periodo: str,
    campos: Optional[Iterable[str]] = ("medidores", "nombre"),
    callback_progreso: Optional[Callable[[int, str], None]] = None,
    sesion: Any = None,
    project_id: Optional[str] = None,
    tamano_pagina: int = TAMANO_PAGINA,
    timeout: Optional[tuple] = None,
) -> Dict[str, Dict[str, Any]]:
    """Descarga TODOS los documentos de `mes_<periodo>` por REST -> {id_documento: {campo: valor}}.
    Nunca se queda colgada: cada petición tiene timeout y como máximo REINTENTOS_POR_PAGINA intentos.
    """
    import requests

    periodo = str(periodo or "").strip()
    if not periodo:
        raise ValueError("Periodo vacío: no se puede determinar la colección mes_aaaa-mm.")
    coleccion = f"mes_{periodo}"

    if sesion is None or not project_id:
        sesion, project_id = crear_sesion_autenticada()

    base_url = (
        f"https://firestore.googleapis.com/v1/projects/{project_id}"
        f"/databases/(default)/documents/{coleccion}"
    )
    params_base: List[tuple] = [("pageSize", str(int(tamano_pagina)))]
    for campo in (campos or []):
        params_base.append(("mask.fieldPaths", str(campo)))

    tiempo_espera = timeout or (TIMEOUT_CONEXION_S, TIMEOUT_LECTURA_S)

    documentos: Dict[str, Dict[str, Any]] = {}
    page_token: Optional[str] = None

    while True:
        params = list(params_base)
        if page_token:
            params.append(("pageToken", page_token))

        ultimo_error: Optional[Exception] = None
        datos: Optional[Dict[str, Any]] = None
        for intento in range(1, REINTENTOS_POR_PAGINA + 1):
            try:
                resp = sesion.get(base_url, params=params, timeout=tiempo_espera)
            except requests.exceptions.Timeout as e:
                ultimo_error = TimeoutError(
                    "Firebase tardó demasiado en responder (más de "
                    f"{int(tiempo_espera[1])} s). Revisa tu conexión a Internet e inténtalo de nuevo."
                )
                ultimo_error.__cause__ = e
            except requests.exceptions.ConnectionError as e:
                ultimo_error = ConnectionError("No hay conexión con Firebase. Verifica que el equipo tenga Internet.")
                ultimo_error.__cause__ = e
            else:
                if resp.status_code == 200:
                    try:
                        datos = resp.json() or {}
                    except ValueError as e:
                        ultimo_error = ValueError(f"Respuesta de Firebase ilegible: {e}")
                    else:
                        break
                elif resp.status_code in (429, 500, 502, 503, 504):
                    ultimo_error = RuntimeError(_mensaje_http(resp.status_code, resp.text, coleccion))
                else:
                    raise RuntimeError(_mensaje_http(resp.status_code, resp.text, coleccion))

            if intento < REINTENTOS_POR_PAGINA:
                espera = ESPERA_BASE_REINTENTO_S * (2 ** (intento - 1))
                if callback_progreso:
                    callback_progreso(
                        len(documentos),
                        f"Reintentando conexión con Firebase ({intento}/{REINTENTOS_POR_PAGINA - 1})...",
                    )
                time.sleep(espera)

        if datos is None:
            raise ultimo_error or RuntimeError("Fallo desconocido al leer Firebase.")

        for doc in datos.get("documents", []) or []:
            if not isinstance(doc, dict):
                continue
            doc_id = id_desde_nombre(doc.get("name", ""))
            if not doc_id:
                continue
            documentos[doc_id] = campos_desde_firestore(doc.get("fields", {}) or {})

        if callback_progreso:
            callback_progreso(
                len(documentos),
                f"Descargando lecturas de la nube ({len(documentos)} documentos recibidos)...",
            )

        page_token = datos.get("nextPageToken") or None
        if not page_token:
            break

    return documentos