# Generar la aplicación de Windows

Desde PowerShell, en la carpeta `escritorio`, instala los requisitos de la
aplicación y la herramienta de empaquetado:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-build.txt
.\build_windows.ps1
```

El ejecutable se genera en `dist\CAAPD\CAAPD.exe`. Se distribuye la carpeta
`dist\CAAPD` completa, no solo el `.exe`: contiene las bibliotecas y recursos de
PySide6 necesarios.

Al iniciar, la aplicación crea junto al ejecutable `Base de datos`, `datos`,
`logs`, `plantillas`, `salida` y `respaldos`. No borra archivos ya existentes y
no incluye los padrones del directorio de desarrollo; copia únicamente los
padrones que deban usarse a `dist\CAAPD\Base de datos`.

Las credenciales de Firebase no se incluyen en el ejecutable. Para habilitar
las acciones que requieren Firebase, coloca el archivo de credenciales
autorizado como `serviceAccountKey.json` junto al ejecutable, o configura la
variable de entorno `FIREBASE_KEY_PATH`. No subas ese archivo al repositorio ni
lo compartas junto con la aplicación.
