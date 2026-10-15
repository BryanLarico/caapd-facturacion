# ESCRITORIO D1 — Base de la aplicación de escritorio e Inicio (réplica del HTML)

**Antigravity:** conversación nueva, modo Planning:
`Lee docs/CONTEXTO.md y docs/INTERFAZ_ESCRITORIO.md y ejecuta docs/ESCRITORIO_D1_BASE_E_INICIO.md.`

## Objetivo
Crear **desde cero** `escritorio/`, un proyecto aparte con ventana nativa, que se vea y se sienta como el HTML actual. **No modifiques ningún archivo fuera de `escritorio/`.**

## Tareas
1. **Auditoría (primero, sin escribir código).** Lee `app.py`, `templates/*.html`, `static/css/estilo.css`, `firebase_client.py`, `respaldo.py`, `codigos.py` y las capturas de `docs/capturas/html/`. Dame: (a) lista de lo que se va a reutilizar, (b) paleta y medidas extraídas del CSS, (c) plan. **Espera mi OK.**
2. **Entorno propio.** `escritorio/venv`, `requirements.txt` (PySide6, firebase-admin, openpyxl, reportlab, matplotlib, qrcode con Pillow, pytest, pytest-qt) y `iniciar.bat` (crea el entorno si falta, instala y abre la aplicación). `pytest.ini` con `pythonpath = . ..`.
3. **`rutas.py`.** Agrega la raíz del proyecto a `sys.path` para importar `firebase_client`, `calculos`, `codigos`, `respaldo` y `config_local` **sin copiarlos**. Todas las rutas se calculan desde la ubicación del programa. Prueba que `import firebase_client` funciona desde `escritorio/` sin conectarse.
4. **Tema.** Extrae del CSS a `ui/estilos/paleta.py` y `tema.qss`. Mismos colores, radios, tipografía y degradados.
5. **Ventana principal.** Barra superior con "CAAPD Ispacas" y los 6 enlaces (Inicio, Usuarios, Lecturas, Recibos, Cobros, Configuración) con los mismos íconos; el activo resaltado. Barra de estado inferior con "CAAPD Ispacas © 2026", Lecturas, Escrituras, "Límite diario: 50 000 lect. / 20 000 escrit." (de `fb.get_ops()`), y los avisos de `fb.hay_aviso_ops()` en color de alerta.
6. **Avisos** equivalentes a `flash` con los 4 tipos (exito, peligro, info, aviso), como componente reutilizable.
7. **Inicio**, igual a `inicio.html`:
   - Encabezado "Panel de control — Facturación mensual de agua potable".
   - Si no hay mes: alerta amarilla "No hay un mes activo. Ve a Recibos para abrir el primer mes."
   - Si hay mes: banner con el periodo (AAAA/MM), emisión, vencimiento y estado, y los botones **según la tabla de CONTEXTO §3b** (no copies la lógica de botones de `inicio.html`; anota la diferencia en tu resumen). Por ahora los botones llevan a las páginas correspondientes.
   - 3 tarjetas: Recibos generados, Pagados (verde) y Pendientes de pago (naranja).
   - "Avance de lecturas por sector": una fila por sector con "x de y", ✅ al 100 % y barra de progreso (verde al completar). Sin datos: "Sin datos — Abre un mes para ver el avance de lecturas."
   - Las estadísticas salen de una **función pura** `servicios/estadisticas.py` (misma lógica que la ruta `inicio` de `app.py`) con pruebas.
8. **Páginas restantes** (Usuarios, Lecturas, Recibos, Cobros, Configuración): aviso "Esta pantalla estará disponible en la Fase N", como en el HTML. Usuarios se completa en D2.
9. **Botón Actualizar**: `limpiar_cache(limpiar_config=True)` y recarga, en segundo plano.
10. **Hilos** (`ui/hilos.py`) e indicador de carga: la ventana aparece al instante y Inicio se llena cuando llegan los datos. Errores de Firebase en un diálogo claro, sin cerrar el programa.
11. **Rendimiento:** mide y anota en `escritorio/RENDIMIENTO.md` el tiempo hasta ventana visible y hasta Inicio con datos (primera carga y con caché).
12. **Pruebas** con pytest y pytest-qt (offscreen): la ventana abre, navega por las 6 páginas, el pie muestra contadores y las estadísticas de Inicio son correctas con un doble en memoria.

## Criterios de aceptación
- `escritorio\iniciar.bat` abre la ventana de escritorio con un aspecto muy cercano al HTML.
- La aplicación HTML sigue funcionando exactamente igual (`git status` / lista de archivos modificados fuera de `escritorio/` = ninguno).
- Cambiar un color en `paleta.py` cambia toda la aplicación.
- `pytest` pasa en `escritorio/` y en la raíz.

## Al terminar
Resume, muestra las mediciones de rendimiento y **espera mi OK** para D2.
