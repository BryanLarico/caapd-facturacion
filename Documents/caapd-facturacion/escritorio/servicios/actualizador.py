"""
servicios/actualizador.py — Auto-actualización vía GitHub Releases.

Flujo: consultar /releases/latest -> comparar tag con VERSION -> descargar ZIP ->
escribir un .bat que espera el cierre de la app, descomprime y relanza.
Solo reemplaza CAAPD.exe y _internal/. NUNCA toca 'Base de datos', datos,
respaldos, logs, plantillas, salida ni serviceAccountKey.json.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import requests

import rutas
from version import REPO_ACTUALIZACIONES, VERSION

URL_LATEST = f"https://api.github.com/repos/{REPO_ACTUALIZACIONES}/releases/latest"
TIMEOUT = 10


@dataclass
class InfoActualizacion:
    version: str          # "1.0.1"
    url_zip: str          # URL del asset .zip
    notas: str            # cuerpo del release (changelog)
    nombre_zip: str


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


def buscar_actualizacion() -> Optional[InfoActualizacion]:
    """Devuelve InfoActualizacion si hay una versión nueva; None si no o si falla la red."""
    try:
        r = requests.get(
            URL_LATEST,
            timeout=TIMEOUT,
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": "CAAPD-Facturacion"},
        )
        if r.status_code != 200:
            return None
        data = r.json()
        tag = str(data.get("tag_name", "")).strip()
        if not tag or not hay_version_mayor(tag):
            return None
        asset = next(
            (a for a in data.get("assets", []) if a.get(
                "name", "").lower().endswith(".zip")),
            None,
        )
        if not asset:
            return None
        return InfoActualizacion(
            version=tag.lstrip("vV"),
            url_zip=asset["browser_download_url"],
            notas=data.get("body") or "",
            nombre_zip=asset["name"],
        )
    except Exception:
        return None


def descargar_zip(info: InfoActualizacion,
                  progreso: Optional[Callable[[int], None]] = None) -> Path:
    """Descarga el ZIP a %TEMP% y devuelve la ruta. progreso(porcentaje 0-100)."""
    destino = Path(tempfile.gettempdir()) / f"CAAPD-update-{info.version}.zip"
    with requests.get(info.url_zip, stream=True, timeout=60,
                      headers={"User-Agent": "CAAPD-Facturacion"}) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0) or 0)
        leido = 0
        with open(destino, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if not chunk:
                    continue
                f.write(chunk)
                leido += len(chunk)
                if progreso and total:
                    progreso(min(100, int(leido * 100 / total)))
    return destino


def aplicar_y_reiniciar(ruta_zip: Path) -> None:
    """
    Escribe un .bat que: espera a que CAAPD.exe termine, descomprime el ZIP sobre
    la carpeta de instalación (solo CAAPD.exe y _internal) y relanza la app.
    Luego llama a os._exit para cerrar la app actual.
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

    contenido = f"""@echo off
chcp 65001 >nul
title Actualizando CAAPD...
echo Esperando a que se cierre CAAPD...
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
    echo ERROR al descomprimir. La aplicacion NO fue modificada.
    pause
    exit /b 1
)
echo Reemplazando archivos del programa...
if exist "{carpeta_app / '_internal'}" rmdir /s /q "{carpeta_app / '_internal'}"
robocopy "{tmp_extract}" "{carpeta_app}" /E /R:3 /W:2 /NFL /NDL /NJH /NJS /NP >nul
echo Limpiando...
rmdir /s /q "{tmp_extract}" 2>nul
del /q "{ruta_zip}" 2>nul
echo Iniciando CAAPD actualizado...
start "" "{exe}" {args}
(goto) 2>nul & del "%~f0"
"""
    bat.write_text(contenido, encoding="utf-8")

    # DETACHED para que el .bat sobreviva al cierre de esta app
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    subprocess.Popen(
        ["cmd.exe", "/c", str(bat)],
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
        cwd=str(carpeta_app),
    )
