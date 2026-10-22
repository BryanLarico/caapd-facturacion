"""
servicios/actualizador.py — Auto-actualización vía GitHub Releases.

Flujo: consultar /releases/latest -> comparar tag con VERSION -> descargar ZIP ->
escribir un .bat que espera el cierre de la app, descomprime y relanza.
Solo reemplaza CAAPD.exe y _internal/. NUNCA toca 'Base de datos', datos,
respaldos, logs, plantillas, salida ni serviceAccountKey.json.

Diagnóstico: todo queda registrado en logs/actualizador.log junto al exe.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import certifi
import requests

import rutas
from version import REPO_ACTUALIZACIONES, VERSION

# ---------------------------------------------------------------------------
# Certificados: dentro del exe (PyInstaller) requests no siempre localiza los
# certificados raíz del sistema. Usamos el cacert.pem empaquetado por certifi.
# ---------------------------------------------------------------------------
CA_BUNDLE = certifi.where()
os.environ.setdefault("SSL_CERT_FILE", CA_BUNDLE)
os.environ.setdefault("REQUESTS_CA_BUNDLE", CA_BUNDLE)

URL_LATEST = f"https://api.github.com/repos/{REPO_ACTUALIZACIONES}/releases/latest"
TIMEOUT = 10
HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "CAAPD-Facturacion",
}


# ---------------------------------------------------------------------------
# Log
# ---------------------------------------------------------------------------
def _log(msg: str) -> None:
    try:
        ruta = rutas.ruta_aplicacion("logs", "actualizador.log")
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------
@dataclass
class InfoActualizacion:
    version: str          # "1.0.1"
    url_zip: str          # URL del asset .zip
    notas: str            # cuerpo del release (changelog)
    nombre_zip: str


# ---------------------------------------------------------------------------
# Versiones
# ---------------------------------------------------------------------------
def _a_tupla(v: str) -> tuple:
    v = v.strip().lstrip("vV")
    partes = []
    for p in v.split("."):
        num = "".join(ch for ch in p if ch.isdigit())
        partes.append(int(num) if num else 0)
    while len(partes) < 3:
        partes.append(0)
    return tuple(partes[:3])


def hay_version_mayor(remota: str, local: str = VERSION) -> bool:
    return _a_tupla(remota) > _a_tupla(local)


# ---------------------------------------------------------------------------
# Consulta
# ---------------------------------------------------------------------------
def buscar_actualizacion() -> Optional[InfoActualizacion]:
    """Devuelve InfoActualizacion si hay una versión nueva; None si no o si falla la red."""
    _log(
        f"Buscando actualización. Local={VERSION} frozen={getattr(sys, 'frozen', False)}")
    _log(f"URL={URL_LATEST}")
    _log(f"CA_BUNDLE={CA_BUNDLE} existe={os.path.exists(CA_BUNDLE)}")
    try:
        r = requests.get(URL_LATEST, timeout=TIMEOUT,
                         headers=HEADERS, verify=CA_BUNDLE)
        _log(f"HTTP {r.status_code}")
        if r.status_code != 200:
            return None

        data = r.json()
        tag = str(data.get("tag_name", "")).strip()
        es_mayor = bool(tag) and hay_version_mayor(tag)
        _log(f"Remota={tag or '(vacío)'} es_mayor={es_mayor}")
        if not es_mayor:
            return None

        asset = next(
            (a for a in data.get("assets", [])
             if str(a.get("name", "")).lower().endswith(".zip")),
            None,
        )
        if not asset:
            _log("El release no tiene un adjunto .zip; se ignora.")
            return None

        info = InfoActualizacion(
            version=tag.lstrip("vV"),
            url_zip=asset["browser_download_url"],
            notas=data.get("body") or "",
            nombre_zip=asset["name"],
        )
        _log(f"Actualización disponible: {info.nombre_zip} -> {info.url_zip}")
        return info

    except Exception as e:
        _log(f"ERROR al buscar: {type(e).__name__}: {e}")
        return None


# ---------------------------------------------------------------------------
# Descarga
# ---------------------------------------------------------------------------
def descargar_zip(info: InfoActualizacion,
                  progreso: Optional[Callable[[int], None]] = None) -> Path:
    """Descarga el ZIP a %TEMP% y devuelve la ruta. progreso(porcentaje 0-100)."""
    destino = Path(tempfile.gettempdir()) / f"CAAPD-update-{info.version}.zip"
    _log(f"Descargando {info.url_zip} -> {destino}")
    try:
        with requests.get(info.url_zip, stream=True, timeout=60,
                          headers={"User-Agent": HEADERS["User-Agent"]},
                          verify=CA_BUNDLE) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length", 0) or 0)
            leido = 0
            ultimo_pct = -1
            with open(destino, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if not chunk:
                        continue
                    f.write(chunk)
                    leido += len(chunk)
                    if progreso and total:
                        pct = min(100, int(leido * 100 / total))
                        if pct != ultimo_pct:
                            progreso(pct)
                            ultimo_pct = pct
        _log(f"Descarga completa: {leido} bytes")
        return destino
    except Exception as e:
        _log(f"ERROR al descargar: {type(e).__name__}: {e}")
        raise


# ---------------------------------------------------------------------------
# Aplicar
# ---------------------------------------------------------------------------
def aplicar_y_reiniciar(ruta_zip: Path) -> None:
    """
    Escribe un .bat que: espera a que CAAPD.exe termine, descomprime el ZIP sobre
    la carpeta de instalación (solo CAAPD.exe y _internal) y relanza la app.
    El llamador debe cerrar la aplicación después de invocar esta función.
    """
    if not getattr(sys, "frozen", False):
        raise RuntimeError(
            "La actualización automática solo funciona en el .exe compilado.")

    exe = Path(sys.executable).resolve()
    carpeta_app = exe.parent
    pid = os.getpid()
    # conserva flags como --firebase
    args = " ".join(f'"{a}"' for a in sys.argv[1:])
    tmp_extract = Path(tempfile.gettempdir()) / "CAAPD-update-extract"
    bat = Path(tempfile.gettempdir()) / "caapd_actualizar.bat"
    log_bat = rutas.ruta_aplicacion("logs", "actualizador_bat.log")

    _log(f"Aplicando actualización. exe={exe} pid={pid} zip={ruta_zip}")

    contenido = f"""@echo off
