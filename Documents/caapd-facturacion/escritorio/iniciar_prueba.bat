@echo off
chcp 65001 >nul
title CAAPD Ispacas — Facturación [ENTORNO DE PRUEBA]

cd /d "%~dp0"

echo ===================================================
echo   CAAPD Ispacas — ENTORNO DE PRUEBA (Desktop)
echo   Bases y respaldos aislados en:
echo   escritorio\Base de datos PRUEBA\
echo ===================================================

set CAAPD_ENTORNO=prueba

if not exist "venv\Scripts\python.exe" (
    echo [INFO] Creando entorno virtual venv...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno virtual. Asegurese de tener Python 3.10 o superior instalado.
        pause
        exit /b 1
    )
    echo [INFO] Instalando dependencias de requirements.txt...
    venv\Scripts\python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Error instalando dependencias.
        pause
        exit /b 1
    )
)

echo [INFO] Iniciando aplicacion de escritorio en MODO PRUEBA...
start "" "venv\Scripts\python.exe" main.py
