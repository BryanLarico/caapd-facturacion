"""
servicios/metricas_monitoring.py — Consulta de métricas reales de Firestore vía Google Cloud Monitoring.

Consulta las métricas reales de Google Cloud Monitoring (read_count, write_count, delete_count)
acumuladas desde las 00:00 hora del Pacífico (EE. UU. / Los Ángeles) de hoy,
sin consumir la cuota de 50.000 lecturas de Firestore.
"""
from __future__ import annotations
import datetime
from pathlib import Path
import time
from typing import Any, Dict, Optional
import zoneinfo

import rutas

# Cache en memoria para no saturar consultas (expira en 60 segundos)
_CACHE_METRICAS: Dict[str, Any] = {
    "timestamp": 0.0,
    "resultado": None,
}


def obtener_rango_hoy_pacifico() -> tuple[str, str, str]:
    """
    Calcula el rango de tiempo desde las 00:00:00 hora del Pacífico (America/Los_Angeles)
    de hoy hasta el momento actual, devolviendo cadenas ISO-8601 en UTC (formato Z).
    """
    try:
        tz_pacifico = zoneinfo.ZoneInfo("America/Los_Angeles")
    except Exception:
        # Fallback a UTC-7 si falta zona
        tz_pacifico = datetime.timezone(datetime.timedelta(hours=-7))

    ahora_pacifico = datetime.datetime.now(tz_pacifico)
    inicio_hoy_pacifico = ahora_pacifico.replace(hour=0, minute=0, second=0, microsecond=0)

    # Convertir a UTC para la API de Cloud Monitoring
    inicio_utc = inicio_hoy_pacifico.astimezone(datetime.timezone.utc)
    fin_utc = ahora_pacifico.astimezone(datetime.timezone.utc)

    iso_inicio = inicio_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    iso_fin = fin_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    hora_legible = inicio_hoy_pacifico.strftime("%Y-%m-%d 00:00 %Z")

    return iso_inicio, iso_fin, hora_legible


def _buscar_archivo_credenciales(ruta_personalizada: Optional[Path | str] = None) -> Optional[Path]:
    """Busca el archivo de clave de cuenta de servicio json en el proyecto."""
    if ruta_personalizada:
        p = Path(ruta_personalizada)
        if p.exists():
            return p

    # Buscar en escritorio y raíz
    candidatos = [
        rutas.ruta_aplicacion("serviceAccountKey.json"),
        rutas.ruta_recurso("caapd-ispacas-optimizado-firebase-adminsdk-fbsvc-e6c4b2f0b0.json"),
        rutas.ruta_aplicacion("caapd-ispacas-optimizado-firebase-adminsdk-fbsvc-e6c4b2f0b0.json"),
        rutas.DIR_BASE.parent / "caapd-ispacas-optimizado-firebase-adminsdk-fbsvc-e6c4b2f0b0.json",
    ]
    for c in candidatos:
        if c.exists():
            return c

    # Buscar cualquier *.json de adminsdk
    for dir_cand in [rutas.DIR_BASE, rutas.DIR_BASE.parent]:
        for f in dir_cand.glob("*adminsdk*.json"):
            return f

    return None


def _log(msg: str) -> None:
    """Diagnóstico en logs/metricas.log junto al exe (nunca falla)."""
    try:
        ruta = rutas.ruta_aplicacion("logs", "metricas.log")
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except Exception:
        pass


def _mensaje_error_http(resp: Any) -> str:
    """Extrae el mensaje real que devuelve Google (p. ej. 'API no habilitada')."""
    try:
        return str(resp.json().get("error", {}).get("message") or resp.text[:300])
    except Exception:
        return str(getattr(resp, "text", "")[:300])


def _sumar_metrica(base_url: str, headers: Any, metric_name: str,
                   iso_inicio: str, iso_fin: str, requests: Any) -> int:
    """
    Total de una métrica DELTA en el rango, con agregación del lado de Google:
    - ALIGN_SUM por hora reduce miles de puntos crudos a <= 24 por serie
    - REDUCE_SUM junta todas las series (tipo de operación, base de datos...)
    y se siguen todas las páginas (nextPageToken).
    """
    params = {
        "filter": f'metric.type = "{metric_name}"',
        "interval.startTime": iso_inicio,
        "interval.endTime": iso_fin,
        "aggregation.alignmentPeriod": "3600s",
        "aggregation.perSeriesAligner": "ALIGN_SUM",
        "aggregation.crossSeriesReducer": "REDUCE_SUM",
        "view": "FULL",
    }
    suma = 0
    token_pagina = None
    for _ in range(50):  # tope de seguridad
        if token_pagina:
            params["pageToken"] = token_pagina
        resp = requests.get(base_url, headers=headers, params=params, timeout=8)
        if resp.status_code != 200:
            raise _ErrorHttp(resp.status_code, _mensaje_error_http(resp))
        data = resp.json()
        for serie in data.get("timeSeries", []):
            for pt in serie.get("points", []):
                val = pt.get("value", {})
                if val.get("int64Value") is not None:
                    suma += int(val["int64Value"])
                elif val.get("doubleValue") is not None:
                    suma += int(round(float(val["doubleValue"])))
        token_pagina = data.get("nextPageToken")
        if not token_pagina:
            break
    return suma


