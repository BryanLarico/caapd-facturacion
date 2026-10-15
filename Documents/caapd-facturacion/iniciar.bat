@echo off
REM iniciar.bat — Crea el entorno virtual, instala dependencias y arranca el servidor.
REM Doble clic para usar.

echo.
echo ============================================================
echo   CAAPD Ispacas - Sistema de Facturacion de Agua Potable
echo ============================================================
echo.

REM Ir al directorio del script
cd /d "%~dp0"

REM Crear el entorno virtual si no existe
if not exist "venv\" (
    echo [1/3] Creando entorno virtual Python...
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: No se pudo crear el entorno virtual.
        echo Verifica que Python 3.11+ este instalado y en el PATH.
        pause
        exit /b 1
    )
)

REM Activar el entorno virtual
call venv\Scripts\activate.bat

REM Instalar/actualizar dependencias
echo [2/3] Instalando dependencias...
pip install -q -r requirements.txt
if errorlevel 1 (
    echo ERROR: Fallo la instalacion de dependencias.
    pause
    exit /b 1
)

REM Verificar que config_local.py tiene la clave correcta
if not exist "config_local.py" (
    echo ERROR: No se encontro config_local.py
    echo Crea el archivo con la ruta a tu clave Firebase.
    pause
    exit /b 1
)

echo [3/3] Iniciando servidor en http://127.0.0.1:5000
echo.
echo Abre tu navegador en:  http://127.0.0.1:5000
echo Para detener el servidor presiona Ctrl+C
echo.

REM Abrir el navegador automaticamente (espera 2 segundos)
start "" /b timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:5000"

REM Iniciar Flask
python app.py

pause
