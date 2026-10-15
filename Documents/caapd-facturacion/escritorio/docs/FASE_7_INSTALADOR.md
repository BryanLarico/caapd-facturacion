# FASE 7 — Ejecutable e instalador para Windows

**Cómo usarlo en Antigravity:** conversación nueva, modo Planning, y escribe:
`Lee docs/CONTEXTO.md y ejecuta docs/FASE_7_INSTALADOR.md.`
Haz esta fase solo si la versión de **escritorio** fue la elegida (`ESCRITORIO_D8_CONSOLIDAR.md`) y las Fases 3 a 6 están aprobadas.

## Objetivo
Una aplicación que la secretaria instale con doble clic, abra desde un ícono del escritorio, y que **conserve sus datos** al actualizar o desinstalar.

## Tareas
1. **Identidad.** Ícono `.ico` (una gota de agua sencilla; si no hay, genera uno), nombre "CAAPD Ispacas", versión visible en el pie (`version.py`).
2. **Ejecutable.** Usa `pyside6-deploy` (Nuitka) como primera opción. Si falla o tarda demasiado, usa PyInstaller en **modo carpeta** (no un solo archivo: abre más rápido). Crea `build.py` (o `build.bat`) que haga todo con un comando.
3. **Datos fuera del programa.** La app se instala en `C:\Program Files\CAAPD Ispacas\` y sus datos viven en `C:\CAAPD\` (`datos`, `respaldos`, `recibos`, `salida`, `serviceAccountKey.json`, `cola_pendiente.json`, el log). `rutas.py` apunta ahí. **Nada de datos dentro del ejecutable.**
4. **Primer arranque** (asistente de 3 pasos): crea las carpetas, pide seleccionar el archivo `serviceAccountKey.json` (lo copia a `C:\CAAPD\`) y prueba la conexión a Firebase mostrando "Conexión correcta" o el error en español. Nunca incluyas la clave en el instalador.
5. **Instalador con Inno Setup** (`instalador/caapd.iss`): en español, accesos directos en el escritorio y en el menú Inicio, la versión. **Al desinstalar o actualizar NO se borra `C:\CAAPD\`.** Instalar una versión nueva encima conserva todo.
6. **Cierre seguro.** Al cerrar la ventana se genera el respaldo (Fase 6) con el aviso "Guardando respaldo...". Si hay cambios sin enviar en la cola, avisa antes de salir.
7. **Registro de errores.** Archivo de log con rotación en `C:\CAAPD\logs\`, sin credenciales. Un botón "Abrir carpeta de registros" en Configuración.
8. **Documentación** `docs/INSTALACION.md` (en español, para la secretaria y para ti): requisitos (Windows 10 u 11), cómo compilar, cómo generar el instalador, cómo instalar, cómo actualizar y cómo desinstalar sin perder datos. Incluye una sección sobre el **antivirus**: los ejecutables creados con estas herramientas a veces son marcados como falsos positivos; explica cómo agregar `C:\Program Files\CAAPD Ispacas\` y `C:\CAAPD\` a las excepciones de Windows Defender.

## Pruebas (checklist para la PC de la secretaria o una máquina limpia)
- Instala sin tener Python instalado y abre desde el ícono.
- Primer arranque: selecciona la clave y confirma la conexión.
- Funciona con y sin internet (modo respaldo y cola de la Fase 6).
- Cierra la ventana → se crea el respaldo.
- Instala una versión nueva encima → los datos siguen ahí.
- Desinstala → `C:\CAAPD\` sigue intacta.
- Genera un recibo PDF y un Excel de respaldo desde el programa instalado.

## Criterios de aceptación
- Un solo comando genera el ejecutable y otro el instalador.
- Instalar, actualizar y desinstalar no pierde datos.
- El ejecutable abre en menos de unos pocos segundos y la ventana nunca se congela.

## Al terminar
Resume, entrega los pasos exactos de compilación y la checklist, y **espera mi OK**.
