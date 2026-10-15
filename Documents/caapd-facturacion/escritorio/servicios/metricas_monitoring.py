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


def consultar_metricas_hoy(forzar: bool = False) -> Dict[str, Any]:
    """
    Consulta a Google Cloud Monitoring las operaciones reales de hoy (desde 00:00 Pacífico).
    No gasta cuota de Firestore. Si la API no tiene permiso o no hay conexión,
    retorna disponible=False sin lanzar excepciones.
    """
    global _CACHE_METRICAS
    ahora = time.time()
    if not forzar and _CACHE_METRICAS["resultado"] is not None and (ahora - _CACHE_METRICAS["timestamp"]) < 60.0:
        return _CACHE_METRICAS["resultado"]

    ruta_clave = _buscar_archivo_credenciales()
    if not ruta_clave:
        res = {
            "disponible": False,
            "lecturas": 0,
            "escrituras": 0,
            "fuente": "Local",
            "error": "No se encontró archivo de credenciales de Google Cloud",
        }
        _CACHE_METRICAS = {"timestamp": ahora, "resultado": res}
        return res

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

        scopes = [
            "https://www.googleapis.com/auth/cloud-platform",
            "https://www.googleapis.com/auth/monitoring.read",
        ]
        credentials = service_account.Credentials.from_service_account_file(
            str(ruta_clave),
            scopes=scopes,
        )
        credentials.refresh(Request())
        token = credentials.token

        headers = {"Authorization": f"Bearer {token}"}
        iso_inicio, iso_fin, legible_pacifico = obtener_rango_hoy_pacifico()

        base_url = f"https://monitoring.googleapis.com/v3/projects/{project_id}/timeSeries"

        # Métricas a consultar
        metricas = {
            "read_count": "firestore.googleapis.com/document/read_count",
            "write_count": "firestore.googleapis.com/document/write_count",
            "delete_count": "firestore.googleapis.com/document/delete_count",
        }

        totales = {"read_count": 0, "write_count": 0, "delete_count": 0}

        for clave_m, metric_name in metricas.items():
            params = {
                "filter": f'metric.type = "{metric_name}"',
                "interval.startTime": iso_inicio,
                "interval.endTime": iso_fin,
            }
            resp = requests.get(base_url, headers=headers, params=params, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                series = data.get("timeSeries", [])
                suma = 0
                for s in series:
                    for pt in s.get("points", []):
                        val = pt.get("value", {})
                        int_val = val.get("int64Value")
                        if int_val is not None:
                            suma += int(int_val)
                        elif "doubleValue" in val:
                            suma += int(val["doubleValue"])
                totales[clave_m] = suma
            elif resp.status_code == 403:
                # Permiso denegado: falta el rol Monitoring Viewer en GCP Console
                res = {
                    "disponible": False,
                    "lecturas": 0,
                    "escrituras": 0,
                    "fuente": "Local",
                    "error": "Requiere rol 'Monitoring Viewer' en Google Cloud Console",
                    "codigo": 403,
                }
                _CACHE_METRICAS = {"timestamp": ahora, "resultado": res}
                return res
            else:
                # Otro código HTTP
                res = {
                    "disponible": False,
                    "lecturas": 0,
                    "escrituras": 0,
                    "fuente": "Local",
                    "error": f"Error HTTP {resp.status_code} al consultar Cloud Monitoring",
                    "codigo": resp.status_code,
                }
                _CACHE_METRICAS = {"timestamp": ahora, "resultado": res}
                return res

        total_lecturas = totales["read_count"]
        total_escrituras = totales["write_count"] + totales["delete_count"]

        res = {
            "disponible": True,
            "lecturas": total_lecturas,
            "escrituras": total_escrituras,
            "fuente": "Cloud Monitoring",
            "desde_pacifico": legible_pacifico,
            "error": None,
        }
        _CACHE_METRICAS = {"timestamp": ahora, "resultado": res}
        return res

    except Exception as e:
        res = {
            "disponible": False,
            "lecturas": 0,
            "escrituras": 0,
            "fuente": "Local",
            "error": str(e),
        }
        _CACHE_METRICAS = {"timestamp": ahora, "resultado": res}
        return res