class _ErrorHttp(Exception):
    def __init__(self, codigo: int, mensaje: str) -> None:
        super().__init__(f"HTTP {codigo}: {mensaje}")
        self.codigo = codigo
        self.mensaje = mensaje


def consultar_metricas_hoy(forzar: bool = False) -> Dict[str, Any]:
    """
    Consulta a Google Cloud Monitoring las operaciones reales de hoy (desde 00:00 Pacífico).
    No gasta cuota de Firestore. Si la API no tiene permiso o no hay conexión,
    retorna disponible=False (con el motivo real en 'error') sin lanzar excepciones.
    """
    global _CACHE_METRICAS
    ahora = time.time()
    if not forzar and _CACHE_METRICAS["resultado"] is not None and (ahora - _CACHE_METRICAS["timestamp"]) < 60.0:
        return _CACHE_METRICAS["resultado"]

    def _no_disponible(error: str, codigo: Optional[int] = None) -> Dict[str, Any]:
        global _CACHE_METRICAS
        res = {"disponible": False, "lecturas": 0, "escrituras": 0,
               "fuente": "Local", "error": error}
        if codigo is not None:
            res["codigo"] = codigo
        _CACHE_METRICAS = {"timestamp": ahora, "resultado": res}
        _log(f"NO DISPONIBLE: {error}")
        return res

    ruta_clave = _buscar_archivo_credenciales()
    if not ruta_clave:
        return _no_disponible("No se encontró archivo de credenciales de Google Cloud")

    try:
        import json
        import requests
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account

        with open(ruta_clave, "r", encoding="utf-8") as f:
            datos_clave = json.load(f)

        project_id = datos_clave.get("project_id")
        if not project_id:
            raise ValueError("El archivo JSON no contiene 'project_id'")

        credentials = service_account.Credentials.from_service_account_file(
            str(ruta_clave),
            scopes=["https://www.googleapis.com/auth/monitoring.read"],
        )
        credentials.refresh(Request())
        headers = {"Authorization": f"Bearer {credentials.token}"}
        iso_inicio, iso_fin, legible_pacifico = obtener_rango_hoy_pacifico()
        base_url = f"https://monitoring.googleapis.com/v3/projects/{project_id}/timeSeries"

        metricas = {
            "read_count": "firestore.googleapis.com/document/read_count",
            "write_count": "firestore.googleapis.com/document/write_count",
            "delete_count": "firestore.googleapis.com/document/delete_count",
        }
        totales: Dict[str, int] = {}
        for clave_m, metric_name in metricas.items():
            totales[clave_m] = _sumar_metrica(
                base_url, headers, metric_name, iso_inicio, iso_fin, requests)

        res = {
            "disponible": True,
            "lecturas": totales["read_count"],
            "escrituras": totales["write_count"] + totales["delete_count"],
            "eliminaciones": totales["delete_count"],
            "fuente": "Cloud Monitoring",
            "desde_pacifico": legible_pacifico,
            "error": None,
        }
        _CACHE_METRICAS = {"timestamp": ahora, "resultado": res}
        _log(f"OK proyecto={project_id} desde={iso_inicio} lecturas={totales['read_count']} "
             f"escrituras={totales['write_count']} eliminaciones={totales['delete_count']}")
        return res

    except _ErrorHttp as e:
        msg = e.mensaje
        if e.codigo == 403 and ("disabled" in msg.lower() or "has not been used" in msg.lower()):
            texto = ("La API de Cloud Monitoring no está habilitada en el proyecto. "
                     "Habilítela en console.cloud.google.com/apis/library/monitoring.googleapis.com")
        elif e.codigo == 403:
            texto = ("La cuenta de servicio no tiene permiso: asigne el rol 'Visualizador de Monitoring' "
                     f"(Monitoring Viewer) en IAM. Detalle: {msg}")
        else:
            texto = f"Error HTTP {e.codigo} al consultar Cloud Monitoring: {msg}"
        return _no_disponible(texto, e.codigo)
    except Exception as e:
        return _no_disponible(f"{type(e).__name__}: {e}")
