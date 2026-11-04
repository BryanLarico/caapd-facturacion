"""Actualizaciones portables: solo se reemplazan el ejecutable y sus recursos."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree

import certifi
import requests

import rutas
from version import REPO_ACTUALIZACIONES, VERSION

CA_BUNDLE = certifi.where()
URL_RELEASES = f"https://api.github.com/repos/{REPO_ACTUALIZACIONES}/releases"
URL_LATEST = URL_RELEASES + "/latest"
URL_ATOM = f"https://github.com/{REPO_ACTUALIZACIONES}/releases.atom"
CACHE_SEGUNDOS = 600
_cache_versiones = None
_cache_hasta = 0.0
_cache_lock = threading.Lock()
TIMEOUT = 15
HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "CAAPD-Facturacion"}


def _log(msg: str) -> None:
    try:
        ruta = rutas.ruta_aplicacion("logs", "actualizador.log")
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with ruta.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except OSError:
        pass


def _verificacion():
    if Path(CA_BUNDLE).is_file():
        return CA_BUNDLE
    _log(f"ADVERTENCIA: falta CA bundle {CA_BUNDLE}; usando verificación predeterminada.")
    return True


@dataclass
class InfoActualizacion:
    version: str
    url_zip: str
    notas: str
    nombre_zip: str
    tamano: int = 0
    fecha: str = ""


def _a_tupla(v: str) -> tuple:
    partes = [int("".join(c for c in p if c.isdigit()) or 0)
              for p in v.strip().lstrip("vV").split(".")]
    return tuple((partes + [0, 0, 0])[:3])


def hay_version_mayor(remota: str, local: str = VERSION) -> bool:
    return _a_tupla(remota) > _a_tupla(local)


def _info(data) -> Optional[InfoActualizacion]:
    if data.get("draft") or data.get("prerelease") or not data.get("tag_name"):
        return None
    for asset in data.get("assets", []):
        if str(asset.get("name", "")).lower().endswith(".zip"):
            return InfoActualizacion(
                data["tag_name"].lstrip("vV"), asset["browser_download_url"],
                data.get("body") or "", asset["name"], int(asset.get("size") or 0),
                data.get("published_at") or "")
    return None


def _listar_api() -> list[InfoActualizacion]:
    versiones = []
    url = URL_RELEASES + "?per_page=100"
    while url:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, verify=_verificacion())
        r.raise_for_status()
        versiones.extend(info for data in r.json() if (info := _info(data)))
        url = r.links.get("next", {}).get("url")
    return versiones


class _TextoNotas(HTMLParser):
    def __init__(self):
        super().__init__()
        self.partes = []

    def handle_data(self, data):
        self.partes.append(data)


def _listar_atom() -> list[InfoActualizacion]:
    r = requests.get(URL_ATOM, headers={"User-Agent": HEADERS["User-Agent"]},
                     timeout=TIMEOUT, verify=_verificacion())
    r.raise_for_status()
    raiz = ElementTree.fromstring(r.content)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    if raiz.tag != "{http://www.w3.org/2005/Atom}feed":
        raise ValueError("La respuesta no es un feed Atom de releases.")
    versiones = []
    for entrada in raiz.findall("a:entry", ns):
        enlace = next((e.get("href", "") for e in entrada.findall("a:link", ns)
                       if e.get("rel", "alternate") == "alternate"), "")
        tag = unquote(urlparse(enlace).path.rsplit("/", 1)[-1])
        if not re.fullmatch(r"v?\d+\.\d+\.\d+", tag):
            continue
        ver = tag.lstrip("v")
        notas = _TextoNotas()
        notas.feed(entrada.findtext("a:content", "", ns))
        fecha = (entrada.findtext("a:published", "", ns)
                 or entrada.findtext("a:updated", "", ns))
        nombre = f"CAAPD-{ver}.zip"
        versiones.append(InfoActualizacion(
            ver, f"https://github.com/{REPO_ACTUALIZACIONES}/releases/download/v{ver}/{nombre}",
            " ".join(notas.partes), nombre, fecha=fecha))
    _log(f"Fallback Atom: {[i.version for i in versiones]}")
    return versiones


def listar_versiones() -> list[InfoActualizacion]:
    global _cache_versiones, _cache_hasta
    with _cache_lock:
        if _cache_versiones is not None and time.monotonic() < _cache_hasta:
            _log("Releases: usando caché en memoria.")
            return list(_cache_versiones)
        try:
            versiones = _listar_api()
        except Exception as e:
            _log(f"ERROR API de releases: {e}; consultando Atom.")
            try:
                versiones = _listar_atom()
            except Exception as error_atom:
                _log(f"ERROR Atom de releases: {error_atom}")
                raise
        versiones.sort(key=lambda info: _a_tupla(info.version), reverse=True)
        _cache_versiones = list(versiones)
        _cache_hasta = time.monotonic() + CACHE_SEGUNDOS
        _log(f"Releases publicados: {[i.version for i in versiones]}")
        return versiones


def versiones_anteriores() -> list[InfoActualizacion]:
    return [i for i in listar_versiones() if _a_tupla(i.version) < _a_tupla(VERSION)]


def version_para_reparar() -> InfoActualizacion:
    versiones = listar_versiones()
    candidatas = [i for i in versiones if _a_tupla(i.version) >= _a_tupla(VERSION)]
    if not candidatas:
        raise RuntimeError("No hay una versión igual o más reciente disponible para reparar.")
    return candidatas[0]


def buscar_actualizacion() -> Optional[InfoActualizacion]:
    _log(f"Buscando actualización. Local={VERSION}")
    try:
        try:
            versiones = listar_versiones()
        except Exception as e:
            _log(f"ERROR al listar releases: {e}; consultando latest.")
            r = requests.get(URL_LATEST, headers=HEADERS, timeout=TIMEOUT,
                             verify=_verificacion())
            r.raise_for_status()
            info = _info(r.json())
            versiones = [info] if info else []
        return next((i for i in versiones if hay_version_mayor(i.version, VERSION)), None)
    except Exception as e:
        _log(f"ERROR al buscar: {e}")
        return None


def validar_zip(ruta: Path) -> None:
    try:
        with zipfile.ZipFile(ruta) as z:
            nombres = set(z.namelist())
            if not {"CAAPD.exe", "_internal/ui/estilos/tema.qss"} <= nombres:
                raise ValueError("Faltan CAAPD.exe o _internal/ui/estilos/tema.qss.")
            for nombre in nombres:
                if "\\" in nombre or nombre.startswith("/") or ".." in nombre.split("/") or ":" in nombre:
                    raise ValueError("El ZIP contiene rutas inseguras.")
            malo = z.testzip()
            if malo:
                raise ValueError(f"Archivo dañado: {malo}")
    except (zipfile.BadZipFile, ValueError) as e:
        raise ValueError(f"Actualización ZIP inválida: {e}") from e


def descargar_zip(info: InfoActualizacion,
                  progreso: Optional[Callable[[int], None]] = None) -> Path:
    fd, nombre = tempfile.mkstemp(prefix="CAAPD-update-", suffix=".zip")
    os.close(fd)
    destino = Path(nombre)
    try:
        with requests.get(info.url_zip, stream=True, timeout=60, headers=HEADERS,
                          verify=_verificacion()) as r:
            r.raise_for_status()
            total = info.tamano or int(r.headers.get("Content-Length", 0) or 0)
            leido = 0
            with destino.open("wb") as f:
                for chunk in r.iter_content(chunk_size=262144):
                    if chunk:
                        f.write(chunk)
                        leido += len(chunk)
                        if progreso and total:
                            progreso(min(100, leido * 100 // total))
        if info.tamano and leido != info.tamano:
            raise ValueError(f"Descarga incompleta: {leido} bytes; se esperaban {info.tamano}.")
        validar_zip(destino)
        _log(f"Descarga validada: {destino}, {leido} bytes")
        return destino
    except Exception as e:
        destino.unlink(missing_ok=True)
        _log(f"ERROR al descargar: {e}")
        raise


def recursos_faltantes() -> list[str]:
    if not getattr(sys, "frozen", False):
        return []
    recursos = [rutas.ruta_recurso("ui", "estilos", "tema.qss"),
                rutas.ruta_recurso("recursos", "iconos"),
                rutas.ruta_recurso("ui", "estilos", "fuentes"), Path(CA_BUNDLE)]
    faltan = [str(p) for p in recursos if not p.exists() or (p.is_dir() and not any(p.iterdir()))]
    if faltan:
        _log(f"La instalación está incompleta: {faltan}")
    return faltan


def limpiar_copias_anteriores() -> None:
    if not getattr(sys, "frozen", False) or recursos_faltantes():
        return
    for nombre in ("_internal.old", "CAAPD.exe.old"):
        p = rutas.ruta_aplicacion(nombre)
        try:
            if p.is_dir():
                shutil.rmtree(p)
            elif p.exists():
                p.unlink()
        except OSError as e:
            _log(f"Limpieza pendiente {p}: {e}")


def aplicar_y_reiniciar(ruta_zip: Path) -> None:
    if not getattr(sys, "frozen", False):
        raise RuntimeError("La actualización automática solo funciona en el .exe compilado.")
    validar_zip(ruta_zip)
    from servicios.script_actualizacion import SCRIPT
    exe = Path(sys.executable).resolve()
    trabajo = Path(tempfile.mkdtemp(prefix="CAAPD-aplicar-"))
    config = trabajo / "config.json"
    config.write_text(json.dumps(dict(exe=str(exe), zip=str(ruta_zip.resolve()),
                                     pid=os.getpid(), args=sys.argv[1:]),
                                 ensure_ascii=False), encoding="utf-8")
    script = trabajo / "actualizar.ps1"
    script.write_text(SCRIPT, encoding="utf-8-sig")
    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(script), str(config)],
        creationflags=0x00000010 | 0x00000200, close_fds=True, cwd=str(exe.parent))
    _log(f"Script lanzado: {script}")
