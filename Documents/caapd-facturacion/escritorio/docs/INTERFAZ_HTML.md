# INTERFAZ HTML (Flask) — convenciones de la versión que ya existe

> Léelo solo si trabajas en la versión HTML (raíz del proyecto). **Si trabajas en `escritorio/`, no toques nada de esto.**

## Qué hay
- `app.py` (Flask, `127.0.0.1:5000`, puerto y modo debug en `config_local.py`), `templates/` (`base.html`, `inicio.html`, `usuarios.html`...), `static/css/estilo.css` (variables en `:root`), `static/js/`, `iniciar.bat` (crea el entorno, instala y abre el navegador).
- Los datos se leen con `firebase_client` (caché en memoria por sesión). El contexto global (`config`, contadores de operaciones, `mes_actual`) se inyecta a todas las plantillas.
- Mensajes al usuario con `flash(...)` y las categorías `exito`, `peligro`, `info` y `aviso`.

## Convenciones para pantallas nuevas
- Heredan de `base.html`. Todo el estilo en `estilo.css`, con las clases existentes (`tarjeta`, `tarjeta-stat`, `alerta`, `boton`...). Sin estilos en línea.
- Ninguna plantilla llama a Firebase: las rutas de `app.py` preparan los datos.
- Cada cambio de datos llama a `respaldo.on_datos_cambiados(...)`.

## Pendiente conocido
`inicio.html` decide los botones con los estados del mes de forma distinta a la tabla de CONTEXTO §3b (muestra "Abrir mes nuevo" con `CERRADO` y "Generar recibos" con `ABIERTO`). Si se sigue con HTML, corrígelo según CONTEXTO.
