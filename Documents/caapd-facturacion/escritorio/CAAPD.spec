# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.building.datastruct import Tree
from PyInstaller.utils.hooks import collect_all


ROOT = Path(SPECPATH).resolve()
datas = [
    (str(ROOT / "ui" / "estilos" / "tema.qss"), "ui/estilos"),
    (str(ROOT / "ui" / "estilos" / "fuentes" / "Inter-Variable.ttf"), "ui/estilos/fuentes"),
    (str(ROOT / "ui" / "estilos" / "fuentes" / "OFL.txt"), "ui/estilos/fuentes"),
]
datas.append((str(ROOT / "recursos"), "recursos"))
binaries = []
hiddenimports = []

for package in (
    "firebase_admin",
    "google.cloud.firestore_v1",
    "google.api_core",
    "google.auth",
    "reportlab",
    "qrcode",
    "certifi",
):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["config_local", "pytest", "tests"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CAAPD",
    icon=str(ROOT / "recursos" / "caapd.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="CAAPD",
)