chcp 65001 >nul
title Actualizando CAAPD Ispacas...
echo ====================================================
echo   Actualizando CAAPD Ispacas. No cierre esta ventana.
echo ====================================================
echo Esperando a que se cierre la aplicacion...
:esperar
tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto esperar
)
echo Descomprimiendo actualizacion...
if exist "{tmp_extract}" rmdir /s /q "{tmp_extract}"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath '{ruta_zip}' -DestinationPath '{tmp_extract}' -Force"
if errorlevel 1 (
    echo [%date% %time%] ERROR al descomprimir >> "{log_bat}"
    echo ERROR al descomprimir. La aplicacion NO fue modificada.
    pause
    exit /b 1
)
echo Reemplazando archivos del programa...
if exist "{carpeta_app / '_internal'}" rmdir /s /q "{carpeta_app / '_internal'}"
robocopy "{tmp_extract}" "{carpeta_app}" /E /R:3 /W:2 /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
    echo [%date% %time%] ERROR robocopy codigo %errorlevel% >> "{log_bat}"
    echo ERROR al copiar archivos. Contacte a soporte.
    pause
    exit /b 1
)
echo [%date% %time%] Actualizacion aplicada OK desde {ruta_zip.name} >> "{log_bat}"
echo Limpiando...
rmdir /s /q "{tmp_extract}" 2>nul
del /q "{ruta_zip}" 2>nul
echo Iniciando CAAPD actualizado...
start "" "{exe}" {args}
(goto) 2>nul & del "%~f0"
"""
    bat.write_text(contenido, encoding="utf-8")

    # Consola propia y grupo de procesos independiente: el .bat sobrevive al cierre
    # de esta app y el usuario ve el progreso del reemplazo.
    CREATE_NEW_CONSOLE = 0x00000010
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    subprocess.Popen(
        ["cmd.exe", "/c", str(bat)],
        creationflags=CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
        cwd=str(carpeta_app),
    )
    _log("Script de actualización lanzado; cerrando la aplicación.")
